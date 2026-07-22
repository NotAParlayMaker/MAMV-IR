import pytest

from agent.informational import (
    CandidateAnswer, CandidateExport, ClaimCandidate, EvidenceCandidate,
    GenerationSample, ProposedEvidenceRelation, build_inference_frame,
    deserialize_candidate_export, serialize_candidate_export,
)


def frame(mode="fragmented", strategy="self_consistency"):
    return build_inference_frame(
        question="What changed?", context="chunk", model_id="local", model_revision="abc",
        selected_source_ids=("chunk-a",), integration_mode=mode, strategy=strategy,
        created_at="2025-01-01T00:00:00+00:00",
    )


def test_export_preserves_derivation_strategy_samples_and_disagreement():
    claim = ClaimCandidate("claim-1", "A proposed statement", "generated", evidence_density=.2)
    evidence = EvidenceCandidate("evidence-1", "Quoted context", "extracted", ("chunk-a",))
    answer = CandidateAnswer("answer-1", "A candidate answer", ("chunk-a",), (claim,), (evidence,),
                              (ProposedEvidenceRelation("claim-1", "evidence-1", "may_relates_to"),), .4,
                              ("Sparse context.",))
    exported = CandidateExport("mamv-model-candidate-export/v1", frame(), "fragmented", "self_consistency",
                                (answer,), (GenerationSample("sample-1", "Alternative", evidence_density=.2),),
                                "sample-1", "Selected without resolving the retained alternative.",
                                ("Grounding was incomplete; model-stated confidence was downgraded.",), ("Context is bounded.",))
    assert deserialize_candidate_export(serialize_candidate_export(exported)) == exported
    assert exported.answers[0].claim_candidates[0].derivation == "generated"


def test_generated_content_requires_density_and_fragmented_scope_stays_separate():
    with pytest.raises(ValueError, match="require evidence_density"):
        ClaimCandidate("c", "text", "generated")
    answer = CandidateAnswer("a", "text", ("one", "two"))
    with pytest.raises(ValueError, match="one evidence scope"):
        CandidateExport("mamv-model-candidate-export/v1", frame(strategy="direct"), "fragmented", "direct", (answer,))


def test_multi_strategy_cannot_drop_its_samples_or_selected_id():
    answer = CandidateAnswer("a", "text", ("chunk-a",))
    with pytest.raises(ValueError, match="preserve"):
        CandidateExport("mamv-model-candidate-export/v1", frame("integrated", "multi_model_debate"), "integrated", "multi_model_debate", (answer,))
    with pytest.raises(ValueError, match="selected_sample_id"):
        CandidateExport("mamv-model-candidate-export/v1", frame("integrated", "direct"), "integrated", "direct", (answer,), selected_sample_id="gone")
