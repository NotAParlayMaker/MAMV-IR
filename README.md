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

Every run records JSON-serializable `Context`, `Evidence`, `Claim`, `AcceptanceCriterion`, `VerificationResult`, immutable `ExecutionAttempt`, and chronological `LedgerEvent` records. Sandbox observations authoritatively establish stdout, stderr, exit code, and timeout only. Test runners and static analyzers own their respective results. The reasoning model cannot verify an unobserved runtime fact.

Required criteria are evaluated independently. Completion requires an execution, every required criterion supported at the configurable `MAMV_IR_CONFIDENCE_THRESHOLD` (default `0.80`), no contradiction, and a passing constitutional review. Failed diagnoses and repair predictions are retained and marked contradicted rather than erased.

### Example

For a goal that requires `Result: 42`, a program that prints `Result: 41` and exits `0` produces valid sandbox evidence but fails the stdout criterion, so the run is rejected and diagnosed. A program that exits `0` *and* prints `Result: 42` can finish after constitutional review.

## Run locally

```bash
pip install -r requirements.txt
python main.py --backend mock --sandbox subprocess fibonacci
python main.py --backend mock --sandbox subprocess "bug demo: division" --verbose
```

The offline `MockLLM` is deterministic and all tests run without an API key or network.

## Kimi and other providers

Kimi remains supported through `KimiK3Backend`, using Moonshot's OpenAI-compatible API:

```bash
export MOONSHOT_API_KEY=your-key
# optional: export MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
python main.py --backend kimi --sandbox subprocess "Write a Python program"
```

To add another provider, implement the provider-neutral `LLMBackend.chat(messages) -> str` interface in `agent/llm.py`; do not add governance behavior to the adapter. The graph depends only on that interface.

## Persistence helpers

`agent.informational.serialization` exposes `serialize_run`, `deserialize_run`, `export_claim_evidence_graph`, and `chronological_ledger`. These support later durable storage without changing the in-memory model.

## Current limitations

- Acceptance criteria are currently deterministic methods (`exit_code` and `stdout_contains`) plus an explicit-evidence fallback; richer test and static-analysis integrations are future work.
- Generated code is still a single Python script.
- The subprocess sandbox is a development fallback, not a host-security boundary; use Docker for untrusted code.
- A model can propose a weak or ambiguous goal interpretation, but ambiguity is retained and cannot silently satisfy missing evidence.
