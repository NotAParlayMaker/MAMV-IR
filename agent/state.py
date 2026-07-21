"""Typed LangGraph state; structured informational records are authoritative."""
from typing import Any, TypedDict
from .informational.models import AcceptanceCriterion, Claim, Evidence, ExecutionAttempt, LedgerEvent, VerificationResult
class AgentState(TypedDict, total=False):
    goal: str; original_goal: str; normalized_goal: str; assumptions: list[str]; ambiguities: list[str]
    acceptance_criteria: list[AcceptanceCriterion]; required_evidence: list[str]; plan: str; current_code: str
    scratchpad: list[str]; claims: list[Claim]; evidence: list[Evidence]; verification_results: list[VerificationResult]
    ledger_events: list[LedgerEvent]; attempts: list[ExecutionAttempt]; iteration: int; max_iterations: int
    constitutional_violations: list[str]; final_decision: dict[str, Any] | None; completion_status: str
    done: bool; success: bool; final_answer: str | None
