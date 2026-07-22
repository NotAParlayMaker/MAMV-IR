import pytest
from agent.metacognition import assess_communicability, parse_reflective_output, select_candidate, ReasoningCandidate, ReflectiveOutput, is_model_inference, is_observed_fact
from agent.informational.models import Claim, Context, Evidence, ReasoningStep
from agent.informational.serialization import deserialize_run, serialize_run

TEXT='''Reasoning Summary:\n- inspect plan\nAssumptions:\n- input is valid\nUncertainties:\n- tests absent\nAlternatives Considered:\n- seek tests\nEvidence Needed:\n- test result\nProposed Action:\nseek_evidence\nConfidence (0-1):\n0.7'''
def test_reflective_parser_and_confidence():
    value=parse_reflective_output(TEXT); assert value.summary == "- inspect plan" and value.assumptions == ("input is valid",) and value.confidence == .7
def test_malformed_reflection_is_warned(): assert "unparseable" in parse_reflective_output("hello").warnings[0]
def test_confidence_validation_and_evidence_boundary():
    with pytest.raises(ValueError): ReasoningStep("s","planning","x",model_confidence=2)
    context=Context(0,"g"); evidence=Evidence("e","exit_code",0,"sandbox",context,{"authoritative":True})
    assert is_observed_fact(evidence) and is_model_inference(ReasoningStep("s","planning","x"))
def test_deliberation_round_trip_is_backward_compatible():
    restored=deserialize_run(serialize_run({"deliberation": {"reasoning_steps":[],"critiques":[],"snapshots":[]}})); assert restored["deliberation"].reasoning_steps == ()
    assert deserialize_run("{}")["deliberation"].critiques == ()
def test_consensus_is_not_evidence_or_truth():
    c=select_candidate((ReasoningCandidate("a",ReflectiveOutput(proposed_action="revise"),True), ReasoningCandidate("b",ReflectiveOutput(proposed_action="revise"),True)))
    assert c.consensus_confidence == 1 and not is_observed_fact(c)
def test_communicability_requires_evidence_references():
    claim=Claim("c","conclusion","inference","reasoning_model",Context(0,"g"))
    assessment=assess_communicability(claim,[],[],None); assert not assessment.communicable and "evidence references" in assessment.missing_elements
