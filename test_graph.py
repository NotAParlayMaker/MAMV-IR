"""Tests for the plan/code/execute/fix loop, using the offline MockLLM so
these run with no network access or API key."""

from agent.llm import MockLLM, LLMBackend
from agent.sandbox import SubprocessSandbox
from agent.graph import run_agent


def test_succeeds_on_first_attempt():
    state = run_agent("fibonacci", MockLLM(), SubprocessSandbox(), max_iterations=3)
    assert state["success"] is True
    assert state["iteration"] == 1
    assert "34" in state["final_answer"]  # fib(9) == 34, present in the printed list


def test_self_corrects_after_a_sandbox_error():
    state = run_agent("bug demo: division", MockLLM(), SubprocessSandbox(), max_iterations=3)
    assert state["success"] is True
    assert state["iteration"] == 2  # first attempt fails, second (fixed) attempt succeeds
    assert state["attempts"][0]["success"] is False
    assert "ZeroDivisionError" in state["attempts"][0]["stderr"]
    assert state["attempts"][1]["success"] is True


class StubbornMockLLM(MockLLM):
    """Never produces working code — used to test the give-up path."""

    def chat(self, messages):
        joined = "\n".join(m["content"] for m in messages)
        if "You are planning" in joined:
            return "PLAN:\n1. Fail on purpose."
        return "```python\nraise RuntimeError('always broken')\n```"


def test_gives_up_after_max_iterations():
    state = run_agent("unfixable task", StubbornMockLLM(), SubprocessSandbox(), max_iterations=3)
    assert state["success"] is False
    assert state["completion_status"] == "stuck_in_loop"
    assert "repeats" in state["final_answer"]


def test_repeated_repair_abstains_before_another_sandbox_run():
    class RepeatingRepairLLM(MockLLM):
        def chat(self, messages):
            joined = "\n".join(message["content"] for message in messages)
            if "You are planning" in joined:
                return "PLAN: deliberately fail."
            return "```python\nraise RuntimeError('same broken code')\n```"

    state = run_agent("unfixable task", RepeatingRepairLLM(), SubprocessSandbox(), max_iterations=5)
    assert state["completion_status"] == "stuck_in_loop"
    assert len(state["attempts"]) == 1


def test_llm_backend_is_swappable():
    """Any LLMBackend subclass should work with run_agent — this guards
    against the graph accidentally depending on MockLLM internals."""

    class EchoLLM(LLMBackend):
        def chat(self, messages):
            joined = "\n".join(m["content"] for m in messages)
            if "You are planning" in joined:
                return "PLAN:\n1. Print a constant."
            return "```python\nprint('Result: 42')\n```"

    state = run_agent("anything", EchoLLM(), SubprocessSandbox(), max_iterations=1)
    assert state["success"] is True
    assert "42" in state["final_answer"]
