import httpx
import pytest
from openai import APIConnectionError

from agent.llm import KimiK3Backend, LLMCallFailed


class FakeCompletions:
    def __init__(self, failures): self.failures, self.calls = failures, 0
    def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise APIConnectionError(request=httpx.Request("POST", "https://example.test"))
        return type("Response", (), {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "ok"})()})()]})()


def backend(failures):
    value = object.__new__(KimiK3Backend)
    value.model, value.temperature, value.max_retries, value.retry_backoff_seconds = "fake", 0.3, 2, 0
    completions = FakeCompletions(failures)
    value._client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    return value, completions


def test_real_backend_retries_transient_error_then_recovers():
    value, completions = backend(2)
    assert value.chat([], temperature=0.1) == "ok"
    assert completions.calls == 3


def test_real_backend_raises_named_error_after_retry_exhaustion():
    value, completions = backend(3)
    with pytest.raises(LLMCallFailed):
        value.chat([])
    assert completions.calls == 3
