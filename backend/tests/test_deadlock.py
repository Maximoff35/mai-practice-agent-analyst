import httpx
import pytest
from fastapi.testclient import TestClient

from analyst import AnalystAgent, MAIProvider, OpenRouterProvider
from api.main import app, get_agent
from model_checker import TLCConfig, VerificationStatus, generate_tla, validate_model, verify
from model_checker.parser import parse_tlc_output


def state_is(value):
    return {"eq": [{"var": "phase"}, value]}


def workflow():
    return {
        "variables": [{"name": "phase", "type": "enum", "values": ["Ready", "Done", "Stuck"]}],
        "initial": {"phase": "Ready"},
        "transitions": [{"name": "Finish", "guard": state_is("Ready"), "effects": [{"set": ["phase", "Done"]}]}],
        "properties": [{"name": "NoDeadlock", "type": "deadlock_free"}],
    }


@pytest.mark.integration
@pytest.mark.parametrize("variant,status,path", [
    ("blocked", "PROPERTY_VIOLATED", ["Ready", "Done"]),
    ("initial", "PROPERTY_VIOLATED", ["Stuck"]),
    ("terminal", "PROPERTY_HOLDS", []),
    ("cycle", "PROPERTY_HOLDS", []),
    ("business_self_loop", "PROPERTY_HOLDS", []),
    ("unreachable_blocked", "PROPERTY_HOLDS", []),
    ("terminal_has_exit", "PROPERTY_VIOLATED", ["Ready", "Done", "Stuck"]),
    ("terminal_true", "PROPERTY_HOLDS", []),
    ("terminal_false", "PROPERTY_VIOLATED", ["Ready", "Done"]),
])
def test_deadlock_semantics_with_real_tlc(configured_tlc, variant, status, path):
    model = workflow()
    if variant == "initial":
        model["initial"]["phase"] = "Stuck"
    if variant in {"terminal", "terminal_has_exit"}:
        model["properties"][0]["terminal_states"] = state_is("Done")
    if variant in {"terminal_true", "terminal_false"}:
        model["properties"][0]["terminal_states"] = variant == "terminal_true"
    if variant == "cycle":
        model["transitions"].append({"name": "Restart", "guard": state_is("Done"), "effects": [{"set": ["phase", "Ready"]}]})
    if variant == "business_self_loop":
        model["transitions"][0]["guard"] = True
    if variant == "unreachable_blocked":
        model["transitions"][0]["effects"] = [{"set": ["phase", "Ready"]}]
    if variant == "terminal_has_exit":
        model["transitions"].append({"name": "Fail", "guard": state_is("Done"), "effects": [{"set": ["phase", "Stuck"]}]})
    result = verify(model)
    assert result.status.value == status, result.stdout + result.stderr
    assert [state.values["phase"] for state in result.deadlock_path] == path
    assert not result.counterexample and not result.witness
    item = result.property_results[0]
    assert item.deadlock_path == result.deadlock_path
    if len(path) == 2:
        assert [state.transition for state in result.deadlock_path] == [None, "Finish"]


@pytest.mark.integration
@pytest.mark.parametrize("name", ["Created", "Cancelled", "Done"])
def test_terminal_state_is_not_inferred_from_its_name(configured_tlc, name):
    model = workflow()
    if name != "Done":
        model["variables"][0]["values"].append(name)
    model["initial"]["phase"] = name
    result = verify(model)
    assert result.status == VerificationStatus.PROPERTY_VIOLATED
    assert len(result.deadlock_path) == 1


@pytest.mark.integration
@pytest.mark.parametrize("deadlock_first", [True, False])
def test_mixed_properties_are_not_hidden_by_deadlock(configured_tlc, deadlock_first):
    model = workflow()
    others = [
        {"name": "CanFinish", "type": "reachable", "expression": state_is("Done")},
        {"name": "AlwaysReady", "type": "invariant", "expression": state_is("Ready")},
    ]
    model["properties"] = model["properties"] + others if deadlock_first else others + model["properties"]
    result = verify(model)
    results = {item.property_name: item for item in result.property_results}
    assert results["CanFinish"].status == VerificationStatus.PROPERTY_HOLDS
    assert results["AlwaysReady"].status == VerificationStatus.PROPERTY_VIOLATED
    assert results["NoDeadlock"].status == VerificationStatus.PROPERTY_VIOLATED
    assert len(results["CanFinish"].witness) == len(results["AlwaysReady"].counterexample) == len(results["NoDeadlock"].deadlock_path) == 2
    assert result.status == VerificationStatus.PROPERTY_VIOLATED


