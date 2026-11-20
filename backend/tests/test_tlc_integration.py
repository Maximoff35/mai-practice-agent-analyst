"""Acceptance checks that require an actual Java runtime and TLA+ Tools JAR."""

import shutil

import pytest

from model_checker import TLCConfig, VerificationStatus, verify


def _config_or_skip() -> TLCConfig:
    config = TLCConfig.from_env()
    if not shutil.which(config.java_executable):
        pytest.skip("Java is not configured")
    if not config.tla2tools_jar or not config.tla2tools_jar.is_file():
        pytest.skip("MODEL_CHECKER_TLA2TOOLS_JAR is not configured")
    return config


@pytest.mark.integration
def test_buggy_model_finds_real_counterexample(buggy_model):
    result = verify(buggy_model, _config_or_skip())
    assert result.status == VerificationStatus.PROPERTY_VIOLATED, result.stdout + result.stderr
    assert result.violated_property == "NoExecutedAfterCancel"
    assert [state.values["status"] for state in result.counterexample] == [
        "Created", "Approved", "Cancelled", "Executed"
    ]
    assert [state.transition for state in result.counterexample] == [
        None, "Approve", "Cancel", "Execute"
    ]


@pytest.mark.integration
def test_fixed_model_holds_with_real_tlc(fixed_model):
    result = verify(fixed_model, _config_or_skip())
    assert result.status == VerificationStatus.PROPERTY_HOLDS, result.stdout + result.stderr


def integer_boundary_model():
    low, high = -2147483648, 2147483647
    return {
        "variables": [{"name": "n", "type": "integer", "min": low, "max": high}],
        "initial": {"n": low},
        "transitions": [
            {"name": "Raise", "guard": {"eq": [{"var": "n"}, low]}, "effects": [{"set": ["n", high]}]},
            {"name": "Lower", "guard": {"eq": [{"var": "n"}, high]}, "effects": [{"set": ["n", low]}]},
        ],
        "properties": [{"id": "P1", "type": "invariant", "expression": {"in": [{"var": "n"}, [low, high]]}}],
    }


@pytest.mark.integration
def test_tlc_checks_full_int32_domain_and_both_boundary_values():
    result = verify(integer_boundary_model(), _config_or_skip())
    assert result.status == VerificationStatus.PROPERTY_HOLDS, result.stdout + result.stderr
    assert result.statistics.distinct_states == 2


@pytest.mark.parametrize("value", [-2147483649, 2147483648])
@pytest.mark.parametrize("position", ["bound", "initial", "guard", "effect", "property"])
def test_out_of_range_integer_is_model_invalid(value, position):
    model = integer_boundary_model()
    if position == "bound":
        model["variables"][0]["min" if value < 0 else "max"] = value
    elif position == "initial":
        model["initial"]["n"] = value
    elif position == "guard":
        model["transitions"][0]["guard"] = {"eq": [value, value]}
    elif position == "effect":
        model["transitions"][0]["effects"][0]["set"][1] = value
    else:
        model["properties"][0]["expression"] = {"in": [value, [value]]}
    result = verify(model)
    assert result.status == VerificationStatus.MODEL_INVALID
