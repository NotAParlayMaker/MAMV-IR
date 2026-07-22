# MAMV-IR

> **MAMV-IR is an informational-governance operating layer for reasoning models. It governs how claims are created, contextualized, supported, challenged, revised, verified, and converted into decisions.**

MAMV-IR refactors the original autonomous coding prototype so a clean process exit is **evidence**, not proof that a user's task is done. A reasoning model (Kimi K3 or another adapter) may plan, interpret evidence, diagnose, and predict repairs. The MAMV-IR governance layer owns the structured ledger, applies observer authority boundaries, evaluates acceptance criteria, and blocks unsupported completion.

## Flow

```text
interpret_goal → plan → generate_code → execute → collect_evidence → verify
  → constitutional_review ── verified → finish
                           └─ insufficient evidence / contradicted → diagnose
                              → propose_repair → fix_code → execute
```

## Information model

Every run records JSON-serializable `Context`, `Evidence`, `Claim`, `AcceptanceCriterion`, `VerificationResult`, immutable `ExecutionAttempt`, and chronological `LedgerEvent` records. Sandbox observations authoritatively establish stdout, stderr, exit code, and timeout only. Test runners and static analyzers now produce and own their respective results: `test_result` is authored by `test_runner`, while `static_analysis_result` is authored by `static_analyzer`. The reasoning model cannot verify an unobserved runtime fact.

Required criteria are evaluated independently. Completion requires an execution, every required criterion supported at the configurable `MAMV_IR_CONFIDENCE_THRESHOLD` (default `0.80`), no contradiction, and a passing constitutional review. Failed diagnoses and repair predictions are retained and marked contradicted rather than erased.

### Example

For a goal that requires `Result: 42`, a program that prints `Result: 41` and exits `0` produces valid sandbox evidence but fails the stdout criterion, so the run is rejected and diagnosed. A program that exits `0` *and* prints `Result: 42` can finish after constitutional review.

## Run locally

```bash
pip install .
mamv-ir --backend mock --sandbox subprocess fibonacci --receipt --save-run run.json
mamv-ir --backend mock --sandbox subprocess "bug demo: division" --verbose
```

`--receipt` prints the acceptance criteria, confidence, related claims, and constitutional violations for either a successful or failed run. `--save-run PATH` writes the complete JSON record, including claims, evidence, and ledger events; load it later with `deserialize_run`. The offline `MockLLM` is deterministic and all tests run without an API key or network. Contributors should see [CONTRIBUTING.md](CONTRIBUTING.md) for extension points and local checks.

## Reasoning-loop context and resilience

Repair sees the complete execution-attempt history for a run: every prior code
candidate is paired with its stdout, stderr, exit code, and timeout evidence.
This gives the repair model direct context about fixes that already failed.
To avoid spending iterations on a repeated known-bad candidate, MAMV-IR
normalizes trailing whitespace and detects exact normalized-code repeats
(similarity ratio **1.0**); it then abstains with `completion_status` of
`stuck_in_loop` instead of executing that candidate again. The history is
currently unbounded because `max_iterations` defaults to three, so it is small
and complete in normal runs.

Planning uses a more exploratory temperature (`0.5`), while diagnosis and
repair use `0.1` and evidence-bound system prompts. Generation uses `0.3`.
If generated or repaired output lacks a complete Python fence, the graph makes
one corrective follow-up requesting exactly one fenced block; a second failure
records `model_output_unparseable` evidence and abstains rather than running
model prose in the sandbox.

For Kimi, transient OpenAI-compatible connection, timeout, rate-limit, and
server errors receive two retries after exponential backoff of 0.1 seconds and
0.2 seconds (three total attempts). Exhaustion raises `LLMCallFailed`, which
the graph records as `llm_unavailable`, distinct from a sandbox/code failure.
`MockLLM` intentionally has no retry behavior, keeping offline tests fully
deterministic.

## Kimi and other providers

Kimi remains supported through `KimiK3Backend`, using Moonshot's OpenAI-compatible API:

```bash
export MOONSHOT_API_KEY=your-key
# optional: export MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
mamv-ir --backend kimi --sandbox subprocess "Write a Python program"
```

To add another provider, implement the provider-neutral `LLMBackend.chat(messages) -> str` interface in `agent/llm.py`; do not add governance behavior to the adapter. The graph depends only on that interface.

