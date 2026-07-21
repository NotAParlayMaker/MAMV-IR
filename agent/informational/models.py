"""JSON-serializable records that form MAMV-IR's factual ledger."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

EvidenceType = Literal["stdout", "stderr", "exit_code", "test_result", "static_analysis_result", "generated_artifact", "human_feedback", "model_output"]
ClaimType = Literal["observation", "interpretation", "inference", "prediction", "normative_judgment"]
ClaimStatus = Literal["proposed", "supported", "disputed", "contradicted", "verified", "superseded", "insufficient_evidence"]

def new_id(prefix: str) -> str: return f"{prefix}_{uuid4().hex}"
def now() -> str: return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class Context:
    iteration: int; goal: str; runtime: str | None = None; sandbox: str | None = None
    model: str | None = None; code_hash: str | None = None; timestamp: str = field(default_factory=now)
    environment_metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Evidence:
    evidence_id: str; evidence_type: EvidenceType; value: Any; source: str; context: Context
    reliability: dict[str, Any] | None = None

@dataclass(frozen=True)
class Claim:
    claim_id: str; statement: str; claim_type: ClaimType; observer: str | None; context: Context | None
    evidence_ids: list[str] = field(default_factory=list); confidence: float = 0.0
    status: ClaimStatus = "proposed"; derived_from: list[str] = field(default_factory=list)
    contradicted_by: list[str] | None = None; supersedes: str | None = None

@dataclass(frozen=True)
class AcceptanceCriterion:
    criterion_id: str; description: str; verification_method: str; required: bool
    expected_result: str | None = None

@dataclass(frozen=True)
class VerificationResult:
    criterion_id: str; satisfied: bool; confidence: float; explanation: str; observer: str
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradictory_evidence_ids: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class LedgerEvent:
    event_id: str; event_type: str; actor: str; timestamp: str; context: Context; payload: dict[str, Any]
    previous_event_id: str | None = None

@dataclass(frozen=True)
class ExecutionAttempt:
    attempt_id: str; code: str; stdout: str; stderr: str; exit_code: int; timed_out: bool; context: Context
    evidence_ids: list[str]

    @property
    def success(self) -> bool:
        """Compatibility view: process completion, not task completion."""
        return self.exit_code == 0 and not self.timed_out

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

def jsonable(value: Any) -> Any:
    return asdict(value) if hasattr(value, "__dataclass_fields__") else value
