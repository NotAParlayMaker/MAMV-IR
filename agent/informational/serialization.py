"""Persistence helpers. Legacy list/dict records are normalized on load."""
from __future__ import annotations
import json
from datetime import datetime
from dataclasses import fields, is_dataclass
from collections.abc import Mapping
from .relativity import CompletionDecision, FrameTransformation, InformationalFrame, InformationalPerspective, RelativeVerificationResult
from .models import AcceptanceCriterion, Claim, Context, Critique, DeliberationRecord, Evidence, ExecutionAttempt, LedgerEvent, MetacognitiveSnapshot, ReasoningStep, VerificationResult

def _plain(value):
    if is_dataclass(value): return {f.name:_plain(getattr(value,f.name)) for f in fields(value)}
    if isinstance(value, Mapping): return {k:_plain(v) for k,v in value.items()}
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, tuple): return [_plain(v) for v in value]
    if isinstance(value, list): return [_plain(v) for v in value]
    return value
def serialize_run(state: dict) -> str: return json.dumps(_plain(state), sort_keys=True)
def _context(d): return Context(**d)
def deserialize_run(payload: str) -> dict:
    s=json.loads(payload)
    def dt(value): return datetime.fromisoformat(value) if isinstance(value, str) else value
    def frame(x): return InformationalFrame(**{**x, "valid_at":dt(x["valid_at"]), "created_at":dt(x["created_at"])})
    def relative(x): return RelativeVerificationResult(**{**x, "status": x["status"], "valid_at":dt(x["valid_at"]), "expires_at":dt(x["expires_at"]) if x.get("expires_at") else None})
    s["informational_frames"]=[frame(x) for x in s.get("informational_frames", [])]
    s["relative_verification_results"]=[relative(x) for x in s.get("relative_verification_results", [])]
    s["frame_transformations"]=[FrameTransformation(**x) for x in s.get("frame_transformations", [])]
    s["informational_perspectives"]=[InformationalPerspective(**x) for x in s.get("informational_perspectives", [])]
    if s.get("completion_decision"): s["completion_decision"]=CompletionDecision(**{**s["completion_decision"], "decided_at":dt(s["completion_decision"]["decided_at"])})
    if not s["informational_frames"] and (s.get("claims") or s.get("evidence")):
        # Migration is deliberately labeled: legacy records did not record this frame.
        legacy=InformationalFrame("frame_legacy_inferred", "context_legacy_inferred", "legacy", "legacy", "legacy", "legacy", (), (), (), {}, datetime.now().astimezone(), datetime.now().astimezone(), limitations=("Legacy implicit frame inferred during migration; it was not originally recorded.",), frame_origin="legacy_inferred")
        s["informational_frames"]=[legacy]; s["active_frame_id"]=legacy.frame_id
    s["acceptance_criteria"]=[AcceptanceCriterion(**x) for x in s.get("acceptance_criteria", [])]
    s["claims"]=[Claim(**{**x,"context":_context(x["context"]) if x.get("context") else None}) for x in s.get("claims", [])]
    s["evidence"]=[Evidence(**{**x,"context":_context(x["context"])}) for x in s.get("evidence", [])]
    s["verification_results"]=[VerificationResult(**x) for x in s.get("verification_results", [])]
    s["ledger_events"]=[LedgerEvent(**{**x,"context":_context(x["context"])}) for x in s.get("ledger_events", [])]
    s["attempts"]=[ExecutionAttempt(**{**x,"context":_context(x["context"])}) for x in s.get("attempts", [])]
    d=s.get("deliberation", {})
    s["deliberation"]=DeliberationRecord(tuple(ReasoningStep(**x) for x in d.get("reasoning_steps", [])), tuple(Critique(**x) for x in d.get("critiques", [])), tuple(MetacognitiveSnapshot(**x) for x in d.get("snapshots", [])))
    return s
def export_claim_evidence_graph(state: dict) -> dict:
    d=state.get("deliberation", DeliberationRecord())
    return {"claims":[_plain(x) for x in state.get("claims",[])],"evidence":[_plain(x) for x in state.get("evidence",[])],"reasoning_steps":[_plain(x) for x in d.reasoning_steps],"edges":[{"claim_id":c.claim_id,"evidence_id":e} for c in state.get("claims",[]) for e in c.evidence_ids]}
def chronological_ledger(state: dict) -> list[LedgerEvent]: return sorted(state.get("ledger_events",[]), key=lambda event:event.timestamp)


def export_informational_frames(state: dict) -> list[dict]: return [_plain(x) for x in state.get("informational_frames", [])]
def export_frame_comparison(state: dict, frame_a: str, frame_b: str) -> dict:
    frames={x.frame_id:x for x in state.get("informational_frames", [])}; return {"frame_a":_plain(frames.get(frame_a)), "frame_b":_plain(frames.get(frame_b))}
def export_relative_verification_graph(state: dict) -> dict: return {"frames":export_informational_frames(state), "relative_verifications":[_plain(x) for x in state.get("relative_verification_results", [])]}
