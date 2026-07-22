"""Bounded answer records and safe persistence for answer inference frames.

This module records concise reasoning summaries only.  It intentionally does not
store unrestricted prompts or private chain-of-thought.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field, fields, is_dataclass
import json
from typing import Any
from .relativity import InferenceFrame


def _confidence(value: float | None, name: str) -> None:
    if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1):
        raise ValueError(f"{name} must be between 0.0 and 1.0")

@dataclass(frozen=True)
class ConfidenceSignals:
    """Separate signals; none alone establishes correctness."""
    stated: float | None = None
    consensus: float | None = None
    grounding: float | None = None
    retrieval_coverage: float | None = None
    coherence: float | None = None
    def __post_init__(self):
        for name in ("stated", "consensus", "grounding", "retrieval_coverage", "coherence"):
            _confidence(getattr(self, name), name)

@dataclass(frozen=True)
class ReasoningTrace:
    summary: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    confidence_signals: ConfidenceSignals | None = None
    def __post_init__(self): object.__setattr__(self, "warnings", tuple(self.warnings or ()))

@dataclass(frozen=True)
class IntegrationBudget:
    max_tokens: int | None = None
    used_tokens: int | None = None
    truncated: bool = False

@dataclass(frozen=True)
class Answer:
    """Answer relative to its optional declared inference frame.

    Existing callers may retain the original seven positional arguments.
    """
    text: str
    confidence: float | None = None
    sources: tuple[str, ...] = field(default_factory=tuple)
    reasoning: ReasoningTrace | None = None
    integration_budget: IntegrationBudget | None = None
    notable_convergence: bool = False
    notable_convergence_reason: str | None = None
    inference_frame: InferenceFrame | None = None
    confidence_signals: ConfidenceSignals | None = None
    def __post_init__(self):
        _confidence(self.confidence, "confidence")
        object.__setattr__(self, "sources", tuple(self.sources or ()))


def compare_answer_frames(answer_a: Answer, answer_b: Answer) -> dict[str, Any]:
    """Compare bounded conditions, without ranking strategies as universally better."""
    left, right = answer_a.inference_frame, answer_b.inference_frame
    if left is None or right is None:
        return {"same_context": False, "same_model_artifacts": False, "same_retrieval_scope": False,
                "same_reasoning_strategy": False, "same_answer_text": answer_a.text == answer_b.text,
                "compatible": False, "requires_reverification": True,
                "differences": ("one_or_both_answers_have_no_inference_frame",)}
    differences = []
    same_context = (left.question_hash, left.document_hash, left.context_hash) == (right.question_hash, right.document_hash, right.context_hash)
    same_model = left.model == right.model
    same_scope = left.retrieval == right.retrieval
    same_strategy = left.generation.strategy == right.generation.strategy
    for name, same in (("context", same_context), ("model_artifacts", same_model), ("retrieval_scope", same_scope), ("reasoning_strategy", same_strategy)):
        if not same: differences.append(name)
    compatible = same_context and same_model and same_scope
    return {"same_context": same_context, "same_model_artifacts": same_model,
            "same_retrieval_scope": same_scope, "same_reasoning_strategy": same_strategy,
            "same_answer_text": answer_a.text == answer_b.text, "compatible": compatible,
            "requires_reverification": not compatible, "differences": tuple(differences)}


def _plain(value: Any) -> Any:
    if is_dataclass(value): return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple): return [_plain(item) for item in value]
    if isinstance(value, dict): return {key: _plain(item) for key, item in value.items()}
    return value

def serialize_inference_frame(frame: InferenceFrame) -> str:
    return json.dumps(_plain(frame), sort_keys=True, separators=(",", ":"))

def deserialize_inference_frame(payload: str) -> InferenceFrame:
    from .relativity import GenerationFrame, ModelArtifactReference, RetrievalFrame
    data = json.loads(payload)
    required = {"frame_id", "question_hash", "document_hash", "context_hash", "model", "retrieval", "generation", "assumptions", "limitations", "created_at"}
    if not isinstance(data, dict) or not required.issubset(data): raise ValueError("invalid inference frame payload")
    known = required | {"parent_frame_id"}
    data = {key: value for key, value in data.items() if key in known}
    data["model"] = ModelArtifactReference(**data["model"])
    data["retrieval"] = RetrievalFrame(**data["retrieval"])
    data["generation"] = GenerationFrame(**data["generation"])
    return InferenceFrame(**data)

def serialize_answer(answer: Answer) -> str:
    return json.dumps(_plain(answer), sort_keys=True, separators=(",", ":"))

def deserialize_answer(payload: str) -> Answer:
    data = json.loads(payload)
    if not isinstance(data, dict) or "text" not in data: raise ValueError("invalid answer payload")
    allowed = {item.name for item in fields(Answer)}
    data = {key: value for key, value in data.items() if key in allowed}
    if data.get("inference_frame") is not None: data["inference_frame"] = deserialize_inference_frame(json.dumps(data["inference_frame"]))
    if data.get("reasoning") is not None:
        trace = data["reasoning"]
        if trace.get("confidence_signals") is not None: trace["confidence_signals"] = ConfidenceSignals(**trace["confidence_signals"])
        data["reasoning"] = ReasoningTrace(**trace)
    if data.get("integration_budget") is not None: data["integration_budget"] = IntegrationBudget(**data["integration_budget"])
    if data.get("confidence_signals") is not None: data["confidence_signals"] = ConfidenceSignals(**data["confidence_signals"])
    return Answer(**data)
