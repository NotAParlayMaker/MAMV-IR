"""Tamper-evident event-chain helpers for audit records."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Any, Sequence
from .models import Context, LedgerEvent

def _normal(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"): return {k: _normal(v) for k, v in value.__dict__.items()}
    if isinstance(value, dict) or hasattr(value, "items"): return {str(k): _normal(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_normal(v) for v in value]
    return value

def compute_event_hash(event: LedgerEvent) -> str:
    payload={"previous_event_hash":event.previous_event_hash,"event_id":event.event_id,"event_type":event.event_type,"actor":event.actor,"timestamp":event.timestamp,"context":_normal(event.context),"payload":_normal(event.payload)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

def chained_event(*, event_id: str, event_type: str, actor: str, timestamp: str, context: Context, payload: dict[str, Any], prior: LedgerEvent | None = None) -> LedgerEvent:
    base=LedgerEvent(event_id,event_type,actor,timestamp,context,payload,prior.event_id if prior else None,prior.event_hash if prior else None)
    return LedgerEvent(**{**base.__dict__, "event_hash":compute_event_hash(base)})

@dataclass(frozen=True)
class IntegrityViolation:
    event_id: str; rule: str; detail: str

def validate_ledger_chain(events: Sequence[LedgerEvent]) -> list[IntegrityViolation]:
    issues=[]; prior=None
    for event in events:
        if not event.event_hash:
            continue # legacy event: readable but cannot be integrity-validated
        expected=compute_event_hash(event)
        if event.event_hash != expected: issues.append(IntegrityViolation(event.event_id,"event_hash","payload or event fields do not match event_hash"))
        if prior is None:
            if event.previous_event_id or event.previous_event_hash: issues.append(IntegrityViolation(event.event_id,"genesis_link","first hashed event has a previous link"))
        else:
            if event.previous_event_id != prior.event_id: issues.append(IntegrityViolation(event.event_id,"previous_event_id","previous event id does not link to preceding event (reordered or missing event)"))
            if event.previous_event_hash != prior.event_hash: issues.append(IntegrityViolation(event.event_id,"previous_event_hash","previous event hash link is incorrect"))
        prior=event
    return issues
