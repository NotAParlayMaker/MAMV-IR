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
