"""The core Moonshot-Agent-X execution loop, built as a LangGraph StateGraph.

Flow:

    plan -> generate_code -> execute -> evaluate --success--> finish
                                  ^                  |
                                  |               failure
                                  |                  v
                                  +------------ fix_code
                                      (until max_iterations, then finish)

Every node is a small, pure-ish function over AgentState so the loop stays
inspectable: at any point you can print state["scratchpad"] and see exactly
what Kimi K3 was told, what it planned, what it wrote, and why it did or
didn't work.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from .llm import LLMBackend
from .sandbox import Sandbox
from .state import AgentState, ExecutionAttempt


SYSTEM_PROMPT = (
    "You are Kimi K3 acting as an autonomous coding agent. You reason step "
    "by step out loud before acting, write correct self-contained Python, "
    "and fix your own bugs when the sandbox reports an error. Always place "
    "runnable code in a single ```python fenced block."
)


def build_graph(llm: LLMBackend, sandbox: Sandbox):
    graph = StateGraph(AgentState)

    def plan_node(state: AgentState) -> AgentState:
        prompt = (
            f"You are planning how to solve the following goal.\n"
            f"Goal: {state['goal']}\n\n"
            "Think step by step and lay out a short numbered plan before "
            "any code is written. Prefix your plan with 'PLAN:'."
        )
        reply = llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        scratchpad = state.get("scratchpad", [])
        scratchpad.append(f"[plan]\n{reply}")
        return {**state, "plan": reply, "scratchpad": scratchpad}

    def generate_code_node(state: AgentState) -> AgentState:
        prompt = (
            f"Goal: {state['goal']}\n\n"
            f"Your plan:\n{state['plan']}\n\n"
            "Write Python code that carries out this plan and prints its "
            "final result clearly (prefix the printed line with 'Result:'). "
            "Return only a single ```python fenced code block."
        )
        reply = llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        code = _extract_code(reply)
        scratchpad = state.get("scratchpad", [])
        scratchpad.append(f"[generate_code]\n{reply}")
        return {**state, "current_code": code, "scratchpad": scratchpad}

    def execute_node(state: AgentState) -> AgentState:
        code = state["current_code"]
        result = sandbox.run(code)
        attempt: ExecutionAttempt = {
            "code": code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "success": result.success,
        }
        attempts = state.get("attempts", [])
        attempts.append(attempt)
        scratchpad = state.get("scratchpad", [])
        scratchpad.append(
            f"[execute] exit={result.exit_code} success={result.success}\n"
            f"stdout: {result.stdout.strip()[:500]}\n"
            f"stderr: {result.stderr.strip()[:500]}"
        )
        return {**state, "attempts": attempts, "scratchpad": scratchpad}

    def evaluate_node(state: AgentState) -> AgentState:
        last = state["attempts"][-1]
        iteration = state.get("iteration", 0) + 1
        if last["success"]:
            return {
                **state,
                "iteration": iteration,
                "done": True,
                "success": True,
                "final_answer": last["stdout"].strip(),
            }
        if iteration >= state.get("max_iterations", 3):
            return {
                **state,
                "iteration": iteration,
                "done": True,
                "success": False,
                "final_answer": (
                    "Gave up after reaching max_iterations. Last error:\n"
                    + last["stderr"].strip()
                ),
            }
        return {**state, "iteration": iteration, "done": False}

    def fix_code_node(state: AgentState) -> AgentState:
        last = state["attempts"][-1]
        prompt = (
            f"Goal: {state['goal']}\n\n"
            f"This code you wrote failed:\n```python\n{last['code']}```\n\n"
            f"It produced this traceback:\n{last['stderr']}\n\n"
            "Read the traceback, identify the specific bug, and return a "
            "corrected, complete version of the script in a single "
            "```python fenced code block. Do not explain outside the block."
        )
        reply = llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        code = _extract_code(reply)
        scratchpad = state.get("scratchpad", [])
        scratchpad.append(f"[fix_code] iteration={state['iteration']}\n{reply}")
        return {**state, "current_code": code, "scratchpad": scratchpad}

    graph.add_node("plan", plan_node)
    graph.add_node("generate_code", generate_code_node)
    graph.add_node("execute", execute_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("fix_code", fix_code_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "generate_code")
    graph.add_edge("generate_code", "execute")
    graph.add_edge("execute", "evaluate")

    def route_after_evaluate(state: AgentState) -> str:
        if state["done"]:
            return "finish"
        return "fix_code"

    graph.add_conditional_edges(
        "evaluate", route_after_evaluate, {"finish": END, "fix_code": "fix_code"}
    )
    graph.add_edge("fix_code", "execute")

    return graph.compile()


def _extract_code(reply: str) -> str:
    """Pulls the contents of the first ```python fenced block out of a
    model reply. Falls back to the raw reply if no fence is found, since
    some backends occasionally omit the fence for very short snippets."""
    marker = "```python"
    start = reply.find(marker)
    if start == -1:
        return reply.strip()
    start += len(marker)
    end = reply.find("```", start)
    if end == -1:
        return reply[start:].strip()
    return reply[start:end].strip()


def run_agent(goal: str, llm: LLMBackend, sandbox: Sandbox, max_iterations: int = 3) -> AgentState:
    """Convenience entry point: builds the graph and runs it to completion."""
    app = build_graph(llm, sandbox)
    initial_state: AgentState = {
        "goal": goal,
        "max_iterations": max_iterations,
        "scratchpad": [],
        "attempts": [],
        "iteration": 0,
        "done": False,
    }
    final_state = app.invoke(initial_state)
    return final_state
