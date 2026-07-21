"""Persistence helpers. Legacy list/dict records are normalized on load."""
from __future__ import annotations
import json
from dataclasses import fields, is_dataclass
from collections.abc import Mapping
from .models import AcceptanceCriterion, Claim, Context, Evidence, ExecutionAttempt, LedgerEvent, VerificationResult

def _plain(value):
    if is_dataclass(value): return {f.name:_plain(getattr(value,f.name)) for f in fields(value)}
    if isinstance(value, Mapping): return {k:_plain(v) for k,v in value.items()}
    if isinstance(value, tuple): return [_plain(v) for v in value]
    if isinstance(value, list): return [_plain(v) for v in value]
    return value
def serialize_run(state: dict) -> str: return json.dumps(_plain(state), sort_keys=True)
def _context(d): return Context(**d)
def deserialize_run(payload: str) -> dict:
    s=json.loads(payload)
    s["acceptance_criteria"]=[AcceptanceCriterion(**x) for x in s.get("acceptance_criteria", [])]
    s["claims"]=[Claim(**{**x,"context":_context(x["context"]) if x.get("context") else None}) for x in s.get("claims", [])]
    s["evidence"]=[Evidence(**{**x,"context":_context(x["context"])}) for x in s.get("evidence", [])]
    s["verification_results"]=[VerificationResult(**x) for x in s.get("verification_results", [])]
    s["ledger_events"]=[LedgerEvent(**{**x,"context":_context(x["context"])}) for x in s.get("ledger_events", [])]
    s["attempts"]=[ExecutionAttempt(**{**x,"context":_context(x["context"])}) for x in s.get("attempts", [])]
    return s
def export_claim_evidence_graph(state: dict) -> dict:
    return {"claims":[_plain(x) for x in state.get("claims",[])],"evidence":[_plain(x) for x in state.get("evidence",[])],"edges":[{"claim_id":c.claim_id,"evidence_id":e} for c in state.get("claims",[]) for e in c.evidence_ids]}
def chronological_ledger(state: dict) -> list[LedgerEvent]: return sorted(state.get("ledger_events",[]), key=lambda event:event.timestamp)
