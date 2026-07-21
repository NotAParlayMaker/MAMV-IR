"""Fast, offline smoke checks for prompt/context behavior; not a full eval harness."""
import json

from agent.graph import run_agent
from agent.llm import LLMBackend, LLMCallFailed
from agent.sandbox import SubprocessSandbox


class RecordingLLM(LLMBackend):
    def __init__(self, fence_after_retry=False):
        self.calls = []
        self.fence_after_retry = fence_after_retry

    def chat(self, messages, temperature=None):
        text = "\n".join(message["content"] for message in messages)
        self.calls.append((text, temperature))
        if "Interpret the goal as JSON" in text:
            return json.dumps({"normalized_goal": "print 42", "assumptions": [], "ambiguities": [], "acceptance_criteria": [{"description": "prints 42", "verification_method": "stdout_contains", "required": True, "expected_result": "42"}], "required_evidence": ["stdout"]})
        if "MISSING_CODE_FENCE" in text or "did not contain a complete" in text:
            return "```python\nprint('Result: 42')\n```" if self.fence_after_retry else "still prose"
        if "Write Python code" in text:
            return "prose without a fence" if self.fence_after_retry else "```python\nraise RuntimeError('boom')\n```"
        if "Diagnose failed criteria" in text:
            return "The supplied failure evidence says the criterion was not satisfied."
        if "Prior attempts" in text:
            return "```python\nprint('Result: 42')\n```"
        return "Plan for goal: print 42"


def test_temperatures_and_goal_are_present_in_offline_prompt_smoke_check():
    llm = RecordingLLM()
    state = run_agent("print 42", llm, SubprocessSandbox(), max_iterations=2)
    assert any("print 42" in text for text, _ in llm.calls)
    temperatures = {temperature for _, temperature in llm.calls}
    assert 0.5 in temperatures and 0.1 in temperatures
    diagnose_prompt = next(text for text, _ in llm.calls if "Diagnose failed criteria" in text)
    assert "Direct authoritative evidence evaluated." in diagnose_prompt
    repair_prompt = next(text for text, _ in llm.calls if "Prior attempts" in text)
    assert "Attempt 1:" in repair_prompt and "RuntimeError('boom')" in repair_prompt
    assert state["success"] is True


def test_missing_fence_retries_once_and_extracts_correct_code():
    llm = RecordingLLM(fence_after_retry=True)
    state = run_agent("print 42", llm, SubprocessSandbox(), max_iterations=1)
    assert state["success"] is True
    assert any("did not contain a complete" in text for text, _ in llm.calls)
    assert state["attempts"][0].code == "print('Result: 42')"


def test_never_fenced_output_abstains_with_identifiable_evidence():
    llm = RecordingLLM(fence_after_retry=False)
    # Make initial generation unfenced too, independently of repair paths.
    original = llm.chat
    def unfenced(messages, temperature=None):
        text = "\n".join(message["content"] for message in messages)
        if "Write Python code" in text or "did not contain a complete" in text:
            llm.calls.append((text, temperature)); return "unfenced prose"
        return original(messages, temperature)
    llm.chat = unfenced
    state = run_agent("print 42", llm, SubprocessSandbox(), max_iterations=1)
    assert state["completion_status"] == "model_output_unparseable"
    assert not state["attempts"]
    assert any(e.evidence_type == "model_output_unparseable" for e in state["evidence"])


def test_llm_unavailable_is_a_terminal_state_not_a_sandbox_failure():
    class Unavailable(LLMBackend):
        def chat(self, messages, temperature=None):
            raise LLMCallFailed("synthetic provider outage")
    state = run_agent("print 42", Unavailable(), SubprocessSandbox(), 1)
    assert state["completion_status"] == "llm_unavailable"
    assert not state["attempts"]