@pytest.mark.integration
def test_real_deadlock_timeout_does_not_confirm_safety(configured_tlc):
    result = verify(workflow(), TLCConfig.from_env().model_copy(update={"timeout_seconds": 0.001}))
    assert result.status == VerificationStatus.TIMEOUT
    assert result.property_results[0].status == VerificationStatus.TIMEOUT
    assert not result.deadlock_path


@pytest.mark.integration
def test_api_preserves_deadlock_references_when_explanation_fails(configured_tlc):
    model = workflow()
    model["properties"][0]["source_reference"] = {"id": "R1", "fragment": "Блокировки запрещены"}
    model["transitions"][0]["source_reference"] = {"id": "R2", "fragment": "Завершить процесс"}
    class Provider:
        def build_model(self, requirements):
            return validate_model(model)
        def explain_result(self, requirements, model, result):
            raise RuntimeError("LLM failed")
    app.dependency_overrides[get_agent] = lambda: AnalystAgent(Provider())
    try:
        response = TestClient(app).post("/api/analyze", json={"requirements": "[R1] Блокировки запрещены. [R2] Завершить процесс."})
    finally:
        app.dependency_overrides.pop(get_agent, None)
    body = response.json()
    assert response.status_code == 200
    assert body["counterexample"] is None
    assert body["verification_result"]["counterexample"] == []
    assert [item["id"] for item in body["related_requirements"]] == ["R1", "R2"]
    assert body["verification_result"]["deadlock_path"][1]["related_requirements"][0]["id"] == "R2"
    assert "Шаблонное сообщение" in body["explanation"]


@pytest.mark.parametrize("prop", [
    {"name": "P", "type": "deadlock_free", "expression": True},
    {"name": "P", "type": "deadlock_free", "terminal_states": {"var": "missing"}},
    {"name": "P", "type": "deadlock_free", "terminal_states": {"var": "phase"}},
    {"name": "P", "type": "deadlock_free", "terminal_states": {"eq": [{"var": "phase"}, "Unknown"]}},
    {"name": "P", "type": "invariant"},
    {"name": "P", "type": "reachable", "expression": True, "terminal_states": False},
])
def test_invalid_property_is_rejected_before_tlc(prop, monkeypatch):
    model = workflow()
    model["properties"] = [prop]
    monkeypatch.setattr("model_checker.runner.subprocess.Popen", lambda *args, **kwargs: pytest.fail("TLC started"))
    assert verify(model).status == VerificationStatus.MODEL_INVALID


def test_deadlock_generation_excludes_stutter_from_enabled_actions():
    files = generate_tla(workflow())
    assert "BusinessNext ==\n  \\/ Step_Finish" in files.tla
    assert "ENABLED BusinessNext" in files.tla
    assert "UNCHANGED vars" not in files.tla.split("BusinessNext ==")[1].split("Next ==")[0]
    assert "INVARIANT Property_NoDeadlock" in files.cfg
    model = workflow()
    model["properties"].append({"name": "Safe", "type": "invariant", "expression": True})
    with pytest.raises(ValueError, match="verify"):
        generate_tla(model)


@pytest.mark.parametrize("output,code,timed_out,status", [
    ("Model checking completed. No error has been found.", 0, False, "PROPERTY_HOLDS"),
    ("Model checking completed. No error has been found.", 1, False, "ENGINE_ERROR"),
    ("Model checking completed. No error has been found.", 0, True, "TIMEOUT"),
    ("State limit reached", 0, False, "STATE_LIMIT_REACHED"),
    ("Error: Deadlock reached.", 11, False, "ENGINE_ERROR"),
    ("Error: Invariant Property_NoDeadlock is violated.", 12, False, "ENGINE_ERROR"),
    ('Error: Invariant Property_NoDeadlock is violated.\nState 1: <Initial predicate>\nv_phase = "Ready"', 12, False, "ENGINE_ERROR"),
])
def test_parser_does_not_invent_deadlock_paths(output, code, timed_out, status):
    result = parse_tlc_output(output, "", code, timed_out=timed_out, model=validate_model(workflow()))
    assert result.status.value == status
    assert not result.deadlock_path


@pytest.mark.parametrize("provider_class", [MAIProvider, OpenRouterProvider])
def test_both_providers_accept_deadlock_contract(provider_class):
    import json
    model = workflow()
    model["properties"][0]["terminal_states"] = state_is("Done")
    def handler(request):
        instructions = json.loads(request.content)["messages"][0]["content"]
        assert "deadlock_free" in instructions and "terminal_states" in instructions
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(model)}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = provider_class("test-key", "test-model", client=client).build_model("Явно допустимо завершение Done")
    assert result.properties[0].terminal_states.root == state_is("Done")
