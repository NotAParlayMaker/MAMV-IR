"""Run MAMV-IR as a library and inspect its claim/evidence graph."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python examples/inspect_a_run.py` from a source checkout before install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.graph import run_agent
from agent.informational.serialization import export_claim_evidence_graph
from agent.llm import get_backend
from agent.sandbox import get_sandbox


def main() -> None:
    state = run_agent(
        "fibonacci",
        get_backend("mock"),
        get_sandbox("subprocess"),
    )
    print(json.dumps(export_claim_evidence_graph(state), indent=2))


if __name__ == "__main__":
    main()