## Persistence helpers

`agent.informational.serialization` exposes `serialize_run`, `deserialize_run`, `export_claim_evidence_graph`, and `chronological_ledger`. These support later durable storage without changing the in-memory model.

## Current limitations

- Acceptance criteria also support `tests_pass` when goal interpretation supplies optional `test_code`. The test runner writes generated code and that test module into the selected sandbox and runs `python -m pytest -q`; absent `test_code` produces explicit “no test evidence available” abstention rather than a pass.
- `passes_static_analysis` performs only offline Python `ast.parse`/`compile` syntax validation and rejects bare `except:` clauses. It is intentionally not a full linter, type checker, security scanner, or semantic correctness check.
- Generated code is still a single Python script.
- The subprocess sandbox is a development fallback, not a host-security boundary; use Docker for untrusted code.
- A model can propose a weak or ambiguous goal interpretation, but ambiguity is retained and cannot silently satisfy missing evidence.

## Governance hardening and migration

Verification is now **policy-authorized**, rather than merely represented by
record fields. The authority matrix evaluates the requested verified status,
observer, claim type, evidence type, and verification method; a confidence
number cannot expand an observer's authority. Ledger events emitted by new
runs form a SHA-256 chain, while execution emits dedicated timeout evidence.
Criteria proposed by a reasoning model must be explicitly policy-approved
before required criteria can permit completion.

### Serialized-record migration

`deserialize_run` remains backward compatible with pre-v2 JSON: list fields
are converted to immutable tuples, metadata/payload dictionaries are copied
into immutable mappings, and old unhashed ledger events load as legacy audit
records. New serialized runs include `previous_event_hash` and `event_hash`.
Legacy events cannot retrospectively prove tamper evidence; append new chained
events for forward integrity. Invalid confidence values are rejected on load.

## Remaining security assumptions

The event chain detects changes to records supplied to validation, but does not
provide external timestamping, key signatures, durable storage, or protection
against an attacker who can replace an entire ledger and its trust anchor. The
subprocess sandbox remains explicitly **not** a real host isolation boundary.
The graph supports direct runtime checks (`exit_code`, `stdout_contains`, and
`not_timed_out`), sandboxed pytest-backed `tests_pass`, and the deliberately
minimal `passes_static_analysis` check. Static analysis does not replace a
full linter, type checker, security scanner, or tests.
# Metacognitive governance

When enabled, MAMV-IR records concise structured reasoning summaries, assumptions, uncertainty, alternatives, critiques, and snapshots. These are model inferences rather than observed evidence: sandbox, test-runner, and static-analyzer evidence retain their authority boundaries. Self-consistency is only a stability signal, never a vote that establishes truth. Communicability review makes a conclusion inspectable through its claim, evidence references, criterion, source, and limitations. The deliberation record is persisted with the ledger, but it neither exposes private chain-of-thought nor establishes consciousness, correctness, or faithful access to latent model computation. See [Metacognitive governance](docs/METACOGNITION.md).

## Informational Relativity

MAMV-IR treats verification as relative to an explicit informational frame: context, observer authority, evidence scope, verification method, acceptance criteria, artifact versions, policy, and time. A sandbox exit code can verify that a process exited successfully, but it cannot by itself verify that the user’s task was completed. Frames make those boundaries explicit, inspectable, serializable, and tamper-evident. Use `--show-frame`, `--frame-summary`, `--show-stale-results`, or `--export-frames PATH` to inspect a run without flooding normal output.

## Answer Informational Relativity

MAMV-IR can also record an answer relative to an explicit inference frame: model artifacts, selected context, retrieval scope, reasoning strategy, grounding configuration, and generation settings. The same question can produce different valid or invalid outputs under different frames. Frame metadata makes those conditions inspectable without claiming context-free truth or exposing private chain-of-thought. `Answer`, `InferenceFrame`, and their stable JSON helpers live in `agent.informational`; confidence signals remain separate self-report, consensus, grounding, retrieval-coverage, and coherence measures. For the MAMV-Model-to-MAMV handoff, `CandidateExport` provides a versioned candidate-only contract: it labels claim and evidence derivation, requires evidence density for generated material, preserves multi-strategy samples, and keeps fragmented chunk answers separate. See [the candidate export contract](docs/INFORMATIONAL_RELATIVITY.md#mamv-model-candidate-export-contract).
