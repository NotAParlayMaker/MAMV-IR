#!/usr/bin/env python3
"""Command-line entry point for MAMV-IR.

Usage:
    python main.py "Compute the first 10 Fibonacci numbers"
    python main.py --backend mock --sandbox subprocess "bug demo: divide by a bad divisor"
    python main.py --backend kimi --sandbox docker "Scrape example.com and count the links"

With no flags, the LLM backend auto-selects Kimi K3 if MOONSHOT_API_KEY is
set (otherwise the offline mock), and the sandbox auto-selects Docker if a
daemon is reachable (otherwise the subprocess fallback).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent.graph import run_agent
from agent.informational.serialization import serialize_run
from agent.llm import get_backend
from agent.sandbox import get_sandbox


def _claims_for_evidence(final_state: dict, evidence_ids: tuple[str, ...]) -> list[object]:
    """Return claims connected to the evidence used by a verification result."""
    involved = set(evidence_ids)
    return [
        claim
        for claim in final_state.get("claims", [])
        if involved.intersection(claim.evidence_ids)
    ]


def print_receipt(final_state: dict) -> None:
    """Print a concise, human-readable summary of governance completion."""
    criteria = {criterion.criterion_id: criterion for criterion in final_state.get("acceptance_criteria", [])}

    print("\n--- governance receipt ---")
    print(f"completion status: {final_state.get('completion_status', 'unknown')}")
    results = final_state.get("verification_results", [])
    if not results:
        print("acceptance criteria: no verification results recorded")
    for result in results:
        criterion = criteria.get(result.criterion_id)
        description = criterion.description if criterion else result.criterion_id
        status = "satisfied" if result.satisfied else "not satisfied"
        required = "required" if criterion and criterion.required else "optional"
        print(f"- [{status}] {description} ({required}; confidence {result.confidence:.2f})")
        print(f"  verification: {result.explanation}")
        claims = _claims_for_evidence(
            final_state,
            result.supporting_evidence_ids + result.contradictory_evidence_ids,
        )
        if claims:
            print("  claims involved:")
            for claim in claims:
                print(f"    - {claim.claim_id} [{claim.status}, {claim.confidence:.2f}]: {claim.statement}")
        elif result.supporting_evidence_ids or result.contradictory_evidence_ids:
            print("  claims involved: none")

    violations = final_state.get("constitutional_violations", [])
    print("constitutional violations:")
    if violations:
        for violation in violations:
            print(f"- {violation}")
    else:
        print("- none")


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="MAMV-IR: evidence-governed reasoning")
    parser.add_argument("goal", help="The task to solve")
    parser.add_argument(
        "--backend", choices=["auto", "kimi", "mock"], default="auto", help="LLM backend"
    )
    parser.add_argument(
        "--sandbox", choices=["auto", "docker", "subprocess"], default="auto", help="Execution sandbox"
    )
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--verbose", action="store_true", help="Print the full reasoning scratchpad")
    parser.add_argument(
        "--receipt",
        action="store_true",
        help="Print acceptance-criterion and constitutional-review details",
    )
    parser.add_argument(
        "--save-run",
        metavar="PATH",
        help="Write the complete serialized run record to PATH",
    )
    args = parser.parse_args()

    llm = get_backend(args.backend)
    sandbox = get_sandbox(args.sandbox)

    print(f"[moonshot-agent-x] backend={type(llm).__name__} sandbox={type(sandbox).__name__}")
    print(f"[moonshot-agent-x] goal: {args.goal}\n")

    final_state = run_agent(args.goal, llm, sandbox, max_iterations=args.max_iterations)

    if args.verbose:
        print("\n--- reasoning trace ---")
        for entry in final_state["scratchpad"]:
            print(entry)
            print("-" * 40)

    print("\n--- result ---")
    print(f"success: {final_state['success']}")
    print(f"iterations used: {final_state['iteration']}")
    print(final_state["final_answer"])

    if args.receipt:
        print_receipt(final_state)

    if args.save_run:
        destination = Path(args.save_run)
        try:
            destination.write_text(serialize_run(final_state), encoding="utf-8")
        except OSError as error:
            print(f"Could not save run to {destination}: {error}", file=sys.stderr)
            return 1
        print(f"\nSaved full run record to {destination}")

    return 0 if final_state["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
