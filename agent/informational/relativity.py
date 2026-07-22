"""First-class informational-frame governance primitives.

Frames name the bounded conditions under which verification is meaningful; they
are not assertions of context-free truth.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence


def _freeze(value: Mapping[str, str] | None) -> Mapping[str, str]:
    return MappingProxyType(dict(value or {}))
def _items(value: Sequence[str] | None) -> tuple[str, ...]: return tuple(value or ())
def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None: raise ValueError(f"{name} must be timezone-aware")
def _canonical(value: Any) -> str:
    if hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
def _id(prefix: str, payload: Mapping[str, Any]) -> str: return f"{prefix}_{sha256(_canonical(payload).encode()).hexdigest()[:24]}"

class ClaimScope(str, Enum):
    LOCAL="local"; EXECUTION="execution"; ARTIFACT="artifact"; RUN="run"; ENVIRONMENT="environment"; TEMPORAL="temporal"; GENERAL="general"
class RelativeVerificationStatus(str, Enum):
    SUPPORTED="supported"; CONTRADICTED="contradicted"; INSUFFICIENT_EVIDENCE="insufficient_evidence"; UNAUTHORIZED="unauthorized"; AMBIGUOUS="ambiguous"; STALE="stale"; NOT_APPLICABLE="not_applicable"

@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str; artifact_type: str; version: str; content_hash: str; parent_version: str | None; created_at: datetime
    def __post_init__(self): _aware(self.created_at,"created_at")

@dataclass(frozen=True)
class InformationalFrame:
    frame_id: str; context_id: str; observer_id: str; observer_type: str; authority_policy_id: str; verification_method: str
    evidence_scope: tuple[str,...]; criterion_ids: tuple[str,...]; assumption_ids: tuple[str,...]; artifact_versions: Mapping[str,str]
    valid_at: datetime; created_at: datetime; parent_frame_id: str|None=None; purpose: str|None=None; limitations: tuple[str,...]=field(default_factory=tuple); frame_origin: str="recorded"
    def __post_init__(self):
        for n in ("evidence_scope","criterion_ids","assumption_ids","limitations"): object.__setattr__(self,n,_items(getattr(self,n)))
        object.__setattr__(self,"artifact_versions",_freeze(self.artifact_versions)); _aware(self.valid_at,"valid_at"); _aware(self.created_at,"created_at")
        if not all((self.context_id,self.observer_id,self.observer_type,self.authority_policy_id,self.verification_method)): raise ValueError("informational frame requires context, observer, policy, and method")
    def canonical(self) -> str: return _canonical(self)

@dataclass(frozen=True)
class RelativeVerificationResult:
    verification_id: str; claim_id: str; frame_id: str; status: RelativeVerificationStatus; observer_id: str; method: str; authority_decision: str
    supporting_evidence_ids: tuple[str,...]; contradicting_evidence_ids: tuple[str,...]; unresolved_evidence_ids: tuple[str,...]; criterion_ids: tuple[str,...]; confidence: float; valid_at: datetime; expires_at: datetime|None; limitations: tuple[str,...]; explanation: str
    def __post_init__(self):
        for n in ("supporting_evidence_ids","contradicting_evidence_ids","unresolved_evidence_ids","criterion_ids","limitations"): object.__setattr__(self,n,_items(getattr(self,n)))
        _aware(self.valid_at,"valid_at")
        if self.expires_at: _aware(self.expires_at,"expires_at")
        if not 0 <= self.confidence <= 1: raise ValueError("confidence must be between 0.0 and 1.0")
        if self.status is RelativeVerificationStatus.UNAUTHORIZED and self.authority_decision == "authorized": raise ValueError("unauthorized result requires an unauthorized authority decision")

@dataclass(frozen=True)
class FrameTransformation:
    transformation_id: str; source_frame_id: str; target_frame_id: str; transformation_type: str; changed_fields: tuple[str,...]; preserved_claim_ids: tuple[str,...]; invalidated_claim_ids: tuple[str,...]; requires_reverification: bool; explanation: str
    def __post_init__(self):
        for n in ("changed_fields","preserved_claim_ids","invalidated_claim_ids"): object.__setattr__(self,n,_items(getattr(self,n)))

@dataclass(frozen=True)
class InformationalPerspective:
    perspective_id: str; frame_id: str; claim_id: str; interpretation: str; status: RelativeVerificationStatus; evidence_ids: tuple[str,...]; limitations: tuple[str,...]
    def __post_init__(self): object.__setattr__(self,"evidence_ids",_items(self.evidence_ids)); object.__setattr__(self,"limitations",_items(self.limitations))

@dataclass(frozen=True)
class CompletionDecision:
    decision_id: str; frame_id: str; status: str; required_criterion_ids: tuple[str,...]; verification_ids: tuple[str,...]; constitutional_review_id: str; unresolved_claim_ids: tuple[str,...]; limitations: tuple[str,...]; decided_at: datetime
    def __post_init__(self):
        for n in ("required_criterion_ids","verification_ids","unresolved_claim_ids","limitations"): object.__setattr__(self,n,_items(getattr(self,n)))
        _aware(self.decided_at,"decided_at")

@dataclass(frozen=True)
class ObserverCapability:
    observer_type: str; allowed_evidence_types: tuple[str,...]; allowed_claim_types: tuple[str,...]; allowed_methods: tuple[str,...]; maximum_scope: ClaimScope; prohibited_assertions: tuple[str,...]

CAPABILITIES={
 "sandbox":ObserverCapability("sandbox",("stdout","stderr","exit_code","timeout"),("observation",),("exit_code","stdout_contains","not_timed_out"),ClaimScope.EXECUTION,("semantic correctness","task completion","security")),
 "test_runner":ObserverCapability("test_runner",("test_result",),("observation",),("tests_pass",),ClaimScope.ARTIFACT,("complete correctness","security")),
 "static_analyzer":ObserverCapability("static_analyzer",("static_analysis_result",),("observation",),("passes_static_analysis",),ClaimScope.ARTIFACT,("runtime behavior",)),
 "reasoning_model":ObserverCapability("reasoning_model",("model_output",),("interpretation","inference","prediction"),(),ClaimScope.LOCAL,("observed runtime evidence","task completion")),
}

def build_informational_frame(*, context, observer: str, authority_policy: str, verification_method: str, evidence_scope=(), criteria=(), assumptions=(), artifact_versions=None, parent_frame=None, purpose=None, limitations=(), valid_at=None) -> InformationalFrame:
    if observer not in CAPABILITIES and observer not in {"human","constitutional_reviewer"}: raise ValueError(f"unknown observer: {observer}")
    created=valid_at or datetime.now(timezone.utc); context_id=getattr(context,"context_id",None) or f"context_{sha256(_canonical(context).encode()).hexdigest()[:24]}"
    payload={"context_id":context_id,"observer":observer,"policy":authority_policy,"method":verification_method,"evidence_scope":sorted(evidence_scope),"criteria":sorted(getattr(c,"criterion_id",c) for c in criteria),"assumptions":sorted(assumptions),"artifacts":dict(sorted((artifact_versions or {}).items())),"parent":getattr(parent_frame,"frame_id",None),"purpose":purpose}
    return InformationalFrame(_id("frame",payload),context_id,observer,observer,authority_policy,verification_method,tuple(payload["evidence_scope"]),tuple(payload["criteria"]),tuple(payload["assumptions"]),payload["artifacts"],created,created,getattr(parent_frame,"frame_id",None),purpose,tuple(limitations))

def derive_frame(source: InformationalFrame, *, transformation_type: str, changed_fields=(), **changes):
    data={name:getattr(source,name) for name in InformationalFrame.__dataclass_fields__ if name not in {"frame_id","parent_frame_id","created_at","valid_at","frame_origin"}}
    data.update(changes); target=build_informational_frame(context=type("ContextIdentity",(),{"context_id":data["context_id"]})(),observer=data["observer_id"],authority_policy=data["authority_policy_id"],verification_method=data["verification_method"],evidence_scope=data["evidence_scope"],criteria=data["criterion_ids"],assumptions=data["assumption_ids"],artifact_versions=data["artifact_versions"],parent_frame=source,purpose=data.get("purpose"),limitations=data.get("limitations"))
    changed=tuple(changed_fields); return target, FrameTransformation(_id("transform",{"source":source.frame_id,"target":target.frame_id,"type":transformation_type}),source.frame_id,target.frame_id,transformation_type,changed,(),(),bool(changed),"Frame derivation is conservative; changed conditions require re-verification.")
def compare_contexts(left,right) -> tuple[str,...]:
    keys=("goal","code_hash","version","content_hash","source")
    return tuple(k for k in keys if getattr(left,k,None)!=getattr(right,k,None))
def is_context_compatible(left,right) -> bool: return not compare_contexts(left,right)
def requires_reverification(source,target) -> bool: return source.context_id != target.context_id or source.artifact_versions != target.artifact_versions or source.criterion_ids != target.criterion_ids or source.authority_policy_id != target.authority_policy_id or source.evidence_scope != target.evidence_scope
def is_verification_current(result, frame, *, at=None) -> bool: return result.frame_id == frame.frame_id and not (result.expires_at and (at or datetime.now(timezone.utc)) > result.expires_at)
def mark_stale_results(results, frame): return tuple(r for r in results if not is_verification_current(r,frame))
def find_superseded_results(results, frame): return mark_stale_results(results,frame)
def classify_cross_frame_relation(left,right, left_scope=None,right_scope=None) -> str:
    if left_scope and right_scope and left_scope != right_scope: return "scope_distinct"
    if left.frame_id==right.frame_id and left.status==right.status:return "equivalent"
    if left.status==RelativeVerificationStatus.CONTRADICTED and right.status==RelativeVerificationStatus.SUPPORTED:return "contradicts"
    return "incomparable"
def collect_perspectives(results): return tuple(InformationalPerspective(_id("perspective",{"verification":r.verification_id}),r.frame_id,r.claim_id,r.explanation,r.status,r.supporting_evidence_ids+r.contradicting_evidence_ids,r.limitations) for r in results)
def compare_perspectives(left,right): return "compatible" if left.status==right.status else ("conflicting" if left.frame_id==right.frame_id else "incomparable")
def find_cross_frame_conflicts(perspectives): return tuple((a.perspective_id,b.perspective_id) for i,a in enumerate(perspectives) for b in perspectives[i+1:] if compare_perspectives(a,b)=="conflicting")


# Answer-inference frames are intentionally separate from governance frames above.
# The former describe bounded model output; the latter describe verification authority.
@dataclass(frozen=True)
class ModelArtifactReference:
    model_id: str
    revision: str | None = None
    adapter_id: str | None = None
    adapter_revision: str | None = None
    tokenizer_id: str | None = None
    tokenizer_revision: str | None = None
    local_content_hash: str | None = None

@dataclass(frozen=True)
class RetrievalFrame:
    query: str
    retriever_type: str | None = None
    requested_top_k: int | None = None
    selected_source_ids: tuple[str, ...] = field(default_factory=tuple)
    dropped_source_ids: tuple[str, ...] = field(default_factory=tuple)
    integration_mode: str = "direct"
    max_tokens: int | None = None
    used_tokens: int | None = None
    def __post_init__(self):
        object.__setattr__(self, "selected_source_ids", _items(self.selected_source_ids))
        object.__setattr__(self, "dropped_source_ids", _items(self.dropped_source_ids))

@dataclass(frozen=True)
class GenerationFrame:
    strategy: str = "direct"
    temperature: float | None = None
    top_p: float | None = None
    max_new_tokens: int | None = None
    num_samples: int | None = None
    max_refine_iterations: int | None = None
    require_grounding: bool = False
    def __post_init__(self):
        for name in ("temperature", "top_p"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0.0 and 1.0")

@dataclass(frozen=True)
class InferenceFrame:
    frame_id: str
    question_hash: str
    document_hash: str | None
    context_hash: str
    model: ModelArtifactReference
    retrieval: RetrievalFrame
    generation: GenerationFrame
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = "1970-01-01T00:00:00+00:00"
    parent_frame_id: str | None = None
    def __post_init__(self):
        object.__setattr__(self, "assumptions", _items(self.assumptions))
        object.__setattr__(self, "limitations", _items(self.limitations))
        _parse_timestamp(self.created_at)
    def canonical(self) -> str: return _canonical(self)

@dataclass(frozen=True)
class InferenceFrameTransition:
    source_frame_id: str
    target_frame_id: str
    reason: str
    changed_fields: tuple[str, ...] = field(default_factory=tuple)
    answer_changed: bool = False
    grounding_changed: bool = False
    explanation: str = ""
    def __post_init__(self): object.__setattr__(self, "changed_fields", _items(self.changed_fields))

def _hash_text(value: str | None) -> str | None:
    return sha256(value.encode("utf-8")).hexdigest() if value is not None else None

def _parse_timestamp(value: str) -> datetime:
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error: raise ValueError("created_at must be an ISO-8601 timestamp") from error
    _aware(parsed, "created_at"); return parsed

def build_inference_frame(*, question: str, context: str = "", document: str | None = None, model_id: str = "unknown", model_revision: str | None = None, adapter_id: str | None = None, adapter_revision: str | None = None, tokenizer_id: str | None = None, tokenizer_revision: str | None = None, local_content_hash: str | None = None, retriever_type: str | None = None, requested_top_k: int | None = None, selected_source_ids=(), dropped_source_ids=(), integration_mode: str = "direct", max_tokens: int | None = None, used_tokens: int | None = None, strategy: str = "direct", temperature: float | None = None, top_p: float | None = None, max_new_tokens: int | None = None, num_samples: int | None = None, max_refine_iterations: int | None = None, require_grounding: bool = False, assumptions=(), limitations=(), created_at: str = "1970-01-01T00:00:00+00:00", parent_frame_id: str | None = None) -> InferenceFrame:
    """Create a deterministic, secret-free description of an answer's conditions."""
    _parse_timestamp(created_at)
    limits = list(limitations)
    if model_revision is None and "Model revision was not pinned; exact reproduction is not guaranteed." not in limits:
        limits.append("Model revision was not pinned; exact reproduction is not guaranteed.")
    retrieval = RetrievalFrame(question, retriever_type, requested_top_k, tuple(selected_source_ids), tuple(dropped_source_ids), integration_mode, max_tokens, used_tokens)
    generation = GenerationFrame(strategy, temperature, top_p, max_new_tokens, num_samples, max_refine_iterations, require_grounding)
    model = ModelArtifactReference(model_id, model_revision, adapter_id, adapter_revision, tokenizer_id, tokenizer_revision, local_content_hash)
    payload = {"question_hash": _hash_text(question), "document_hash": _hash_text(document), "context_hash": _hash_text(context) or _hash_text(""), "model": model, "retrieval": retrieval, "generation": generation, "assumptions": tuple(assumptions), "limitations": tuple(limits), "parent_frame_id": parent_frame_id}
    return InferenceFrame(_id("inference", payload), **payload, created_at=created_at)

def derive_inference_frame(source: InferenceFrame, *, reason: str, changed_fields=(), answer_changed: bool = False, grounding_changed: bool = False, explanation: str = "", **changes) -> tuple[InferenceFrame, InferenceFrameTransition]:
    data = {name: getattr(source, name) for name in InferenceFrame.__dataclass_fields__ if name not in {"frame_id", "parent_frame_id"}}
    data.update(changes); data["parent_frame_id"] = source.frame_id
    payload = {name: data[name] for name in ("question_hash", "document_hash", "context_hash", "model", "retrieval", "generation", "assumptions", "limitations", "created_at", "parent_frame_id")}
    # Preserve hashes when deriving; frame id is still deterministic over all conditions.
    target = InferenceFrame(_id("inference", {k:v for k,v in payload.items() if k != "created_at"}), **payload)
    return target, InferenceFrameTransition(source.frame_id, target.frame_id, reason, tuple(changed_fields), answer_changed, grounding_changed, explanation)
