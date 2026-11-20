"""Регрессии константных свойств выполняются настоящим TLC."""

import pytest

from model_checker import VerificationStatus, verify


@pytest.mark.integration
@pytest.mark.parametrize("kind,expression,violated", [
    ("invariant", False, True), ("invariant", True, False),
    ("forbidden_state", True, True), ("forbidden_state", False, False),
    ("invariant", {"and": [True, {"not": True}]}, True),
    ("forbidden_state", {"or": [False, True]}, True),
    ("invariant", {"eq": [1, 1]}, False),
    ("forbidden_state", {"and": [True, False]}, False),
])
def test_constant_property(fixed_model, configured_tlc, kind, expression, violated):
    fixed_model["properties"] = [{"name": "P1", "type": kind, "expression": expression}]
    result = verify(fixed_model)
    expected = VerificationStatus.PROPERTY_VIOLATED if violated else VerificationStatus.PROPERTY_HOLDS
    assert result.status == expected, result.stdout + result.stderr
    if violated:
        assert result.violated_property == "P1"
        assert len(result.counterexample) == 1
        assert result.counterexample[0].values == fixed_model["initial"]
        assert result.counterexample[0].transition is None
    else:
        assert result.counterexample == []


@pytest.mark.integration
def test_constant_with_reachable_and_deadlock(fixed_model, configured_tlc):
    fixed_model["properties"] = [
        {"name": "P1", "type": "invariant", "expression": False},
        {"name": "P2", "type": "reachable", "expression": True},
        {"name": "P3", "type": "deadlock_free", "terminal_states": True},
    ]
    result = verify(fixed_model)
    assert result.status == VerificationStatus.PROPERTY_VIOLATED
    assert [item.status for item in result.property_results] == [
        VerificationStatus.PROPERTY_VIOLATED, VerificationStatus.PROPERTY_HOLDS,
        VerificationStatus.PROPERTY_HOLDS,
    ]
    assert result.property_results[0].counterexample[0].values == fixed_model["initial"]
    assert result.property_results[1].witness[0].values == fixed_model["initial"]
