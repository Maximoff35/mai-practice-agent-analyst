from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from analyst import AnalystAgent
from api.main import app, get_agent
from model_checker import TLCConfig, VerificationResult, VerificationStatus, generate_tla, validate_model, verify
from model_checker.parser import parse_tlc_output


def goal(expression, name="Goal"):
    return {"name": name, "type": "reachable", "expression": expression}


def status_is(value):
    return {"eq": [{"var": "status"}, value]}


@pytest.mark.integration
@pytest.mark.parametrize("target,length", [(True, 2), (False, 1)])
def test_single_variable_tlc_trace(configured_tlc, target, length):
    model = {
        "variables": [{"name": "ready", "type": "boolean"}],
        "initial": {"ready": False},
        "transitions": [{"name": "Prepare", "guard": {"not": {"var": "ready"}},
                         "effects": [{"set": ["ready", True]}]}],
        "properties": [goal({"eq": [{"var": "ready"}, target]})],
    }
    result = verify(model)
    assert result.status == VerificationStatus.PROPERTY_HOLDS, result.stdout
    assert len(result.witness) == length
    assert result.witness[-1].values == {"ready": target}


@pytest.mark.integration
@pytest.mark.parametrize("expression,status,states", [
    (status_is("Executed"), "PROPERTY_HOLDS", ["Created", "Approved", "Executed"]),
    (status_is("Created"), "PROPERTY_HOLDS", ["Created"]),
    ({"and": [status_is("Cancelled"), {"var": "approved"}]}, "PROPERTY_VIOLATED", []),
    (False, "PROPERTY_VIOLATED", []),
    (True, "PROPERTY_HOLDS", ["Created"]),
])
def test_reachable_with_real_tlc(fixed_model, configured_tlc, expression, status, states):
    fixed_model["properties"] = [goal(expression)]
    result = verify(fixed_model)
    assert result.status.value == status, result.stdout + result.stderr
    assert [state.values["status"] for state in result.witness] == states
    assert result.counterexample == []
    assert result.property_results[0].status == result.status
    if states:
        assert result.witness[0].transition is None
    if len(states) == 3:
        assert [state.transition for state in result.witness] == [None, "Approve", "Execute"]


@pytest.mark.integration
@pytest.mark.parametrize("goal_first", [True, False])
def test_reachable_does_not_hide_violated_invariant(buggy_model, configured_tlc, goal_first):
    target = goal(status_is("Executed"))
    if goal_first:
        buggy_model["properties"].insert(0, target)
    else:
        buggy_model["properties"].append(target)
    result = verify(buggy_model)
    assert result.status == VerificationStatus.PROPERTY_VIOLATED, result.stdout
    by_name = {item.property_name: item for item in result.property_results}
    assert by_name["Goal"].status == VerificationStatus.PROPERTY_HOLDS
    assert [state.values["status"] for state in by_name["Goal"].witness] == ["Created", "Approved", "Executed"]
    assert by_name["NoExecutedAfterCancel"].status == VerificationStatus.PROPERTY_VIOLATED
    assert [state.transition for state in result.counterexample] == [None, "Approve", "Cancel", "Execute"]
    assert result.witness == []
    assert result.statistics.distinct_states is None


@pytest.mark.integration
def test_multiple_targets_are_independent(fixed_model, configured_tlc):
    fixed_model["properties"] = [goal(status_is("Created"), "Initial"), goal(False, "Impossible")]
    result = verify(fixed_model)
    assert result.status == VerificationStatus.PROPERTY_VIOLATED
    assert result.violated_property == "Impossible"
    assert [item.status.value for item in result.property_results] == ["PROPERTY_HOLDS", "PROPERTY_VIOLATED"]
    assert len(result.property_results[0].witness) == 1
    assert result.counterexample == []


@pytest.mark.integration
def test_reachable_timeout_is_unknown(fixed_model, configured_tlc):
    fixed_model["properties"] = [goal(False)]
    config = TLCConfig.from_env().model_copy(update={"timeout_seconds": 0.001})
    result = verify(fixed_model, config)
    assert result.status == VerificationStatus.TIMEOUT
    assert result.property_results[0].status == VerificationStatus.TIMEOUT
    assert not result.witness and not result.counterexample


