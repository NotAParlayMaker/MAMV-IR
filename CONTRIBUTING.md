# Contributing to MAMV-IR

## Local checks

Create an environment with the package and development tools, then run the same checks as CI:

```bash
pip install -e .
pytest -q
python -m compileall agent tests
```

The mock backend and subprocess sandbox keep these checks offline; no API key or Docker daemon is required.

## Adding an LLM backend

Add an adapter in `agent/llm.py` that implements the provider-neutral `LLMBackend` interface: `chat(messages) -> str`. Keep provider authentication, request formatting, and response parsing in that adapter. Do not put provider-specific code or governance behavior in `agent/graph.py`; the graph depends only on the interface.

## Adding observers and authority rules

Add observer policy in `agent/informational/observers.py`. In particular, extend `authorize_claim_verification` with a narrow rule for the new observer (for example, `code_reviewer`). Its decision should account for the requested verified status, observer identity, claim type, evidence type, and verification method. Authority is not granted by confidence alone: only the observer/evidence/method combinations explicitly authorized by the matrix may verify a claim. Add adversarial tests for both permitted and prohibited combinations.

## Adding verification methods

Add the evaluator branch for a new `verification_method` in `verify()` in `agent/graph.py`, alongside its authoritative evidence producer and observer authorization. An unimplemented method must fail with a distinct, explicit message; it must never silently fall through to an "uncertain" result.

## Style and governance-critical changes

`agent/graph.py` contains legacy dense one-line Python. Treat that as existing code, not a style to copy: write new code as normal, clear multi-line Python.

`agent/informational/` is governance-critical. Pull requests that touch it must add a new adversarial test in `tests/test_governance_hardening.py`, rather than only updating existing tests.
