"""Structured deliberation, never hidden chain-of-thought or evidence."""
from __future__ import annotations
from dataclasses import dataclass, field
import os, re
from typing import Iterable
from .informational.models import Claim, Evidence, ReasoningStep

@dataclass(frozen=True)
class MetacognitionConfig:
    enabled: bool = False; reasoning_samples: int = 1; max_reflection_iterations: int = 2
    require_stated_assumptions: bool = True; require_evidence_references: bool = True; confidence_threshold: float = .70
    def __post_init__(self):
        if self.reasoning_samples < 1 or self.max_reflection_iterations < 0: raise ValueError("sample and iteration counts must be non-negative")
        if not 0 <= self.confidence_threshold <= 1: raise ValueError("metacognitive confidence threshold must be between 0 and 1")
    @classmethod
    def from_env(cls):
        truth = lambda name, default: os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}
        return cls(truth("MAMV_IR_METACOGNITION_ENABLED", False), int(os.environ.get("MAMV_IR_REASONING_SAMPLES", "1")), int(os.environ.get("MAMV_IR_MAX_REFLECTION_ITERATIONS", "2")), truth("MAMV_IR_REQUIRE_STATED_ASSUMPTIONS", True), truth("MAMV_IR_REQUIRE_EVIDENCE_REFERENCES", True), float(os.environ.get("MAMV_IR_METACOGNITIVE_CONFIDENCE_THRESHOLD", ".70")))

@dataclass(frozen=True)
class ReflectiveOutput:
    summary: str = ""; assumptions: tuple[str,...] = (); uncertainties: tuple[str,...] = (); alternatives_considered: tuple[str,...] = (); evidence_needed: tuple[str,...] = (); proposed_action: str = ""; confidence: float | None = None; warnings: tuple[str,...] = ()
@dataclass(frozen=True)
class ReasoningCandidate:
    candidate_id: str; reflective: ReflectiveOutput; parseable: bool; consensus_confidence: float | None = None
@dataclass(frozen=True)
class CommunicabilityAssessment:
    communicable: bool; missing_elements: tuple[str,...]; contradictions: tuple[str,...]; support_summary: str; limitations: tuple[str,...]

REFLECTION_PROMPT = """Provide a concise structured deliberation record, not private reasoning.\nReasoning Summary:\n- concise rationale\nAssumptions:\n- item\nUncertainties:\n- item\nAlternatives Considered:\n- item\nEvidence Needed:\n- item\nProposed Action:\ncontinue\nConfidence (0-1):\n0.5"""
def reflective_prompt(task: str) -> str: return f"{REFLECTION_PROMPT}\n\nTask/context:\n{task}"
def _items(value: str) -> tuple[str,...]: return tuple(x.strip().lstrip("- ").strip() for x in value.splitlines() if x.strip() and x.strip() not in {"-", "none", "None"})
def parse_reflective_output(text: str) -> ReflectiveOutput:
    headers = r"Reasoning Summary|Assumptions|Uncertainties|Alternatives Considered|Evidence Needed|Proposed Action|Confidence \(0-1\)"
    found = list(re.finditer(rf"(?mi)^({headers}):\s*", text))
    if not found: return ReflectiveOutput(warnings=("metacognitive_output_unparseable: no structured sections",))
    values = {}
    for i, match in enumerate(found): values[match.group(1).lower()] = text[match.end():found[i+1].start() if i+1 < len(found) else len(text)].strip()
    warnings=[]
    summary=values.get("reasoning summary", "")
    if not summary: warnings.append("missing reasoning summary")
    confidence=None
    raw=values.get("confidence (0-1)", "")
    if raw:
        try:
            confidence=float(re.search(r"[01](?:\.\d+)?", raw).group())
            if not 0 <= confidence <= 1: raise ValueError
        except (AttributeError, ValueError): warnings.append("invalid confidence")
    else: warnings.append("missing confidence")
    return ReflectiveOutput(summary, _items(values.get("assumptions", "")), _items(values.get("uncertainties", "")), _items(values.get("alternatives considered", "")), _items(values.get("evidence needed", "")), values.get("proposed action", "").strip(), confidence, tuple(warnings))
def generate_reasoning_candidates(backend, messages, n_samples=1, **_):
    return tuple(ReasoningCandidate(f"reasoning_candidate_{i+1}", (r:=parse_reflective_output(backend.chat(messages))), not any("unparseable" in w for w in r.warnings)) for i in range(n_samples))
def select_candidate(candidates: Iterable[ReasoningCandidate]) -> ReasoningCandidate | None:
    valid=sorted((c for c in candidates if c.parseable), key=lambda c:(not bool(c.reflective.evidence_needed), c.candidate_id))
    if not valid: return None
    chosen=valid[0]; agreement=sum(c.reflective.proposed_action.strip().lower()==chosen.reflective.proposed_action.strip().lower() for c in valid)/len(valid)
    return ReasoningCandidate(chosen.candidate_id, chosen.reflective, True, agreement)
def is_observed_fact(item) -> bool: return isinstance(item, Evidence) and item.source in {"sandbox", "test_runner", "static_analyzer"} and bool((item.reliability or {}).get("authoritative"))
def is_model_inference(item) -> bool: return isinstance(item, ReasoningStep) and item.kind == "model_inference" or isinstance(item, Claim) and item.observer == "reasoning_model"
def requires_external_evidence(claim: Claim) -> bool: return claim.claim_type in {"observation", "inference", "prediction"}
def assess_communicability(claim: Claim, evidence: Iterable[Evidence], criteria, reasoning_step: ReasoningStep | None) -> CommunicabilityAssessment:
    missing=[]; limitations=[]; contradictions=[]
    if not claim.statement.strip(): missing.append("concise claim")
    if not claim.evidence_ids: missing.append("evidence references")
    if not any(c.criterion_id for c in criteria): missing.append("acceptance criterion")
    if not claim.observer: missing.append("observer attribution")
    if reasoning_step and reasoning_step.uncertainties: limitations.extend(reasoning_step.uncertainties)
    if claim.status == "contradicted": contradictions.append("claim is contradicted")
    if not limitations and claim.claim_type != "observation": limitations.append("no limitations stated")
    return CommunicabilityAssessment(not missing and not contradictions, tuple(missing), tuple(contradictions), f"{len(claim.evidence_ids)} evidence reference(s)", tuple(limitations))
