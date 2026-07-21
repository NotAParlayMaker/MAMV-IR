"""Constitutional checks that prevent evidence from becoming unearned success."""
from __future__ import annotations
from dataclasses import dataclass
from .ledger import validate_ledger_chain
from .models import Claim
from .observers import authorize_claim_verification
from .validation import validate_claim_requirements, validate_record_confidence
@dataclass(frozen=True)
class Violation:
    rule: str; subject_id: str; detail: str
    def format(self): return f"[{self.rule}] {self.subject_id}: {self.detail}"
def _dupes(items, attr):
    seen=set(); return {getattr(x,attr) for x in items if getattr(x,attr) in seen or seen.add(getattr(x,attr))}
def review(state: dict) -> list[str]:
    """Review all provenance links; failures remain auditable strings for compatibility."""
    v=[]; claims=state.get("claims",[]); evidence=state.get("evidence",[]); events=state.get("ledger_events",[])
    ids={c.claim_id for c in claims}; eids={e.evidence_id for e in evidence}
    for kind, items, attr in (("duplicate_claim_id",claims,"claim_id"),("duplicate_evidence_id",evidence,"evidence_id"),("duplicate_ledger_event_id",events,"event_id")):
        for value in _dupes(items,attr): v.append(Violation(kind,value,"identifier is duplicated"))
    for claim in claims:
        for requirement, detail in {
            "missing_observer": "has no observer.",
            "missing_context": "has no context.",
            "missing_support": "non-observation lacks evidence or parent claims.",
        }.items():
            if requirement in validate_claim_requirements(claim):
                v.append(Violation(requirement,claim.claim_id,detail))
        try:
            validate_record_confidence(claim)
        except ValueError as error:
            v.append(Violation("invalid_confidence",claim.claim_id,str(error)))
        for eid in claim.evidence_ids:
            if eid not in eids: v.append(Violation("missing_evidence",claim.claim_id,f"references missing evidence {eid}."))
        for parent in claim.derived_from:
            if parent not in ids: v.append(Violation("missing_parent_claim",claim.claim_id,f"references missing parent claim {parent}."))
        if claim.context:
            for item in evidence:
                if item.evidence_id in claim.evidence_ids and item.context.goal != claim.context.goal:
                    v.append(Violation("context_mismatch",claim.claim_id,f"evidence {item.evidence_id} has a different goal context."))
        if claim.status == "verified":
            auth=authorize_claim_verification(claim,[e for e in evidence if e.evidence_id in claim.evidence_ids])
            if not auth.allowed: v.append(Violation("observer_authority",claim.claim_id,auth.explanation))
        if claim.supersedes and claim.supersedes not in ids: v.append(Violation("missing_supersession",claim.claim_id,f"supersedes missing claim {claim.supersedes}."))
    for claim in claims:
        trail=set(); cur=claim
        while cur.supersedes:
            if cur.claim_id in trail: v.append(Violation("supersession_cycle",claim.claim_id,"supersession links form a cycle.")); break
            trail.add(cur.claim_id); cur=next((x for x in claims if x.claim_id==cur.supersedes),cur)
            if cur.claim_id not in ids: break
    required=[c for c in state.get("acceptance_criteria",[]) if c.required]; evaluated={r.criterion_id for r in state.get("verification_results",[])}
    for c in required:
        if c.criterion_id not in evaluated: v.append(Violation("required_not_evaluated",c.criterion_id,"was not explicitly evaluated."))
        if c.approval_status != "approved": v.append(Violation("required_not_approved",c.criterion_id,"is not approved."))
    decision=state.get("final_decision")
    if decision:
        if not decision.get("claim_ids"): v.append(Violation("decision_claims","final_decision","does not cite claims."))
        if not decision.get("evidence_ids"): v.append(Violation("decision_evidence","final_decision","does not cite evidence."))
        for cid in decision.get("claim_ids",[]):
            claim=next((x for x in claims if x.claim_id==cid),None)
            if not claim: v.append(Violation("decision_missing_claim","final_decision",f"cites missing claim {cid}."))
            elif claim.status=="contradicted": v.append(Violation("decision_contradicted_claim","final_decision",f"relies on contradicted claim {cid}."))
        for eid in decision.get("evidence_ids",[]):
            if eid not in eids: v.append(Violation("decision_missing_evidence","final_decision",f"cites missing evidence {eid}."))
    for attempt in state.get("attempts",[]):
        matched=[e for e in evidence if e.evidence_id in attempt.evidence_ids and e.evidence_type=="timeout"]
        if not matched: v.append(Violation("missing_timeout_evidence",attempt.attempt_id,"execution attempt lacks timeout evidence."))
    for issue in validate_ledger_chain(events): v.append(Violation(f"ledger_{issue.rule}",issue.event_id,issue.detail))
    return [x.format() for x in v]
