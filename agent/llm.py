"""LLM backend for Moonshot-Agent-X.

Kimi K3 (Moonshot AI) exposes an OpenAI-compatible chat completions API, so
we talk to it through the `openai` SDK pointed at Moonshot's base URL. A
MockLLM is included so the graph/sandbox loop can be developed and tested
end-to-end without a live API key or network access.
"""

from __future__ import annotations

import os
import re
import time
from abc import ABC, abstractmethod
from typing import List, Dict


class LLMCallFailed(RuntimeError):
    """Raised when the real provider remains unavailable after retries."""


class LLMBackend(ABC):
    """Minimal interface every LLM backend must satisfy."""

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], temperature: float | None = None) -> str:
        """Send a list of {role, content} messages, return the reply text."""
        raise NotImplementedError


class KimiK3Backend(LLMBackend):
    """Talks to Kimi K3 via Moonshot AI's OpenAI-compatible endpoint.

    Requires MOONSHOT_API_KEY. Base URL defaults to Moonshot's global
    endpoint; override with MOONSHOT_BASE_URL for the .cn endpoint or a
    proxy.
    """

    def __init__(
        self,
        model: str = "kimi-k3",
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.3,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.1,
    ):
        from openai import (
            OpenAI,
        )  # local import so MockLLM path needs no dep at import time

        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        api_key = api_key or os.environ.get("MOONSHOT_API_KEY")
        if not api_key:
            raise RuntimeError("MOONSHOT_API_KEY is not set. Export it or pass api_key= explicitly.")
        base_url = base_url or os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1")
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(self, messages: List[Dict[str, str]], temperature: float | None = None) -> str:
        """Retry SDK-defined transient API failures, preserving per-call temperature."""
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

        transient_errors = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature if temperature is None else temperature,
                )
                return response.choices[0].message.content or ""
            except transient_errors as exc:
                if attempt == self.max_retries:
                    raise LLMCallFailed(
                        f"Kimi K3 remained unavailable after {attempt + 1} attempts: {exc}"
                    ) from exc
                time.sleep(self.retry_backoff_seconds * (2**attempt))


class MockLLM(LLMBackend):
    """Deterministic offline stand-in for Kimi K3.

    Lets the whole plan -> code -> execute -> fix loop be exercised without
    network access or an API key. It follows a simple, inspectable script:
    on the first call it plans and writes code for the given goal; on
    subsequent calls (after a sandbox error is fed back in) it "fixes" the
    most common toy bugs it's asked about. Swap KimiK3Backend in for real
    use; this class exists purely for local development and tests.
    """

    def __init__(self):
        self._call_count = 0

    def chat(self, messages: List[Dict[str, str]], temperature: float | None = None) -> str:
        self._call_count += 1
        joined = "\n".join(m["content"] for m in messages)

        if "Write Python code" in joined or "PLAN:" in joined and "CODE:" not in joined:
            pass  # fallthrough handled below by node-specific prompting

        if "Interpret the goal as JSON" in joined:
            goal = _extract_goal(joined)
            expected = (
                "34"
                if "fibonacci" in goal.lower()
                else ("10" if "bug demo" in goal.lower() else ("42" if "42" in goal else "Result:"))
            )
            import json

            return json.dumps(
                {
                    "normalized_goal": goal,
                    "assumptions": [],
                    "ambiguities": [] if expected != "Result:" else ["The precise expected output is not specified."],
                    "acceptance_criteria": [
                        {
                            "description": "Program exits without a runtime error",
                            "verification_method": "exit_code",
                            "required": True,
                            "expected_result": "0",
                        },
                        {
                            "description": "Program prints the expected result",
                            "verification_method": "stdout_contains",
                            "required": True,
                            "expected_result": expected,
                        },
                    ],
                    "required_evidence": ["exit_code", "stdout"],
                }
            )

        if "You are planning" in joined:
            goal = _extract_goal(joined)
            return (
                "PLAN:\n"
                f"1. Understand the goal: {goal}\n"
                "2. Write a small, self-contained Python script that solves it.\n"
                "3. Print the final result clearly to stdout.\n"
                "4. Run it in the sandbox and check for errors.\n"
                "5. If it fails, read the traceback and fix the specific bug."
            )

        if "Write Python code" in joined:
            goal = _extract_goal(joined)
            return _mock_code_for_goal(goal)

        if "traceback" in joined.lower() or "fix" in joined.lower():
            # naive "fix": strip a deliberately-injected bug marker if present
            prev_code = _extract_code_block(joined)
            fixed = prev_code.replace("BUGGY_DIVISOR = 0", "BUGGY_DIVISOR = 1")
            return f"```python\n{fixed}\n```"

        return "I don't have a scripted response for this prompt shape."


def _extract_goal(text: str) -> str:
    match = re.search(r"Goal:\s*(.+)", text)
    return match.group(1).strip() if match else "unspecified goal"


def _extract_code_block(text: str) -> str:
    match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    return match.group(1) if match else ""


def _mock_code_for_goal(goal: str) -> str:
    """Returns toy code. If the goal mentions 'bug demo', injects a
    deliberate ZeroDivisionError so the self-correction loop has something
    real to fix on the first pass."""
    if "bug demo" in goal.lower():
        code = "BUGGY_DIVISOR = 0\ndef compute():\n    return 10 / BUGGY_DIVISOR\nprint('Result:', compute())\n"
    elif "fibonacci" in goal.lower():
        code = (
            "def fib(n):\n"
            "    a, b = 0, 1\n"
            "    for _ in range(n):\n"
            "        a, b = b, a + b\n"
            "    return a\n"
            "print('Result:', [fib(i) for i in range(10)])\n"
        )
    else:
        code = (
            "# Generic fallback for goals the mock doesn't recognize.\n"
            "print('Result: mock backend has no scripted solution for this goal')\n"
        )
    return f"```python\n{code}```"


def get_backend(name: str = "auto") -> LLMBackend:
    """Factory: 'kimi' forces the real backend, 'mock' forces the offline
    one, 'auto' uses Kimi if MOONSHOT_API_KEY is set, otherwise falls back
    to the mock so the framework is runnable out of the box."""
    if name == "mock":
        return MockLLM()
    if name == "kimi":
        return KimiK3Backend()
    if os.environ.get("MOONSHOT_API_KEY"):
        return KimiK3Backend()
    return MockLLM()
