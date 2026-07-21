#!/usr/bin/env python3
"""CLI entry point for Moonshot-Agent-X.

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

from dotenv import load_dotenv

from agent.graph import run_agent
from agent.llm import get_backend
from agent.sandbox import get_sandbox


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Moonshot-Agent-X: an autonomous reasoning agent")
    parser.add_argument("goal", help="The task to solve")
    parser.add_argument(
        "--backend", choices=["auto", "kimi", "mock"], default="auto", help="LLM backend"
    )
    parser.add_argument(
        "--sandbox", choices=["auto", "docker", "subprocess"], default="auto", help="Execution sandbox"
    )
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--verbose", action="store_true", help="Print the full reasoning scratchpad")
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

    return 0 if final_state["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
