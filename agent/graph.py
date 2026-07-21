"""MAMV-IR LangGraph: execution is evidence, never completion by itself."""
from __future__ import annotations
import hashlib, json, os
from dataclasses import asdict
from typing import Any
from langgraph.graph import END, StateGraph
from .informational.constitution import review
from .informational.ledger import chained_event
from .informational.models import (AcceptanceCriterion, Claim, Context, Evidence, ExecutionAttempt, LedgerEvent, VerificationResult, new_id, now)
from .llm import LLMBackend
from .prompts import CORRECT_JSON, GOAL_INTERPRETATION
from .sandbox import Sandbox
from .state import AgentState

CONFIDENCE_THRESHOLD = float(os.environ.get("MAMV_IR_CONFIDENCE_THRESHOLD", "0.80"))
SYSTEM_PROMPT = "You are a provider-agnostic reasoning model. Generate plans, code, and interpretations, but never represent unobserved facts as verified. Return Python in one ```python block when asked for code."

def _append(state: AgentState, key: str, item: Any) -> list[Any]: return [*state.get(key, []), item]
def _context(state: AgentState, code: str | None = None) -> Context:
    return Context(iteration=state.get("iteration", 0), goal=state.get("normalized_goal", state["goal"]), runtime="python", sandbox=state.get("sandbox_name"), model=state.get("model_name"), code_hash=hashlib.sha256(code.encode()).hexdigest() if code else None, environment_metadata={"pid": os.getpid()})
def _event(state: AgentState, event_type: str, actor: str, context: Context, payload: dict) -> LedgerEvent:
    prior=state.get("ledger_events", []); return chained_event(event_id=new_id("evt"), event_type=event_type, actor=actor, timestamp=now(), context=context, payload=payload, prior=prior[-1] if prior else None)
def _extract_code(reply: str) -> str:
    marker="```python"; start=reply.find(marker)
    if start < 0: return reply.strip()
    start += len(marker); end=reply.find("```", start); return reply[start if end < 0 else start:end].strip()
def _structured_goal(llm: LLMBackend, goal: str) -> tuple[dict, list[str]]:
    raw=[]
    messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":f"Goal: {goal}\n\n{GOAL_INTERPRETATION}"}]
    for retry in range(2):
        reply=llm.chat(messages); raw.append(reply)
        try:
            payload=json.loads(reply)
            if not isinstance(payload.get("acceptance_criteria"), list): raise ValueError("acceptance_criteria must be a list")
            return payload, raw
        except (json.JSONDecodeError, ValueError, TypeError): messages.append({"role":"user","content":CORRECT_JSON})
    return {"normalized_goal":goal,"assumptions":[],"ambiguities":["Goal interpretation unavailable; no unobserved result may be accepted."],"acceptance_criteria":[{"description":"Program exits without runtime error","verification_method":"exit_code","required":True,"expected_result":"0"},{"description":"Goal outcome is independently evidenced","verification_method":"stdout_contains","required":True,"expected_result":"Result:"}],"required_evidence":["exit_code","stdout"]}, raw

