"""Constitutional invariants for converting information into a decision."""
from .models import Claim
from .observers import can_verify_claim

def review(state: dict) -> list[str]:
    violations: list[str] = []
    for claim in state.get("claims", []):
        if not claim.observer: violations.append(f"Claim {claim.claim_id} has no observer.")
        if not claim.context: violations.append(f"Claim {claim.claim_id} has no context.")
        if claim.claim_type != "observation" and not (claim.evidence_ids or claim.derived_from):
            violations.append(f"Non-observation claim {claim.claim_id} lacks evidence or parent claims.")
        if not can_verify_claim(claim): violations.append(f"Claim {claim.claim_id} exceeds observer authority.")
        if claim.supersedes and not any(c.claim_id == claim.supersedes for c in state.get("claims", [])):
            violations.append(f"Claim {claim.claim_id} supersedes missing claim {claim.supersedes}.")
    required = [c.criterion_id for c in state.get("acceptance_criteria", []) if c.required]
    evaluated = {r.criterion_id for r in state.get("verification_results", [])}
    for criterion_id in required:
        if criterion_id not in evaluated: violations.append(f"Required criterion {criterion_id} was not explicitly evaluated.")
    if state.get("final_decision") and not state["final_decision"].get("claim_ids"):
        violations.append("Final decision does not cite claims.")
    if state.get("final_decision") and not state["final_decision"].get("evidence_ids"):
        violations.append("Final decision does not cite evidence.")
    return violations
