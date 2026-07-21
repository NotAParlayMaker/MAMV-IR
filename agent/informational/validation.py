"""Shared record validation used as a defensive second line for governance."""
from .models import Claim, VerificationResult

def validate_confidence(value: float) -> None:
    """Reject invalid confidence rather than hiding producer errors by clamping."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {value!r}")
def validate_record_confidence(record: Claim | VerificationResult) -> None:
    validate_confidence(record.confidence)


def validate_claim_requirements(claim: Claim) -> tuple[str, ...]:
    """Return standalone governance requirement failures for one claim."""
    failures = []
    if not claim.observer:
        failures.append("missing_observer")
    if not claim.context:
        failures.append("missing_context")
    if claim.claim_type != "observation" and not (claim.evidence_ids or claim.derived_from):
        failures.append("missing_support")
    return tuple(failures)
