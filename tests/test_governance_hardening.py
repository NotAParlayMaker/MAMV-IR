import json
import pytest
from agent.informational.constitution import review
from agent.informational.ledger import chained_event, validate_ledger_chain
from agent.informational.models import AcceptanceCriterion, Claim, Context, Evidence, ExecutionAttempt, LedgerEvent, VerificationResult
from agent.informational.observers import authorize_claim_verification
from agent.informational.serialization import deserialize_run, serialize_run

def ctx(): return Context(0,"goal")
def ev(kind, ident="e1", source="sandbox"): return Evidence(ident,kind,"x",source,ctx(),{})
def verified(observer, kind, claim_type="observation"):
    e=ev(kind); return Claim("c","fact",claim_type,observer,ctx(),[e.evidence_id],1,"verified"), e
@pytest.mark.parametrize("observer,kind,ctype,phrase",[("sandbox","stdout","normative_judgment","sandbox may"),("reasoning_model","stdout","observation","reasoning_model"),("test_runner","static_analysis_result","observation","test_runner")])
def test_authority_matrix_rejects_cross_authority(observer,kind,ctype,phrase):
    c,e=verified(observer,kind,ctype); result=authorize_claim_verification(c,[e]); assert not result.allowed and phrase in result.explanation

def test_records_are_deeply_immutable_and_confidence_is_bounded():
    c=Claim("c","x","observation","sandbox",ctx(),["e"])
    with pytest.raises(AttributeError): c.evidence_ids.append("other")
    with pytest.raises(TypeError): ctx().environment_metadata["x"]=1
    with pytest.raises(ValueError): Claim("bad","x","observation","sandbox",ctx(),confidence=-.1)
    with pytest.raises(ValueError): VerificationResult("x",True,1.5,"x","sandbox")

def test_legacy_serialization_loads_and_new_roundtrip_is_immutable():
    legacy=json.dumps({"claims":[{"claim_id":"c","statement":"x","claim_type":"observation","observer":"sandbox","context":{"iteration":0,"goal":"g"},"evidence_ids":["e"]}],"evidence":[],"attempts":[],"ledger_events":[],"acceptance_criteria":[],"verification_results":[]})
    restored=deserialize_run(legacy); assert restored["claims"][0].evidence_ids == ("e",)
    again=deserialize_run(serialize_run(restored)); assert isinstance(again["claims"][0].evidence_ids,tuple)

def test_ledger_detects_tampering_reorder_and_broken_link():
    a=chained_event(event_id="a",event_type="x",actor="a",timestamp="1",context=ctx(),payload={})
    b=chained_event(event_id="b",event_type="x",actor="a",timestamp="2",context=ctx(),payload={},prior=a)
    tampered=LedgerEvent(**{**b.__dict__,"payload":{"changed":True}})
    assert any(x.rule=="event_hash" for x in validate_ledger_chain([a,tampered]))
    assert any(x.rule=="previous_event_id" for x in validate_ledger_chain([b,a]))
    broken=LedgerEvent(**{**b.__dict__,"previous_event_hash":"bad"})
    assert any(x.rule=="previous_event_hash" for x in validate_ledger_chain([a,broken]))

def test_review_detects_references_duplicates_timeout_unapproved_and_contradicted_decision():
    c=Claim("c","x","observation","sandbox",ctx(),["missing"],1,"verified",["parent"])
    criterion=AcceptanceCriterion("k","x","unknown",True)
    attempt=ExecutionAttempt("a","","","",0,False,ctx(),())
    state={"claims":[c,c],"evidence":[ev("stdout","e"),ev("stdout","e")],"ledger_events":[LedgerEvent("l","x","a","1",ctx(),{}),LedgerEvent("l","x","a","2",ctx(),{})],"attempts":[attempt],"acceptance_criteria":[criterion],"verification_results":[VerificationResult("k",True,1,"x","sandbox")],"final_decision":{"claim_ids":["c"],"evidence_ids":["nope"]}}
    report="\n".join(review(state))
    for rule in ("missing_evidence","missing_parent_claim","duplicate_claim_id","duplicate_evidence_id","duplicate_ledger_event_id","missing_timeout_evidence","required_not_approved","decision_missing_evidence"): assert rule in report

def test_review_rejects_contradicted_claim_in_final_decision():
    c=Claim("c","x","observation","sandbox",ctx(),[],1,"contradicted")
    assert "decision_contradicted_claim" in "\n".join(review({"claims":[c],"evidence":[],"final_decision":{"claim_ids":["c"],"evidence_ids":[]}}))

def test_bad_confidence_deserialization_rejected():
    with pytest.raises(ValueError): deserialize_run(json.dumps({"claims":[{"claim_id":"c","statement":"x","claim_type":"observation","observer":"sandbox","context":{"iteration":0,"goal":"g"},"confidence":4}],"evidence":[],"attempts":[],"ledger_events":[],"acceptance_criteria":[],"verification_results":[]}))

def test_graph_emits_timeout_evidence():
    from agent.graph import run_agent
    from agent.llm import MockLLM
    from agent.sandbox import ExecutionResult
    class TimeoutSandbox:
        def run(self, code): return ExecutionResult("", "timed out", -1, True)
    state=run_agent("anything",MockLLM(),TimeoutSandbox(),1)
    assert any(e.evidence_type == "timeout" and e.value is True for e in state["evidence"])
