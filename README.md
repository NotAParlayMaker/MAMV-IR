# Moonshot-Agent-X

An autonomous coding agent built around Kimi K3's chain-of-thought
reasoning: given a goal, it plans out loud, writes Python, runs that code
in a sandbox, reads the traceback if it fails, and fixes its own bugs —
looping until the goal is solved or a hard iteration budget is spent.

```
 goal ──▶ plan ──▶ generate_code ──▶ execute ──▶ evaluate ──success──▶ done
                        ▲                            │
                        │                         failure
                        │                            ▼
                        └──────────────────────── fix_code
                             (until max_iterations, then give up)
```

Every step is logged to a scratchpad, so the full reasoning trace — plan,
code, stdout/stderr, and each fix — is inspectable after the fact, not
just the final answer.

## Status

This is a working prototype, verified end-to-end with an offline mock LLM
(no API key needed to try it). Swap in a real `MOONSHOT_API_KEY` to run it
against actual Kimi K3. Test coverage: 8/8 passing, covering the
happy path, the self-correction path, and the give-up-gracefully path.

## Quick start

```bash
pip install -r requirements.txt

# Runs immediately, no API key required — uses the offline MockLLM
# and a resource-limited subprocess sandbox (Docker not required either).
python main.py --backend mock --sandbox subprocess "compute fibonacci"

# Watch it hit a real ZeroDivisionError and fix it:
python main.py --backend mock --sandbox subprocess "bug demo: division" --verbose
```

## Using the real Kimi K3 backend

```bash
cp .env.example .env
# edit .env, set MOONSHOT_API_KEY=your-key-here

python main.py "Write and run a script that finds all primes under 1000"
```

With no `--backend`/`--sandbox` flags, the CLI auto-selects: Kimi K3 if
`MOONSHOT_API_KEY` is set (otherwise the mock), and Docker if a daemon is
reachable (otherwise the subprocess fallback).

## Sandboxing

Two execution backends are provided:

- **`DockerSandbox`** (production): each attempt runs in a fresh,
  network-disabled container with memory and CPU limits, then the
  container is destroyed. This is the actual isolation boundary between
  LLM-written code and your machine — use this for anything beyond local
  experimentation.
- **`SubprocessSandbox`** (dev fallback): runs code as a local process
  with memory/CPU/timeout limits. Convenient when no Docker daemon is
  available, but it is **not** a security boundary — no filesystem or
  network isolation. Don't point it at untrusted goals in production.

Select explicitly with `--sandbox docker` / `--sandbox subprocess`, or
leave `--sandbox auto` to pick Docker whenever a daemon is reachable.

## Project layout

```
agent/
  state.py     # AgentState: the typed dict passed between graph nodes
  llm.py       # KimiK3Backend (real) + MockLLM (offline dev/test double)
  sandbox.py   # DockerSandbox (real) + SubprocessSandbox (dev fallback)
  graph.py     # The LangGraph StateGraph: plan/code/execute/evaluate/fix
main.py        # CLI entry point
tests/         # pytest suite, runs entirely offline against MockLLM
```

## Extending it

- **Give it tools beyond code execution** (web browsing, terminal
  commands, file I/O): add new nodes to the graph in `agent/graph.py` and
  extend `AgentState` with whatever context those tools need. The
  plan/execute/evaluate/fix skeleton doesn't change.
- **Multi-file projects instead of single scripts**: `SubprocessSandbox`
  and `DockerSandbox` already run in an isolated temp dir/container — swap
  `code: str` for a dict of `{filename: contents}` and adjust `run()` to
  write multiple files before executing the entrypoint.
- **Longer-running goals**: LangGraph supports checkpointing
  (`langgraph-checkpoint`, already in requirements.txt) so a run can be
  paused and resumed instead of living entirely in one process — useful
  once `max_iterations` or wall-clock budgets get large.

## Known limitations of this prototype

- `MockLLM` only knows how to "fix" the one deliberately-injected bug
  demo; it's a development/test double, not a general code-fixing model.
  Real self-correction behavior only shows up with the Kimi K3 backend.
- No retry/backoff on the Kimi K3 API calls yet — a transient network
  failure will currently propagate as an exception rather than being
  treated as a recoverable sandbox-style failure.
- The fix loop only ever sees the single most recent failure, not the
  full history of prior attempts — fine for shallow bugs, but it can
  re-try a fix it already effectively attempted on a harder, multi-bug
  script. Feeding `state["attempts"]` (not just the last one) into the
  fix prompt is the natural next improvement.
