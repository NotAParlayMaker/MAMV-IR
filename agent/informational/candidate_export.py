"""Versioned, non-verdict export records for MAMV-Model candidates.

These records are deliberately separate from MAMV's verification records.  They
preserve provenance and disagreement without turning retrieval or model signals
into a finding.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
import json
from typing import Any, Literal

from .relativity import InferenceFrame

Derivation = Literal["retrieved", "extracted", "generated"]
GenerationStrategy = Literal[
    "direct", "structured_reasoning", "self_consistency", "self_refine", "multi_model_debate"
]


def _items(value: Any) -> tuple:
    return tuple(value or ())


def _unit_interval(value: float | None, name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1):
        raise ValueError(f"{name} must be between 0.0 and 1.0")


def _generated_density(derivation: Derivation, evidence_density: float | None) -> None:
    _unit_interval(evidence_density, "evidence_density")
    if derivation == "generated" and evidence_density is None:
        raise ValueError("generated candidates require evidence_density")
    if derivation != "generated" and evidence_density is not None:
        raise ValueError("evidence_density is only meaningful for generated candidates")


@dataclass(frozen=True)
class ClaimCandidate:
    """An unverified claim proposed for MAMV to assess."""
    claim_id: str
    text: str
    derivation: Derivation
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_density: float | None = None
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "source_ids", _items(self.source_ids))
        object.__setattr__(self, "limitations", _items(self.limitations))
        _generated_density(self.derivation, self.evidence_density)


@dataclass(frozen=True)
class EvidenceCandidate:
    """Candidate evidence, not an assertion that it supports a claim."""
    evidence_id: str
    text: str
    derivation: Derivation
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_density: float | None = None
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "source_ids", _items(self.source_ids))
        object.__setattr__(self, "limitations", _items(self.limitations))
        _generated_density(self.derivation, self.evidence_density)


@dataclass(frozen=True)
class ProposedEvidenceRelation:
    """A proposed relation for assessment; it is not support or verification."""
    claim_id: str
    evidence_id: str
    relation: str
    rationale: str | None = None


@dataclass(frozen=True)
class GenerationSample:
    sample_id: str
    text: str
    derivation: Derivation = "generated"
    evidence_density: float | None = None
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "limitations", _items(self.limitations))
        _generated_density(self.derivation, self.evidence_density)


@dataclass(frozen=True)
class CandidateAnswer:
    """One candidate answer with a bounded evidence scope.

    In ``fragmented`` mode, an export contains one of these per retrieved chunk;
    callers must not merge them into an integrated answer implicitly.
    """
    candidate_id: str
    text: str
    evidence_scope: tuple[str, ...]
    claim_candidates: tuple[ClaimCandidate, ...] = field(default_factory=tuple)
    evidence_candidates: tuple[EvidenceCandidate, ...] = field(default_factory=tuple)
    proposed_evidence_relations: tuple[ProposedEvidenceRelation, ...] = field(default_factory=tuple)
    model_stated_confidence: float | None = None
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "evidence_scope", _items(self.evidence_scope))
        object.__setattr__(self, "claim_candidates", _items(self.claim_candidates))
        object.__setattr__(self, "evidence_candidates", _items(self.evidence_candidates))
        object.__setattr__(self, "proposed_evidence_relations", _items(self.proposed_evidence_relations))
        object.__setattr__(self, "limitations", _items(self.limitations))
        _unit_interval(self.model_stated_confidence, "model_stated_confidence")
        claim_ids = {claim.claim_id for claim in self.claim_candidates}
        evidence_ids = {evidence.evidence_id for evidence in self.evidence_candidates}
        for relation in self.proposed_evidence_relations:
            if relation.claim_id not in claim_ids or relation.evidence_id not in evidence_ids:
                raise ValueError("proposed evidence relations must reference exported candidate IDs")


@dataclass(frozen=True)
class CandidateExport:
    """Load-bearing MAMV-Model export contract, schema version 1.

    A grounding gate may add critiques and lower ``model_stated_confidence``;
    this record intentionally has no mechanism for it to promote a candidate.
    """
    schema_version: Literal["mamv-model-candidate-export/v1"]
    inference_frame: InferenceFrame
    retrieval_mode: Literal["direct", "integrated", "fragmented"]
    generation_strategy: GenerationStrategy
    answers: tuple[CandidateAnswer, ...]
    generation_samples: tuple[GenerationSample, ...] = field(default_factory=tuple)
    selected_sample_id: str | None = None
    selection_rationale: str | None = None
    grounding_critiques: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "answers", _items(self.answers))
        object.__setattr__(self, "generation_samples", _items(self.generation_samples))
        object.__setattr__(self, "grounding_critiques", _items(self.grounding_critiques))
        object.__setattr__(self, "limitations", _items(self.limitations))
        if self.retrieval_mode not in {"direct", "integrated", "fragmented"}:
            raise ValueError("unsupported retrieval_mode")
        if self.generation_strategy not in {"direct", "structured_reasoning", "self_consistency", "self_refine", "multi_model_debate"}:
            raise ValueError("unsupported generation_strategy")
        if self.inference_frame.retrieval.integration_mode != self.retrieval_mode:
            raise ValueError("retrieval_mode must match the inference frame")
        if self.inference_frame.generation.strategy != self.generation_strategy:
            raise ValueError("generation_strategy must match the inference frame")
        if not self.answers:
            raise ValueError("a candidate export requires at least one answer")
        if self.retrieval_mode == "fragmented" and any(len(answer.evidence_scope) != 1 for answer in self.answers):
            raise ValueError("fragmented exports require one answer with one evidence scope per chunk")
        sample_ids = {sample.sample_id for sample in self.generation_samples}
        if self.selected_sample_id is not None and self.selected_sample_id not in sample_ids:
            raise ValueError("selected_sample_id must identify an exported generation sample")
        if self.generation_strategy in {"self_consistency", "self_refine", "multi_model_debate"} and not self.generation_samples:
            raise ValueError("multi-strategy exports must preserve their generation samples")


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def serialize_candidate_export(export: CandidateExport) -> str:
    return json.dumps(_plain(export), sort_keys=True, separators=(",", ":"))


def deserialize_candidate_export(payload: str) -> CandidateExport:
    from .answers import deserialize_inference_frame
    data = json.loads(payload)
    if not isinstance(data, dict) or data.get("schema_version") != "mamv-model-candidate-export/v1":
        raise ValueError("unsupported candidate export schema")
    allowed = {item.name for item in fields(CandidateExport)}
    data = {key: value for key, value in data.items() if key in allowed}
    data["inference_frame"] = deserialize_inference_frame(json.dumps(data["inference_frame"]))
    data["answers"] = tuple(CandidateAnswer(
        **{**answer,
           "claim_candidates": tuple(ClaimCandidate(**claim) for claim in answer.get("claim_candidates", ())),
           "evidence_candidates": tuple(EvidenceCandidate(**evidence) for evidence in answer.get("evidence_candidates", ())),
           "proposed_evidence_relations": tuple(ProposedEvidenceRelation(**relation) for relation in answer.get("proposed_evidence_relations", ())),
        }) for answer in data.get("answers", ()))
    data["generation_samples"] = tuple(GenerationSample(**sample) for sample in data.get("generation_samples", ()))
    return CandidateExport(**data)
