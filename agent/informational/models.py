"""Immutable, provenance-bearing records for MAMV-IR.

Confidence is not proof: it is meaningful only with provenance-backed
verification, and is always constrained to the inclusive range 0.0..1.0.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping
from uuid import uuid4

EvidenceType = Literal["stdout", "stderr", "exit_code", "timeout", "test_result", "static_analysis_result", "generated_artifact", "human_feedback", "model_output", "model_output_unparseable", "llm_call_failure"]
ClaimType = Literal["observation", "interpretation", "inference", "prediction", "normative_judgment"]
ClaimStatus = Literal["proposed", "supported", "disputed", "contradicted", "verified", "superseded", "insufficient_evidence"]
ApprovalStatus = Literal["proposed", "approved", "rejected"]

def new_id(prefix: str) -> str: return f"{prefix}_{uuid4().hex}"
def now() -> str: return datetime.now(timezone.utc).isoformat()
def _mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]: return MappingProxyType(dict(value or {}))
def _tuple(value: Any) -> tuple: return tuple(value or ())
def _confidence(value: float) -> None:
    if not 0.0 <= value <= 1.0: raise ValueError(f"confidence must be between 0.0 and 1.0, got {value!r}")

@dataclass(frozen=True)
class Context:
    iteration: int; goal: str; runtime: str | None = None; sandbox: str | None = None; model: str | None = None; code_hash: str | None = None; timestamp: str = field(default_factory=now)
    environment_metadata: Mapping[str, Any] = field(default_factory=dict)
    def __post_init__(self): object.__setattr__(self, "environment_metadata", _mapping(self.environment_metadata))

@dataclass(frozen=True)
class Evidence:
    evidence_id: str; evidence_type: EvidenceType; value: Any; source: str; context: Context
    reliability: Mapping[str, Any] | None = None
    def __post_init__(self):
        if self.reliability is not None: object.__setattr__(self, "reliability", _mapping(self.reliability))

@dataclass(frozen=True)
class Claim:
    claim_id: str; statement: str; claim_type: ClaimType; observer: str | None; context: Context | None
    evidence_ids: tuple[str, ...] = field(default_factory=tuple); confidence: float = 0.0; status: ClaimStatus = "proposed"
    derived_from: tuple[str, ...] = field(default_factory=tuple); contradicted_by: tuple[str, ...] | None = None; supersedes: str | None = None
    def __post_init__(self):
        object.__setattr__(self, "evidence_ids", _tuple(self.evidence_ids)); object.__setattr__(self, "derived_from", _tuple(self.derived_from))
        if self.contradicted_by is not None: object.__setattr__(self, "contradicted_by", _tuple(self.contradicted_by))
        _confidence(self.confidence)

@dataclass(frozen=True)
class AcceptanceCriterion:
    criterion_id: str; description: str; verification_method: str; required: bool; expected_result: str | None = None
    proposed_by: str | None = "reasoning_model"; approved_by: str | None = None; approval_status: ApprovalStatus = "proposed"; approval_source: str | None = None

@dataclass(frozen=True)
class VerificationResult:
    criterion_id: str; satisfied: bool; confidence: float; explanation: str; observer: str
    supporting_evidence_ids: tuple[str, ...] = field(default_factory=tuple); contradictory_evidence_ids: tuple[str, ...] = field(default_factory=tuple); uncertainties: tuple[str, ...] = field(default_factory=tuple)
    def __post_init__(self):
        object.__setattr__(self, "supporting_evidence_ids", _tuple(self.supporting_evidence_ids)); object.__setattr__(self, "contradictory_evidence_ids", _tuple(self.contradictory_evidence_ids)); object.__setattr__(self, "uncertainties", _tuple(self.uncertainties)); _confidence(self.confidence)

@dataclass(frozen=True)
class LedgerEvent:
    event_id: str; event_type: str; actor: str; timestamp: str; context: Context; payload: Mapping[str, Any]
    previous_event_id: str | None = None; previous_event_hash: str | None = None; event_hash: str | None = None
    def __post_init__(self): object.__setattr__(self, "payload", _mapping(self.payload))

@dataclass(frozen=True)
class ExecutionAttempt:
    attempt_id: str; code: str; stdout: str; stderr: str; exit_code: int; timed_out: bool; context: Context; evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    def __post_init__(self): object.__setattr__(self, "evidence_ids", _tuple(self.evidence_ids))
    @property
    def success(self) -> bool: return self.exit_code == 0 and not self.timed_out
    def __getitem__(self, key: str) -> Any: return getattr(self, key)

def jsonable(value: Any) -> Any: return asdict(value) if hasattr(value, "__dataclass_fields__") else value
