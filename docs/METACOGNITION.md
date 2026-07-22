# Metacognitive governance

This optional layer adds concise, structured deliberation records to the existing evidence-governed graph. It is inspired by inner speech, discursive clarity, intersubjective judgment, and metacognition as design ideas—not a claim of human-like thought.

## Architecture and authority

`reflect_on_plan` and `reflect_on_result` request summaries, assumptions, uncertainty, alternatives, needed evidence, action, and confidence. `self_critique` identifies unsupported claims. Their records are immutable `ReasoningStep`, `Critique`, and `MetacognitiveSnapshot` values inside `DeliberationRecord`. They are always `model_inference`; only authorized sandbox, test-runner, and static-analyzer `Evidence` can establish observed facts.

## Persistence and CLI

`serialize_run` includes deliberation and old saved runs deserialize to empty tuples. Ledger events cover recorded steps, critiques, and snapshots and remain hash chained. Enable with `MAMV_IR_METACOGNITION_ENABLED=true` or `--metacognition`; use `--show-deliberation` and `--show-critiques` with `--receipt` for concise output. Configuration also supports `MAMV_IR_REASONING_SAMPLES`, `MAMV_IR_MAX_REFLECTION_ITERATIONS`, and confidence/clarity policy values.

## Limits and failure modes

Malformed reflective output is retained as non-authoritative `model_output_unparseable` evidence. Agreement is a stability signal, not evidence, and cannot override contradictory authorized evidence. A communicable rationale is inspectable, not proven correct. No raw private chain-of-thought is requested or exposed.