def build_graph(llm: LLMBackend, sandbox: Sandbox):
    graph=StateGraph(AgentState)
    def interpret_goal(state):
        payload, raw=_structured_goal(llm,state["goal"]); context=_context(state)
        criteria=[AcceptanceCriterion(criterion_id=f"criterion_{i+1}", **item, approval_status="approved" if item.get("verification_method") in {"exit_code", "stdout_contains", "not_timed_out"} else "proposed", approved_by="policy" if item.get("verification_method") in {"exit_code", "stdout_contains", "not_timed_out"} else None, approval_source="deterministic_low_risk_v1" if item.get("verification_method") in {"exit_code", "stdout_contains", "not_timed_out"} else None) for i,item in enumerate(payload["acceptance_criteria"])]
        evidence=list(state.get("evidence",[])); claims=list(state.get("claims",[])); ledger=list(state.get("ledger_events",[]))
        for response in raw:
            e=Evidence(new_id("ev"),"model_output",response,"reasoning_model",context,{"structured":False}); evidence.append(e)
        claim=Claim(new_id("claim"),"Goal interpretation was proposed.","interpretation","reasoning_model",context,[evidence[-1].evidence_id] if raw else [],0.5,"supported")
        claims.append(claim); ledger.append(_event(state,"goal_interpreted","reasoning_model",context,{"criteria":len(criteria)}))
        return {**state,"original_goal":state["goal"],"normalized_goal":payload["normalized_goal"],"assumptions":payload.get("assumptions",[]),"ambiguities":payload.get("ambiguities",[]),"acceptance_criteria":criteria,"required_evidence":payload.get("required_evidence",[]),"evidence":evidence,"claims":claims,"ledger_events":ledger}
    def plan(state):
        reply=llm.chat([{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":f"You are planning. Goal: {state['normalized_goal']}"}]); return {**state,"plan":reply,"scratchpad":_append(state,"scratchpad",f"[plan]\n{reply}")}
    def generate(state):
        reply=llm.chat([{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":f"Goal: {state['normalized_goal']}\nPlan: {state['plan']}\nWrite Python code and print Result:."}]); return {**state,"current_code":_extract_code(reply),"scratchpad":_append(state,"scratchpad",f"[generate_code]\n{reply}")}
    def execute(state):
        code=state["current_code"]; result=sandbox.run(code); context=_context(state,code); evidence=list(state.get("evidence",[]))
        created=[]
        for typ,value in (("stdout",result.stdout),("stderr",result.stderr),("exit_code",result.exit_code),("timeout",result.timed_out)):
            e=Evidence(new_id("ev"),typ,value,"sandbox",context,{"authoritative":True}); evidence.append(e); created.append(e)
        attempt=ExecutionAttempt(new_id("attempt"),code,result.stdout,result.stderr,result.exit_code,result.timed_out,context,[e.evidence_id for e in created])
        claims=list(state.get("claims",[]))
        if state.get("attempts"):
            claims=[*claims, *(Claim(new_id("claim"), c.statement, c.claim_type, c.observer, context, [*c.evidence_ids, *attempt.evidence_ids], c.confidence, "contradicted", [c.claim_id], [attempt.attempt_id], c.claim_id) for c in claims if c.claim_type == "prediction" and c.status == "proposed")]
        for e in created: claims.append(Claim(new_id("claim"),f"Sandbox observed {e.evidence_type}: {e.value!r}","observation","sandbox",context,[e.evidence_id],1.0,"verified"))
        ledger=_append(state,"ledger_events",_event(state,"executed","sandbox",context,{"attempt_id":attempt.attempt_id,"exit_code":result.exit_code,"timed_out":result.timed_out}))
        return {**state,"evidence":evidence,"claims":claims,"attempts":_append(state,"attempts",attempt),"ledger_events":ledger,"scratchpad":_append(state,"scratchpad",f"[execute] exit={result.exit_code}\nstdout: {result.stdout}\nstderr: {result.stderr}")}
    def verify(state):
        attempt=state["attempts"][-1]; results=[]; claims=list(state["claims"])
        for c in state["acceptance_criteria"]:
            supported=[]; contradictory=[]; uncertainty=[]; satisfied=False
            if c.verification_method == "exit_code": satisfied=attempt.exit_code == int(c.expected_result or 0)
            elif c.verification_method == "stdout_contains" and c.expected_result: satisfied=c.expected_result in attempt.stdout
            elif c.verification_method == "not_timed_out": satisfied=not attempt.timed_out
            else: uncertainty.append(f"Unsupported verification method: {c.verification_method!r}; no evaluator is implemented.")
            for eid in attempt.evidence_ids:
                e=next(e for e in state["evidence"] if e.evidence_id==eid)
                if (e.evidence_type=="exit_code" and c.verification_method=="exit_code") or (e.evidence_type=="stdout" and c.verification_method=="stdout_contains") or (e.evidence_type=="timeout" and c.verification_method=="not_timed_out"): (supported if satisfied else contradictory).append(eid)
            confidence=1.0 if satisfied else 0.0; results.append(VerificationResult(c.criterion_id,satisfied,confidence,"Direct sandbox evidence evaluated." if not uncertainty else uncertainty[0],"sandbox",supported,contradictory,uncertainty))
            claims.append(Claim(new_id("claim"),f"Criterion {c.criterion_id} {'is' if satisfied else 'is not'} satisfied.","inference","reasoning_model",_context(state,attempt.code),supported+contradictory,confidence,"supported" if satisfied else "contradicted",[]))
        return {**state,"verification_results":results,"claims":claims}
    def constitutional(state):
        iteration=state.get("iteration",0)+1; required=[r for r in state["verification_results"] if next(c for c in state["acceptance_criteria"] if c.criterion_id==r.criterion_id).required]
        all_verified=all(r.satisfied and r.confidence>=CONFIDENCE_THRESHOLD for r in required) and all(c.approval_status == "approved" for c in state["acceptance_criteria"] if c.required); contradicted=any(not r.satisfied for r in required)
        decision={"status":"verified" if all_verified else ("contradicted" if contradicted else "insufficient evidence"),"claim_ids":[c.claim_id for c in state["claims"] if c.status != "contradicted"],"evidence_ids":[e.evidence_id for e in state["evidence"]]}
        candidate={**state,"iteration":iteration,"final_decision":decision}; violations=review(candidate)
        success=bool(state["attempts"] and not state["attempts"][-1].timed_out and all_verified and not contradicted and not violations)
        done=success or iteration>=state.get("max_iterations",3)
        answer=state["attempts"][-1].stdout.strip() if success else (("Gave up after reaching max_iterations. " if done else "Verification rejected completion: ") + "; ".join(v.explanation for v in state["verification_results"] if not v.satisfied))
        return {**candidate,"constitutional_violations":violations,"success":success,"done":done,"completion_status":"verified" if success else ("exhausted" if done else decision["status"]),"final_answer":answer,"ledger_events":_append(state,"ledger_events",_event(state,"constitutional_review","governance",_context(state),{"success":success,"violations":violations}))}
    def diagnose(state):
        attempt=state["attempts"][-1]; context=_context(state,attempt.code); source=attempt.evidence_ids
        failed="; ".join(r.explanation for r in state.get("verification_results", []) if not r.satisfied)
        reply=llm.chat([{ "role":"system", "content":SYSTEM_PROMPT},{"role":"user","content":f"Diagnose failed criteria using evidence only: {failed}"}])
        claim=Claim(new_id("claim"),reply,"interpretation","reasoning_model",context,source,0.8,"supported")
        return {**state,"claims":_append(state,"claims",claim),"ledger_events":_append(state,"ledger_events",_event(state,"diagnosed","reasoning_model",context,{"attempt_id":attempt.attempt_id}))}
    def repair(state):
        last=state["attempts"][-1]; context=_context(state,last.code); retained=list(state["claims"]); diagnosis=next((c.statement for c in reversed(retained) if c.claim_type == "interpretation"), "No diagnosis available.")
        prompt=f"Diagnosis: {diagnosis}\nGoal: {state['normalized_goal']}\nCode:\n```python\n{last.code}\n```\nEvidence: stdout={last.stdout!r}; stderr={last.stderr!r}. Fix the code and return corrected code only."
        reply=llm.chat([{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt}]); code=_extract_code(reply); prediction=Claim(new_id("claim"),"The proposed repair is predicted to satisfy the unsupported criteria when executed.","prediction","reasoning_model",context,last.evidence_ids,0.5,"proposed",[c.claim_id for c in retained if c.claim_type=="interpretation"])
        return {**state,"current_code":code,"claims":[*retained,prediction],"scratchpad":_append(state,"scratchpad",f"[fix_code]\n{reply}")}
    for name,node in [("interpret_goal",interpret_goal),("plan",plan),("generate_code",generate),("execute",execute),("collect_evidence",lambda s:s),("verify",verify),("constitutional_review",constitutional),("diagnose",diagnose),("propose_repair",repair),("fix_code",lambda s:s)]: graph.add_node(name,node)
    graph.set_entry_point("interpret_goal"); graph.add_edge("interpret_goal","plan"); graph.add_edge("plan","generate_code"); graph.add_edge("generate_code","execute"); graph.add_edge("execute","collect_evidence"); graph.add_edge("collect_evidence","verify"); graph.add_edge("verify","constitutional_review")
    graph.add_conditional_edges("constitutional_review",lambda s:"finish" if s["done"] else "diagnose",{"finish":END,"diagnose":"diagnose"}); graph.add_edge("diagnose","propose_repair"); graph.add_edge("propose_repair","fix_code"); graph.add_edge("fix_code","execute")
    return graph.compile()
def run_agent(goal: str,llm: LLMBackend,sandbox: Sandbox,max_iterations: int=3) -> AgentState:
    return build_graph(llm,sandbox).invoke({"goal":goal,"max_iterations":max_iterations,"scratchpad":[],"attempts":[],"claims":[],"evidence":[],"ledger_events":[],"iteration":0,"done":False,"sandbox_name":type(sandbox).__name__,"model_name":type(llm).__name__})
