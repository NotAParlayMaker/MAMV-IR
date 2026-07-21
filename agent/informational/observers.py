"""Explicit authority policy; evidence source, not confidence, grants authority."""
from dataclasses import dataclass
from typing import Sequence
from .models import Claim, Evidence
@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool; explanation: str; matched_rule: str; relevant_evidence_ids: tuple[str, ...] = ()
_RUNTIME={"stdout","stderr","exit_code","timeout"}

def authorize_claim_verification(claim: Claim, evidence: Sequence[Evidence], verification_method: str | None = None) -> AuthorizationResult:
    relevant=tuple(e.evidence_id for e in evidence if e.evidence_id in claim.evidence_ids)
    types={e.evidence_type for e in evidence if e.evidence_id in relevant}
    if claim.status != "verified": return AuthorizationResult(True,"Claim is not requesting verified status.","non_verified",relevant)
    if claim.observer == "sandbox":
        ok=claim.claim_type == "observation" and types and types <= _RUNTIME
        return AuthorizationResult(ok,"sandbox may verify runtime observation evidence only." if not ok else "sandbox runtime-observation authority matched.","sandbox_runtime",relevant)
    if claim.observer == "test_runner":
        ok=claim.claim_type == "observation" and types == {"test_result"}
        return AuthorizationResult(ok,"test_runner may verify test_result evidence only." if not ok else "test runner authority matched.","test_runner",relevant)
    if claim.observer == "static_analyzer":
        ok=claim.claim_type == "observation" and types == {"static_analysis_result"}
        return AuthorizationResult(ok,"static_analyzer may verify static_analysis_result evidence only." if not ok else "static analyzer authority matched.","static_analyzer",relevant)
    if claim.observer == "human":
        ok=types == {"human_feedback"}
        return AuthorizationResult(ok,"human verification requires explicit human_feedback evidence." if not ok else "human evidence authority matched.","human_feedback",relevant)
    if claim.observer == "reasoning_model": return AuthorizationResult(False,"reasoning_model may propose interpretations but may not independently verify unobserved facts.","reasoning_model_no_verification",relevant)
    return AuthorizationResult(False,"observer has no declared verification authority.","unknown_observer",relevant)

def can_verify_claim(claim: Claim) -> bool:
    """Compatibility wrapper for callers that do not yet provide evidence."""
    return authorize_claim_verification(claim, (), None).allowed

def observer_for_evidence(evidence_type: str) -> str:
    return {"test_result":"test_runner","static_analysis_result":"static_analyzer","human_feedback":"human"}.get(evidence_type,"sandbox")
