"""Authority boundaries enforced by the governance layer."""
from .models import Claim
RUNTIME_TYPES = {"stdout", "stderr", "exit_code"}

def can_verify_claim(claim: Claim) -> bool:
    """Models may interpret, but only authorized observers verify facts."""
    if claim.status != "verified": return True
    if claim.claim_type == "observation": return claim.observer in {"sandbox", "test_runner", "static_analyzer"}
    return claim.observer != "reasoning_model" or bool(claim.evidence_ids or claim.derived_from)

def observer_for_evidence(evidence_type: str) -> str:
    return {"test_result": "test_runner", "static_analysis_result": "static_analyzer"}.get(evidence_type, "sandbox")
