# Informational Relativity

MAMV-IR records verification in governance frames and bounded model answers in inference frames. An inference frame is not a claim that all truth is subjective: it identifies the conditions under which an output was produced and can be checked.

## Inference frames

`build_inference_frame` creates immutable, canonical JSON-serializable records containing hashes of the question, document, and selected context; a model, adapter, and tokenizer reference; retrieval source IDs (including dropped IDs); integration mode and token budget; generation strategy and parameters; assumptions; limitations; creation time; and an optional parent frame. It never stores API keys, raw access tokens, or unrestricted prompts. Frame IDs are SHA-256-derived from those bounded conditions, so identical inputs receive the same ID. An unpinned model revision receives the explicit reproducibility limitation.

## Context, retrieval, and reasoning

A retrieved answer is relative to its selected chunks, not silently to an entire corpus. Callers should record warnings such as `context_truncated`, `relevant_context_may_be_missing`, `fragmented_answers_disagree`, `retrieval_returned_no_sources`, and `answer_relative_to_selected_chunks` in the concise `ReasoningTrace`. Direct, self-consistency, self-refine, integrated, and fragmented strategies are recorded in `GenerationFrame`; no strategy is universally superior merely because it is more elaborate.

## Confidence and derivation

`ConfidenceSignals` separately records model-stated confidence, sample consensus, grounding support, retrieval coverage, and coherence. None alone establishes correctness, and consensus/coherence are never converted into grounding confidence. `derive_inference_frame` returns a new frame and an immutable `InferenceFrameTransition`; it does not mutate history. Use it for refinement, follow-ups, retrieval, integration, strategy, or bounded conversation-history changes. If earlier turns are dropped, record the warning: `Answer was generated without one or more earlier session turns.` Session context is not permanent model learning.

## Serialization and comparison

`serialize_answer`, `deserialize_answer`, `serialize_inference_frame`, and `deserialize_inference_frame` use stable compact JSON, validate ISO-8601 timezone-aware timestamps and confidence ranges, and ignore unknown optional fields conservatively. `compare_answer_frames` reports context, artifact, retrieval, strategy, text equality, compatibility, re-verification need, and changed dimensions.

```python
frame = build_inference_frame(question="What changed?", context="chunk A", model_id="local", model_revision="abc", selected_source_ids=("A",), created_at="2025-01-01T00:00:00+00:00")
answer = Answer("A bounded answer", inference_frame=frame)
print(serialize_answer(answer))
```

Reproducibility remains limited by unpinned remote artifacts, unavailable source material, runtime/provider behavior, and any context not recorded in the frame.

## MAMV-Model candidate export contract

`CandidateExport` is the versioned handoff from MAMV-Model to MAMV. It is a
candidate-only record, never a verification result or verdict. Its schema version
is `mamv-model-candidate-export/v1`; consumers should reject an unknown version
rather than reinterpret fields silently. Every export has limitations (an empty
array means none were identified), its actual generation strategy, and its
inference frame.

Every `ClaimCandidate` and `EvidenceCandidate` declares a derivation:
`retrieved`, `extracted`, or `generated`. Generated material must include an
`evidence_density` from 0 to 1; retrieved and extracted material cannot borrow
that field to imply a model inference. Model self-report is named
`model_stated_confidence`, not verification confidence. Coherence is not part of
the export contract and must not be interpreted as a truth signal.

Fragmented retrieval exports one `CandidateAnswer` per chunk and each answer has
exactly one `evidence_scope`; callers must explicitly request an integrated
export before combining chunks. Multi-sample strategies (`self_consistency`,
`self_refine`, and `multi_model_debate`) preserve every `GenerationSample`, the
selected sample ID, and the selection rationale. Proposed evidence relations are
only proposals for MAMV to assess, not assertions of support.

`grounding_critiques` records visible shortcomings. A grounding requirement may
only lower `model_stated_confidence` or add critique; it has no success path that
marks a candidate correct. Candidate export is session-scoped metadata and does
not create cross-session memory, a cache, or training data.
