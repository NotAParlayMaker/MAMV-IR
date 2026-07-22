import json
import pytest
from agent.informational import (Answer, ConfidenceSignals, GenerationFrame, IntegrationBudget, ReasoningTrace,
    build_inference_frame, compare_answer_frames, derive_inference_frame, deserialize_answer,
    deserialize_inference_frame, serialize_answer, serialize_inference_frame)


def frame(**changes):
    values = dict(question="What?", context="selected evidence", document="document", model_id="mock", model_revision="abc",
                  selected_source_ids=("a",), dropped_source_ids=("b",), integration_mode="integrated", max_tokens=100, used_tokens=80,
                  created_at="2025-01-01T00:00:00+00:00")
    values.update(changes)
    return build_inference_frame(**values)

def test_direct_answer_has_a_deterministic_frame_and_legacy_answer_is_valid():
    assert Answer("legacy", .5, (), None, None, False, None).inference_frame is None
    first, second = frame(), frame()
    assert first.frame_id == second.frame_id
    answer = Answer("bounded", .5, ("a",), ReasoningTrace("brief"), IntegrationBudget(100, 80), False, None, first)
    assert answer.inference_frame == first

def test_scope_warnings_and_unpinned_limitation_are_recordable():
    unpinned = frame(model_revision=None, integration_mode="fragmented", selected_source_ids=(), dropped_source_ids=("missing",))
    assert "Model revision was not pinned; exact reproduction is not guaranteed." in unpinned.limitations
    trace = ReasoningTrace("summary", ("context_truncated", "relevant_context_may_be_missing", "fragmented_answers_disagree", "retrieval_returned_no_sources", "answer_relative_to_selected_chunks"))
    assert "fragmented_answers_disagree" in trace.warnings

def test_generation_samples_and_derived_frame_are_explicit():
    source = frame(num_samples=3, strategy="self_consistency")
    target, transition = derive_inference_frame(source, reason="self_refinement", changed_fields=("generation.strategy",), answer_changed=True)
    assert source.generation.num_samples == 3
    assert target.parent_frame_id == source.frame_id
    assert transition.reason == "self_refinement" and transition.answer_changed

def test_context_changes_require_reverification_and_confidence_remains_separate():
    left = Answer("same", .8, inference_frame=frame(), confidence_signals=ConfidenceSignals(.8, .9, .2, .7, .8))
    right = Answer("same", .8, inference_frame=frame(context="different"), confidence_signals=ConfidenceSignals(.8, .9, .2, .7, .8))
    result = compare_answer_frames(left, right)
    assert not result["same_context"] and result["requires_reverification"]
    assert left.confidence_signals.consensus != left.confidence_signals.grounding

def test_answer_and_frame_serialization_and_validation():
    original = Answer("answer", .4, inference_frame=frame(), confidence_signals=ConfidenceSignals(coherence=.3))
    assert deserialize_answer(serialize_answer(original)) == original
    assert deserialize_inference_frame(serialize_inference_frame(original.inference_frame)) == original.inference_frame
    with pytest.raises(ValueError): Answer("x", 1.1)
    broken = json.loads(serialize_inference_frame(original.inference_frame)); broken["created_at"] = "not-a-time"
    with pytest.raises(ValueError): deserialize_inference_frame(json.dumps(broken))
