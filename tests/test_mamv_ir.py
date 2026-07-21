import json
from agent.graph import run_agent
from agent.informational.constitution import review
from agent.informational.models import Claim, Context, Evidence, new_id
from agent.informational.serialization import deserialize_run, export_claim_evidence_graph, serialize_run
from agent.llm import LLMBackend, MockLLM, get_backend
from agent.sandbox import SubprocessSandbox

class ScriptedLLM(LLMBackend):
    def __init__(self, code, expected="42", malformed=False): self.code, self.expected, self.malformed, self.calls = code, expected, malformed, 0
    def chat(self, messages):
        text="\n".join(x["content"] for x in messages)
        if "Interpret the goal as JSON" in text:
            self.calls += 1
            if self.malformed and self.calls == 1: return "not json"
            return json.dumps({"normalized_goal":"print 42","assumptions":[],"ambiguities":[],"acceptance_criteria":[{"description":"exits","verification_method":"exit_code","required":True,"expected_result":"0"},{"description":"prints expected","verification_method":"stdout_contains","required":True,"expected_result":self.expected}],"required_evidence":["stdout","exit_code"]})
        if "planning" in text: return "PLAN: print the value"
        return f"```python\n{self.code}\n```"

def test_exit_zero_wrong_answer_is_not_success():
    state=run_agent("print 42", ScriptedLLM("print('Result: 41')"), SubprocessSandbox(), 1)
    assert not state["success"]
    assert state["attempts"][0].exit_code == 0
    assert any(not x.satisfied for x in state["verification_results"])

def test_evidenced_result_can_succeed():
    state=run_agent("print 42", ScriptedLLM("print('Result: 42')"), SubprocessSandbox(), 1)
    assert state["success"]

def test_exception_has_observation_and_diagnosis():
    state=run_agent("print 42", ScriptedLLM("raise RuntimeError('boom')"), SubprocessSandbox(), 2)
    assert any(e.evidence_type == "stderr" and "RuntimeError" in e.value for e in state["evidence"])
    assert any(c.claim_type == "interpretation" for c in state["claims"])

def test_failed_prediction_is_preserved_as_contradicted():
    state=run_agent("print 42", ScriptedLLM("print('Result: wrong')"), SubprocessSandbox(), 2)
    predictions=[c for c in state["claims"] if c.claim_type == "prediction"]
    assert predictions and any(c.status == "contradicted" for c in predictions)

def test_missing_observer_or_context_fails_review():
    state={"claims":[Claim(new_id("claim"),"bad","interpretation",None,None)],"acceptance_criteria":[],"verification_results":[]}
    violations=review(state)
    assert any("no observer" in x for x in violations) and any("no context" in x for x in violations)

def test_model_cannot_verify_unobserved_runtime_fact():
    c=Context(0,"goal")
    state={"claims":[Claim(new_id("claim"),"it ran","interpretation","reasoning_model",c,[],1,"verified")],"acceptance_criteria":[],"verification_results":[]}
    assert any("authority" in x for x in review(state))

def test_malformed_goal_json_falls_back_and_is_evidence():
    state=run_agent("print 42", ScriptedLLM("print('Result: 42')", malformed=True), SubprocessSandbox(), 1)
    assert state["evidence"][0].evidence_type == "model_output"
    assert state["success"]

def test_serialization_and_kimi_factory_contract():
    state=run_agent("fibonacci", MockLLM(), SubprocessSandbox(), 1)
    restored=deserialize_run(serialize_run(state))
    assert export_claim_evidence_graph(restored)["edges"]
    assert get_backend("mock").__class__.__name__ == "MockLLM"

def test_contradictory_evidence_is_retained():
    state=run_agent("print 42", ScriptedLLM("print('Result: 41')"), SubprocessSandbox(), 1)
    result=next(r for r in state["verification_results"] if not r.satisfied)
    assert result.contradictory_evidence_ids
    assert {e.evidence_id for e in state["evidence"]}.issuperset(result.contradictory_evidence_ids)


def test_kimi_adapter_remains_available():
    from agent.llm import KimiK3Backend
    assert KimiK3Backend.__name__ == "KimiK3Backend"
