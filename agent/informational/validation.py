"""Shared record validation used as a defensive second line for governance."""
from .models import Claim, VerificationResult

def validate_confidence(value: float) -> None:
    """Reject invalid confidence rather than hiding producer errors by clamping."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {value!r}")
def validate_record_confidence(record: Claim | VerificationResult) -> None:
    validate_confidence(record.confidence)
