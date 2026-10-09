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
