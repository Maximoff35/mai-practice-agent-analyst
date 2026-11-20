"""Совместимость с примерами исходного Word и неизменность старого API."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from analyst import AnalystAgent, FakeLLMProvider
from api.main import app, get_agent
from model_checker import TraceState, VerificationResult, VerificationStatus, case_result, check_behavior, validate_model


def test_property_id_and_conflict(fixed_model):
    prop = fixed_model["properties"][0]
    prop["id"] = prop.pop("name")
    assert validate_model(fixed_model).properties[0].name == prop["id"]
    prop["name"] = prop["id"]
    validate_model(fixed_model)
    prop["name"] = "Other"
    with pytest.raises(ValidationError, match="должны совпадать"):
        validate_model(fixed_model)
    assert check_behavior(fixed_model)["status"] == "MODEL_INVALID"


@pytest.mark.parametrize("status", list(VerificationStatus))
def test_versioned_api_preserves_legacy_format(status):
    verification = VerificationResult(
        status=status, statistics={"generated_states": 162, "distinct_states": 37, "graph_depth": 8},
        counterexample=[TraceState(number=1, values={"status": "Created"}),
                        TraceState(number=2, values={"status": "Approved"}, transition="Approve")]
        if status == VerificationStatus.PROPERTY_VIOLATED else [],
    )
    app.dependency_overrides[get_agent] = lambda: AnalystAgent(FakeLLMProvider(), lambda _: verification)
    try:
        client = TestClient(app)
        request = {"requirements": "Заявка и отмена"}
        old = client.post("/api/analyze", json=request).json()
        new = client.post("/api/v2/analyze", json=request).json()
    finally:
        app.dependency_overrides.clear()
    assert old["verification_result"] == verification.model_dump(mode="json")
    assert isinstance(old["verification_result"]["counterexample"], list)
    result = new["verification_result"]
    assert result["status"] == status.value
    assert result["property_id"] == "NoExecutedAfterCancel"
    assert result["engine"] == "TLC"
    assert result["statistics"]["states_generated"] == 162
    assert result["statistics"]["depth"] == 8
    assert new["behavioral_model"]["properties"][0]["id"] == result["property_id"]
    if verification.counterexample:
        assert result["counterexample"]["steps"][0]["number"] == 0
        assert result["counterexample"]["steps"][0]["state"] == {"status": "Created"}
        assert result["counterexample"]["steps"][1]["transition"] == "Approve"
    else:
        assert result["counterexample"] == {"steps": []}


@pytest.mark.integration
@pytest.mark.parametrize("kind,expression", [
    ("invariant", False), ("forbidden_state", True), ("reachable", True), ("deadlock_free", None),
])
def test_case_tool_all_property_types(fixed_model, configured_tlc, kind, expression):
    prop = {"id": "P1", "type": kind}
    if kind != "deadlock_free":
        prop["expression"] = expression
    fixed_model["properties"] = [prop]
    result = check_behavior(fixed_model)
    assert result["property_id"] == "P1"
    assert result["engine"] == "TLC"
    assert result["status"] in {"PROPERTY_HOLDS", "PROPERTY_VIOLATED"}
    trace = result[{"reachable": "witness", "deadlock_free": "deadlock_path"}.get(kind, "counterexample")]
    assert trace["steps"][0]["state"] == fixed_model["initial"]
    assert trace["steps"][0]["number"] == 0


@pytest.mark.integration
def test_multiple_invariants_have_independent_identifiers(fixed_model, configured_tlc):
    fixed_model["properties"] = [
        {"id": "P1", "type": "invariant", "expression": True},
        {"id": "P2", "type": "invariant", "expression": False},
    ]
    result = check_behavior(fixed_model)
    assert result["property_id"] == "P2"
    assert [(item["property_id"], item["status"]) for item in result["property_results"]] == [
        ("P1", "PROPERTY_HOLDS"), ("P2", "PROPERTY_VIOLATED"),
    ]
