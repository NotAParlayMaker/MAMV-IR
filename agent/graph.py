"""MAMV-IR LangGraph: execution creates evidence, never completion by itself."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import inspect
from difflib import SequenceMatcher
from typing import Any

from langgraph.graph import END, StateGraph

from .informational.constitution import review
from .informational.ledger import chained_event
from .informational.models import (
    AcceptanceCriterion,
    Claim,
    Context,
    Evidence,
    ExecutionAttempt,
    LedgerEvent,
    VerificationResult,
    new_id,
    now,
)
from .informational.observers import authorize_claim_verification
from .llm import LLMBackend, LLMCallFailed
from .prompts import (
    CORRECT_JSON, DIAGNOSE_PROMPT, DIAGNOSE_SYSTEM_PROMPT, GENERATE_PROMPT,
    GENERATE_SYSTEM_PROMPT, GOAL_INTERPRETATION, MISSING_CODE_FENCE,
    PLAN_PROMPT, PLAN_SYSTEM_PROMPT, REPAIR_PROMPT, REPAIR_SYSTEM_PROMPT,
)
from .sandbox import Sandbox
from .state import AgentState

CONFIDENCE_THRESHOLD = float(os.environ.get("MAMV_IR_CONFIDENCE_THRESHOLD", "0.80"))
_BUILTIN_METHODS = {
    "exit_code",
    "stdout_contains",
    "not_timed_out",
    "tests_pass",
    "passes_static_analysis",
}
LOOP_SIMILARITY_THRESHOLD = 1.0


def _append(state: AgentState, key: str, item: Any) -> list[Any]:
    return [*state.get(key, []), item]


def _context(state: AgentState, code: str | None = None) -> Context:
    return Context(
        iteration=state.get("iteration", 0),
        goal=state.get("normalized_goal", state["goal"]),
        runtime="python",
        sandbox=state.get("sandbox_name"),
        model=state.get("model_name"),
        code_hash=hashlib.sha256(code.encode()).hexdigest() if code else None,
        environment_metadata={"pid": os.getpid()},
    )


def _event(state: AgentState, event_type: str, actor: str, context: Context, payload: dict) -> LedgerEvent:
    prior_events = state.get("ledger_events", [])
    return chained_event(
        event_id=new_id("evt"),
        event_type=event_type,
        actor=actor,
        timestamp=now(),
        context=context,
        payload=payload,
        prior=prior_events[-1] if prior_events else None,
    )


def _chat(llm: LLMBackend, messages: list[dict[str, str]], temperature: float) -> str:
    """Use the override when supported while keeping legacy adapters compatible."""
    parameters = inspect.signature(llm.chat).parameters.values()
    if "temperature" in inspect.signature(llm.chat).parameters or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return llm.chat(messages, temperature=temperature)
    return llm.chat(messages)


def _fenced_code(reply: str) -> str | None:
    marker = "```python"
    start = reply.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = reply.find("```", start)
    return reply[start : end].strip() if end >= 0 else None


def _extract_code(llm: LLMBackend, messages: list[dict[str, str]], reply: str, temperature: float) -> tuple[str | None, list[str]]:
    """Request one corrective response before declaring model code unparseable."""
    responses = [reply]
    code = _fenced_code(reply)
    if code is not None:
        return code, responses
    corrected_messages = [*messages, {"role": "assistant", "content": reply}, {"role": "user", "content": MISSING_CODE_FENCE}]
    corrected = _chat(llm, corrected_messages, temperature)
    responses.append(corrected)
    return _fenced_code(corrected), responses


def _attempt_history(attempts: list[ExecutionAttempt]) -> str:
    """Render every prior execution so a repair can avoid known-bad fixes."""
    return "\n\n".join(
        f"Attempt {index}:\n```python\n{attempt.code}\n```\n"
        f"Failure evidence: stdout={attempt.stdout!r}; stderr={attempt.stderr!r}; "
        f"exit_code={attempt.exit_code}; timed_out={attempt.timed_out}"
        for index, attempt in enumerate(attempts, start=1)
    )


def _is_repeated_repair(code: str, attempts: list[ExecutionAttempt]) -> bool:
    """Reject exact normalized-code repeats (similarity ratio of 1.0)."""
    normalized = "\n".join(line.rstrip() for line in code.strip().splitlines())
    return any(
        SequenceMatcher(None, normalized, "\n".join(line.rstrip() for line in attempt.code.strip().splitlines())).ratio()
        >= LOOP_SIMILARITY_THRESHOLD
        for attempt in attempts
    )


def _structured_goal(llm: LLMBackend, goal: str) -> tuple[dict, list[str]]:
    raw_responses: list[str] = []
    messages = [
        {"role": "system", "content": PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": f"Goal: {goal}\n\n{GOAL_INTERPRETATION}"},
    ]
    for _ in range(2):
        reply = _chat(llm, messages, 0.3)
        raw_responses.append(reply)
        try:
            payload = json.loads(reply)
            if not isinstance(payload.get("acceptance_criteria"), list):
                raise ValueError("acceptance_criteria must be a list")
            return payload, raw_responses
        except (json.JSONDecodeError, ValueError, TypeError):
            messages.append({"role": "user", "content": CORRECT_JSON})
    return {
        "normalized_goal": goal,
        "assumptions": [],
        "ambiguities": ["Goal interpretation unavailable; no unobserved result may be accepted."],
        "acceptance_criteria": [
            {
                "description": "Program exits without runtime error",
                "verification_method": "exit_code",
                "required": True,
                "expected_result": "0",
            },
            {
                "description": "Goal outcome is independently evidenced",
                "verification_method": "stdout_contains",
                "required": True,
                "expected_result": "Result:",
            },
        ],
        "required_evidence": ["exit_code", "stdout"],
    }, raw_responses


def _static_analysis(code: str) -> dict[str, Any]:
    """Run deliberately minimal offline checks: syntax/compile plus bare except."""
    try:
        tree = ast.parse(code)
        compile(tree, "<generated-code>", "exec")
    except (SyntaxError, ValueError, TypeError) as exc:
        return {
            "passed": False,
            "checks": ["ast.parse", "compile"],
            "issues": [str(exc)],
        }
    bare_excepts = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler) and node.type is None)
    issues = ["bare except clause"] * bare_excepts
    return {
        "passed": not issues,
        "checks": ["ast.parse", "compile", "bare_except"],
        "issues": issues,
    }


def _test_result(sandbox: Sandbox, code: str, test_code: str | None) -> dict[str, Any] | None:
    """Run pytest through the sandbox only when interpretation supplied tests."""
    if test_code is None:
        return None
    try:
        result = sandbox.run_tests(code, test_code)
    except (AttributeError, NotImplementedError) as exc:
        return {
            "passed": False,
            "collected": 0,
            "passed_count": 0,
            "failed_count": 0,
            "error": str(exc),
        }
    passed_count = result.stdout.count(" passed")
    failed_count = result.stdout.count(" failed") + result.stdout.count(" error")
    return {
        "passed": result.success,
        "collected": passed_count + failed_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def build_graph(llm: LLMBackend, sandbox: Sandbox):
    """Build the evidence-producing graph and its verification/retry loop."""
    graph = StateGraph(AgentState)

    def llm_unavailable(state: AgentState, exc: LLMCallFailed) -> AgentState:
        context = _context(state)
        evidence = Evidence(new_id("ev"), "llm_call_failure", str(exc), "reasoning_model", context, {"authoritative": False})
        return {**state, "evidence": _append(state, "evidence", evidence), "done": True, "success": False,
                "completion_status": "llm_unavailable", "final_answer": "Abstained: the LLM provider was unavailable."}

    def unparseable_output(state: AgentState, responses: list[str]) -> AgentState:
        context = _context(state)
        evidence = Evidence(new_id("ev"), "model_output_unparseable", responses, "reasoning_model", context, {"structured": False})
        return {**state, "evidence": _append(state, "evidence", evidence), "done": True, "success": False,
                "completion_status": "model_output_unparseable", "final_answer": "Abstained: the model did not return parseable fenced Python code."}

    def interpret_goal(state: AgentState) -> AgentState:
        """Propose goal criteria and retain model-output evidence; may retain test_code."""
        try:
            payload, raw_responses = _structured_goal(llm, state["goal"])
        except LLMCallFailed as exc:
            return llm_unavailable(state, exc)
        context = _context(state)
        criteria = [
            AcceptanceCriterion(
                criterion_id=f"criterion_{index + 1}",
                **item,
                approval_status="approved" if item.get("verification_method") in _BUILTIN_METHODS else "proposed",
                approved_by="policy" if item.get("verification_method") in _BUILTIN_METHODS else None,
                approval_source="deterministic_low_risk_v1"
                if item.get("verification_method") in _BUILTIN_METHODS
                else None,
            )
            for index, item in enumerate(payload["acceptance_criteria"])
        ]
        evidence = list(state.get("evidence", []))
        for response in raw_responses:
            evidence.append(
                Evidence(
                    new_id("ev"),
                    "model_output",
                    response,
                    "reasoning_model",
                    context,
                    {"structured": False},
                )
            )
        claims = list(state.get("claims", []))
        evidence_ids = [evidence[-1].evidence_id] if raw_responses else []
        claims.append(
            Claim(
                new_id("claim"),
                "Goal interpretation was proposed.",
                "interpretation",
                "reasoning_model",
                context,
                evidence_ids,
                0.5,
                "supported",
            )
        )
        update = {
            **state,
            "original_goal": state["goal"],
            "normalized_goal": payload["normalized_goal"],
            "assumptions": payload.get("assumptions", []),
            "ambiguities": payload.get("ambiguities", []),
            "acceptance_criteria": criteria,
            "required_evidence": payload.get("required_evidence", []),
            "evidence": evidence,
            "claims": claims,
            "ledger_events": _append(
                state,
                "ledger_events",
                _event(
                    state,
                    "goal_interpreted",
                    "reasoning_model",
                    context,
                    {"criteria": len(criteria)},
                ),
            ),
        }
        if "test_code" in payload:
            update["test_code"] = payload["test_code"]
        return update

    def plan(state: AgentState) -> AgentState:
        """Produce a non-authoritative plan consumed by code generation."""
        messages = [{"role": "system", "content": PLAN_SYSTEM_PROMPT}, {"role": "user", "content": PLAN_PROMPT.format(goal=state["normalized_goal"])}]
        try:
            reply = _chat(llm, messages, 0.5)
        except LLMCallFailed as exc:
            return llm_unavailable(state, exc)
        return {**state, "plan": reply, "scratchpad": _append(state, "scratchpad", f"[plan]\n{reply}")}

    def generate(state: AgentState) -> AgentState:
        """Generate candidate code; malformed model output causes abstention, not execution."""
        messages = [{"role": "system", "content": GENERATE_SYSTEM_PROMPT}, {"role": "user", "content": GENERATE_PROMPT.format(goal=state["normalized_goal"], plan=state["plan"])}]
        try:
            reply = _chat(llm, messages, 0.3)
            code, responses = _extract_code(llm, messages, reply, 0.3)
        except LLMCallFailed as exc:
            return llm_unavailable(state, exc)
        if code is None:
            return unparseable_output(state, responses)
        return {**state, "current_code": code, "scratchpad": _append(state, "scratchpad", "[generate_code]\n" + "\n".join(responses))}

    def execute(state: AgentState) -> AgentState:
        """Execute runtime/tests and static checks, producing provenance-bound evidence."""
        code = state["current_code"]
        context = _context(state, code)
        runtime_result = sandbox.run(code)
        evidence = list(state.get("evidence", []))
        created: list[Evidence] = []
        for evidence_type, value in (
            ("stdout", runtime_result.stdout),
            ("stderr", runtime_result.stderr),
            ("exit_code", runtime_result.exit_code),
            ("timeout", runtime_result.timed_out),
        ):
            record = Evidence(
                new_id("ev"),
                evidence_type,
                value,
                "sandbox",
                context,
                {"authoritative": True},
            )
            evidence.append(record)
            created.append(record)
        static_record = Evidence(
            new_id("ev"),
            "static_analysis_result",
            _static_analysis(code),
            "static_analyzer",
            context,
            {"authoritative": True},
        )
        evidence.append(static_record)
        test_record: Evidence | None = None
        result = _test_result(sandbox, code, state.get("test_code"))
        if result is not None:
            test_record = Evidence(
                new_id("ev"),
                "test_result",
                result,
                "test_runner",
                context,
                {"authoritative": True},
            )
            evidence.append(test_record)
        attempt = ExecutionAttempt(
            new_id("attempt"),
            code,
            runtime_result.stdout,
            runtime_result.stderr,
            runtime_result.exit_code,
            runtime_result.timed_out,
            context,
            [record.evidence_id for record in created],
        )
        claims = list(state.get("claims", []))
        if state.get("attempts"):
            prior_attempt_ids = [attempt.attempt_id]
            claims.extend(
                Claim(
                    new_id("claim"),
                    claim.statement,
                    claim.claim_type,
                    claim.observer,
                    context,
                    [*claim.evidence_ids, *attempt.evidence_ids],
                    claim.confidence,
                    "contradicted",
                    [claim.claim_id],
                    prior_attempt_ids,
                    claim.claim_id,
                )
                for claim in claims
                if claim.claim_type == "prediction" and claim.status == "proposed"
            )
        for record in created:
            claims.append(
                Claim(
                    new_id("claim"),
                    f"Sandbox observed {record.evidence_type}: {record.value!r}",
                    "observation",
                    "sandbox",
                    context,
                    [record.evidence_id],
                    1.0,
                    "verified",
                )
            )
        for record, observer in (
            (static_record, "static_analyzer"),
            (test_record, "test_runner"),
        ):
            if record is None:
                continue
            claim = Claim(
                new_id("claim"),
                f"{record.evidence_type} was observed.",
                "observation",
                observer,
                context,
                [record.evidence_id],
                1.0,
                "verified",
            )
            if authorize_claim_verification(claim, evidence).allowed:
                claims.append(claim)
        ledger = _append(
            state,
            "ledger_events",
            _event(
                state,
                "executed",
                "sandbox",
                context,
                {
                    "attempt_id": attempt.attempt_id,
                    "exit_code": runtime_result.exit_code,
                    "timed_out": runtime_result.timed_out,
                },
            ),
        )
        return {
            **state,
            "evidence": evidence,
            "claims": claims,
            "attempts": _append(state, "attempts", attempt),
            "ledger_events": ledger,
            "scratchpad": _append(
                state,
                "scratchpad",
                f"[execute] exit={runtime_result.exit_code}\nstdout: {runtime_result.stdout}\nstderr: {runtime_result.stderr}",
            ),
        }

    def verify(state: AgentState) -> AgentState:
        """Evaluate criteria only against their matching, authoritative evidence."""
        attempt = state["attempts"][-1]
        results: list[VerificationResult] = []
        claims = list(state["claims"])
        evidence_by_id = {record.evidence_id: record for record in state["evidence"]}
        for criterion in state["acceptance_criteria"]:
            supported: list[str] = []
            contradictory: list[str] = []
            uncertainties: list[str] = []
            satisfied = False
            observer = "sandbox"
            matching: list[Evidence] = []
            if criterion.verification_method == "exit_code":
                satisfied = attempt.exit_code == int(criterion.expected_result or 0)
                matching = [
                    evidence_by_id[eid]
                    for eid in attempt.evidence_ids
                    if evidence_by_id[eid].evidence_type == "exit_code"
                ]
            elif criterion.verification_method == "stdout_contains" and criterion.expected_result:
                satisfied = criterion.expected_result in attempt.stdout
                matching = [
                    evidence_by_id[eid] for eid in attempt.evidence_ids if evidence_by_id[eid].evidence_type == "stdout"
                ]
            elif criterion.verification_method == "not_timed_out":
                satisfied = not attempt.timed_out
                matching = [
                    evidence_by_id[eid]
                    for eid in attempt.evidence_ids
                    if evidence_by_id[eid].evidence_type == "timeout"
                ]
            elif criterion.verification_method == "tests_pass":
                observer = "test_runner"
                matching = [
                    e
                    for e in state["evidence"]
                    if e.evidence_type == "test_result" and e.context.code_hash == attempt.context.code_hash
                ]
                if matching:
                    satisfied = bool(matching[-1].value["passed"])
                else:
                    uncertainties.append("No test evidence available; interpretation did not provide test_code.")
            elif criterion.verification_method == "passes_static_analysis":
                observer = "static_analyzer"
                matching = [
                    e
                    for e in state["evidence"]
                    if e.evidence_type == "static_analysis_result" and e.context.code_hash == attempt.context.code_hash
                ]
                if matching:
                    satisfied = bool(matching[-1].value["passed"])
                else:
                    uncertainties.append("No static-analysis evidence available.")
            else:
                uncertainties.append(
                    f"Unsupported verification method: {criterion.verification_method!r}; no evaluator is implemented."
                )
            (supported if satisfied else contradictory).extend(e.evidence_id for e in matching)
            explanation = "Direct authoritative evidence evaluated." if not uncertainties else uncertainties[0]
            confidence = 1.0 if satisfied else 0.0
            results.append(
                VerificationResult(
                    criterion.criterion_id,
                    satisfied,
                    confidence,
                    explanation,
                    observer,
                    supported,
                    contradictory,
                    uncertainties,
                )
            )
            claims.append(
                Claim(
                    new_id("claim"),
                    f"Criterion {criterion.criterion_id} {'is' if satisfied else 'is not'} satisfied.",
                    "inference",
                    "reasoning_model",
                    _context(state, attempt.code),
                    supported + contradictory,
                    confidence,
                    "supported" if satisfied else "contradicted",
                    [],
                )
            )
        return {**state, "verification_results": results, "claims": claims}

    def constitutional(state: AgentState) -> AgentState:
        """Consume verification results to gate completion and record the decision."""
        iteration = state.get("iteration", 0) + 1
        required = [
            result
            for result in state["verification_results"]
            if next(c for c in state["acceptance_criteria"] if c.criterion_id == result.criterion_id).required
        ]
        all_verified = all(
            result.satisfied and result.confidence >= CONFIDENCE_THRESHOLD for result in required
        ) and all(c.approval_status == "approved" for c in state["acceptance_criteria"] if c.required)
        contradicted = any(not result.satisfied for result in required)
        decision = {
            "status": "verified" if all_verified else ("contradicted" if contradicted else "insufficient evidence"),
            "claim_ids": [claim.claim_id for claim in state["claims"] if claim.status != "contradicted"],
            "evidence_ids": [record.evidence_id for record in state["evidence"]],
        }
        candidate = {**state, "iteration": iteration, "final_decision": decision}
        violations = review(candidate)
        success = bool(
            state["attempts"]
            and not state["attempts"][-1].timed_out
            and all_verified
            and not contradicted
            and not violations
        )
        done = success or iteration >= state.get("max_iterations", 3)
        failed = "; ".join(result.explanation for result in state["verification_results"] if not result.satisfied)
        answer = (
            state["attempts"][-1].stdout.strip()
            if success
            else (
                ("Gave up after reaching max_iterations. " if done else "Verification rejected completion: ") + failed
            )
        )
        return {
            **candidate,
            "constitutional_violations": violations,
            "success": success,
            "done": done,
            "completion_status": "verified" if success else ("exhausted" if done else decision["status"]),
            "final_answer": answer,
            "ledger_events": _append(
                state,
                "ledger_events",
                _event(
                    state,
                    "constitutional_review",
                    "governance",
                    _context(state),
                    {"success": success, "violations": violations},
                ),
            ),
        }

    def diagnose(state: AgentState) -> AgentState:
        """Interpret failed evidence for repair; it produces no verified fact."""
        attempt = state["attempts"][-1]
        context = _context(state, attempt.code)
        failed = "; ".join(result.explanation for result in state.get("verification_results", []) if not result.satisfied)
        try:
            reply = _chat(llm, [{"role": "system", "content": DIAGNOSE_SYSTEM_PROMPT}, {"role": "user", "content": DIAGNOSE_PROMPT.format(failure=failed)}], 0.1)
        except LLMCallFailed as exc:
            return llm_unavailable(state, exc)
        claim = Claim(new_id("claim"), reply, "interpretation", "reasoning_model", context, attempt.evidence_ids, 0.8, "supported")
        return {**state, "claims": _append(state, "claims", claim), "ledger_events": _append(state, "ledger_events", _event(state, "diagnosed", "reasoning_model", context, {"attempt_id": attempt.attempt_id}))}

    def repair(state: AgentState) -> AgentState:
        """Propose repaired code using all failed attempts as context."""
        last = state["attempts"][-1]
        context = _context(state, last.code)
        retained = list(state["claims"])
        diagnosis = next((claim.statement for claim in reversed(retained) if claim.claim_type == "interpretation"), "No diagnosis available.")
        messages = [{"role": "system", "content": REPAIR_SYSTEM_PROMPT}, {"role": "user", "content": REPAIR_PROMPT.format(diagnosis=diagnosis, goal=state["normalized_goal"], history=_attempt_history(state["attempts"]))}]
        try:
            reply = _chat(llm, messages, 0.1)
            code, responses = _extract_code(llm, messages, reply, 0.1)
        except LLMCallFailed as exc:
            return llm_unavailable(state, exc)
        if code is None:
            return unparseable_output(state, responses)
        if _is_repeated_repair(code, state["attempts"]):
            return {**state, "done": True, "success": False, "completion_status": "stuck_in_loop", "final_answer": "Abstained: the proposed repair repeats a previously failed attempt.", "scratchpad": _append(state, "scratchpad", "[repair_loop_detected]\n" + "\n".join(responses))}
        prediction = Claim(new_id("claim"), "The proposed repair is predicted to satisfy the unsupported criteria when executed.", "prediction", "reasoning_model", context, last.evidence_ids, 0.5, "proposed", [claim.claim_id for claim in retained if claim.claim_type == "interpretation"])
        return {**state, "current_code": code, "claims": [*retained, prediction], "scratchpad": _append(state, "scratchpad", "[fix_code]\n" + "\n".join(responses))}

    def passthrough(state: AgentState) -> AgentState:
        """Preserve state between named graph phases without producing evidence."""
        return state

    for name, node in (
        ("interpret_goal", interpret_goal),
        ("plan", plan),
        ("generate_code", generate),
        ("execute", execute),
        ("collect_evidence", passthrough),
        ("verify", verify),
        ("constitutional_review", constitutional),
        ("diagnose", diagnose),
        ("propose_repair", repair),
        ("fix_code", passthrough),
    ):
        graph.add_node(name, node)
    graph.set_entry_point("interpret_goal")
    graph.add_conditional_edges("interpret_goal", lambda state: "finish" if state.get("done") else "plan", {"finish": END, "plan": "plan"})
    graph.add_conditional_edges("plan", lambda state: "finish" if state.get("done") else "generate_code", {"finish": END, "generate_code": "generate_code"})
    graph.add_conditional_edges("generate_code", lambda state: "finish" if state.get("done") else "execute", {"finish": END, "execute": "execute"})
    graph.add_edge("execute", "collect_evidence")
    graph.add_edge("collect_evidence", "verify")
    graph.add_edge("verify", "constitutional_review")
    graph.add_conditional_edges(
        "constitutional_review",
        lambda state: "finish" if state["done"] else "diagnose",
        {"finish": END, "diagnose": "diagnose"},
    )
    graph.add_conditional_edges("diagnose", lambda state: "finish" if state.get("done") else "propose_repair", {"finish": END, "propose_repair": "propose_repair"})
    graph.add_conditional_edges(
        "propose_repair",
        lambda state: "finish" if state.get("done") else "fix_code",
        {"finish": END, "fix_code": "fix_code"},
    )
    graph.add_edge("fix_code", "execute")
    return graph.compile()


def run_agent(goal: str, llm: LLMBackend, sandbox: Sandbox, max_iterations: int = 3) -> AgentState:
    """Run the graph with its compatible public signature and empty evidence ledger."""
    return build_graph(llm, sandbox).invoke(
        {
            "goal": goal,
            "max_iterations": max_iterations,
            "scratchpad": [],
            "attempts": [],
            "claims": [],
            "evidence": [],
            "ledger_events": [],
            "iteration": 0,
            "done": False,
            "sandbox_name": type(sandbox).__name__,
            "model_name": type(llm).__name__,
        }
    )
