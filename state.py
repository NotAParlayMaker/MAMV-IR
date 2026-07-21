"""Typed state passed between nodes in the LangGraph execution graph."""

from __future__ import annotations

from typing import TypedDict, List, Optional


class ExecutionAttempt(TypedDict):
    """Record of a single code-run attempt inside the sandbox."""

    code: str
    stdout: str
    stderr: str
    exit_code: int
    success: bool


class AgentState(TypedDict, total=False):
    # --- inputs ---
    goal: str  # The task the user wants solved
    max_iterations: int  # Hard cap on plan/code/fix loops

    # --- reasoning trace ---
    plan: str  # Kimi K3's out-loud chain-of-thought plan
    current_code: str  # Most recently generated code
    scratchpad: List[str]  # Running log of reasoning steps, for transparency

    # --- execution ---
    attempts: List[ExecutionAttempt]  # History of every sandbox run
    iteration: int  # Current loop count

    # --- termination ---
    done: bool  # Set True once the goal is verifiably solved or budget is spent
    success: bool  # Whether the loop ended in success or exhausted its budget
    final_answer: Optional[str]  # Human-readable summary of the outcome