@pytest.mark.integration
def test_api_preserves_witness_and_references(fixed_model, configured_tlc):
    target = goal(status_is("Executed"))
    target["source_reference"] = {"id": "R1", "fragment": "Возможно исполнить заявку"}
    fixed_model["properties"] = [target]
    fixed_model["transitions"][0]["source_reference"] = {"id": "R2", "fragment": "Согласовать заявку"}
    class Provider:
        def build_model(self, requirements):
            return validate_model(fixed_model)
        def explain_result(self, requirements, model, result):
            raise RuntimeError("Проверяем сохранение пути при сбое объяснения")
    app.dependency_overrides[get_agent] = lambda: AnalystAgent(Provider())
    try:
        response = TestClient(app).post("/api/analyze", json={
            "requirements": "[R1] Возможно исполнить заявку. [R2] Согласовать заявку.",
        })
    finally:
        app.dependency_overrides.pop(get_agent, None)
    assert response.status_code == 200
    body = response.json()
    assert body["counterexample"] is None
    assert len(body["verification_result"]["witness"]) == 3
    item = body["verification_result"]["property_results"][0]
    assert [ref["id"] for ref in item["related_requirements"]] == ["R1", "R2"]
    assert item["witness"][1]["related_requirements"][0]["id"] == "R2"
    assert "Шаблонное сообщение" in body["explanation"]


def test_reachable_generation_and_invalid_expression(fixed_model, monkeypatch):
    fixed_model["properties"] = [goal(status_is("Executed"))]
    files = generate_tla(fixed_model)
    assert 'Property_Goal == ~((v_status = "Executed"))' in files.tla
    assert "INVARIANT Property_Goal" in files.cfg
    mixed = deepcopy(fixed_model)
    mixed["properties"].append(goal(False, "Another"))
    with pytest.raises(ValueError, match="verify"):
        generate_tla(mixed)
    monkeypatch.setattr("model_checker.runner.subprocess.Popen", lambda *args, **kwargs: pytest.fail("TLC started"))
    fixed_model["properties"][0]["expression"] = {"var": "unknown"}
    assert verify(fixed_model).status == VerificationStatus.MODEL_INVALID


@pytest.mark.parametrize("output,exit_code,timed_out,status", [
    ("Model checking completed. No error has been found.", 0, False, "PROPERTY_VIOLATED"),
    ("Model checking completed. No error has been found.", 1, False, "ENGINE_ERROR"),
    ("Model checking completed. No error has been found.", 0, True, "TIMEOUT"),
    ("State limit reached", 0, False, "STATE_LIMIT_REACHED"),
    ("Finished", 0, False, "ENGINE_ERROR"),
    ("Error: Invariant TypeOK is violated.", 12, False, "ENGINE_ERROR"),
    ("Error: Invariant Property_Goal is violated.", 12, False, "ENGINE_ERROR"),
    ('Error: Invariant Property_Goal is violated.\nState 1: <Initial predicate>\n/\\ v_status = "Created"', 12, False, "ENGINE_ERROR"),
    ('Error: Invariant Property_Goal is violated.\nState 1: <Initial predicate>\nv_status = "Created"\n'
     'State 2: <Next>\nv_status = "Executed"\nv_approved = TRUE\nv_cancelled = FALSE', 12, False, "ENGINE_ERROR"),
])
def test_reachable_parser_never_proves_unreachability_from_incomplete_run(
    fixed_model, output, exit_code, timed_out, status,
):
    fixed_model["properties"] = [goal(status_is("Executed"))]
    result = parse_tlc_output(output, "", exit_code, timed_out=timed_out, model=validate_model(fixed_model))
    assert result.status.value == status
    assert not result.witness


def test_timeout_budget_is_shared_by_all_searches(fixed_model, monkeypatch):
    fixed_model["properties"] = [goal(False, name) for name in ["One", "Two", "Three"]]
    ticks = iter([0, 1, 8, 11])
    monkeypatch.setattr("model_checker.runner.time.monotonic", lambda: next(ticks))
    budgets = []
    def run(model, config):
        budgets.append(config.timeout_seconds)
        return VerificationResult(status=VerificationStatus.PROPERTY_HOLDS)
    monkeypatch.setattr("model_checker.runner._verify_single", run)
    result = verify(fixed_model, TLCConfig(timeout_seconds=10))
    assert budgets == [9, 2]
    assert result.status == VerificationStatus.TIMEOUT
    assert [item.status.value for item in result.property_results] == ["PROPERTY_HOLDS", "PROPERTY_HOLDS", "TIMEOUT"]
