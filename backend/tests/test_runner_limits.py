"""Настоящие процессы SANY/TLC, диагностика и очистка временных каталогов."""

import pytest

from model_checker import TLCConfig, TlaFiles, VerificationStatus, verify
from model_checker import runner


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["invariant", "reachable", "deadlock_free"])
def test_real_state_limit_and_retry(fixed_model, configured_tlc, tmp_path, kind):
    prop = {"id": "P1", "type": kind}
    if kind != "deadlock_free":
        prop["expression"] = kind == "invariant"
    else:
        prop["terminal_states"] = True
    fixed_model["properties"] = [prop]
    config = TLCConfig.from_env().model_copy(update={"temp_root": tmp_path, "max_states": 2})
    result = verify(fixed_model, config)
    assert result.status == VerificationStatus.STATE_LIMIT_REACHED, result.stdout + result.stderr
    assert "Invariant MC_StateBudget is violated" in result.stdout
    assert result.exit_code is not None  # communicate() reaped the actual Java process.
    assert result.statistics.distinct_states == 2
    assert result.counterexample == result.witness == result.deadlock_path == []
    assert list(tmp_path.iterdir()) == []
    retry = verify(fixed_model, config.model_copy(update={"max_states": 100}))
    assert retry.status == (VerificationStatus.PROPERTY_VIOLATED if kind == "reachable" else VerificationStatus.PROPERTY_HOLDS)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.integration
def test_violation_survives_another_property_state_limit(fixed_model, configured_tlc):
    fixed_model["properties"] = [
        {"id": "P1", "type": "invariant", "expression": False},
        {"id": "P2", "type": "reachable", "expression": False},
        {"id": "P3", "type": "deadlock_free", "terminal_states": True},
    ]
    result = verify(fixed_model, TLCConfig.from_env().model_copy(update={"max_states": 2}))
    assert result.status == VerificationStatus.PROPERTY_VIOLATED
    assert [item.status for item in result.property_results] == [
        VerificationStatus.PROPERTY_VIOLATED, VerificationStatus.STATE_LIMIT_REACHED,
        VerificationStatus.STATE_LIMIT_REACHED,
    ]
    assert result.counterexample[0].values == fixed_model["initial"]


@pytest.mark.integration
@pytest.mark.parametrize("text", [
    "---- MODULE Model ----\nVARIABLE x\nBad == /\\\n====\n",
    "---- MODULE Model ----\nBad == MissingIdentifier\n====\n",
    "---- MODULE Model ----\nVARIABLE x\nBad == ENABLED [](x = 1)\n====\n",
])
def test_sany_rejects_invalid_generated_module_before_tlc(fixed_model, configured_tlc, tmp_path, monkeypatch, text):
    monkeypatch.setattr(runner, "generate_tla", lambda *a, **kw: TlaFiles(text, ""))
    original = runner._run_process
    commands = []
    def run(command, directory, timeout):
        commands.append(command[3])
        return original(command, directory, timeout)
    monkeypatch.setattr(runner, "_run_process", run)
    result = verify(fixed_model, TLCConfig.from_env().model_copy(update={"temp_root": tmp_path}))
    assert result.status == VerificationStatus.MODEL_INVALID, result.stdout + result.stderr
    assert commands == ["tla2sany.SANY"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.integration
def test_real_sany_timeout_cleans_up(fixed_model, configured_tlc, tmp_path):
    result = verify(fixed_model, TLCConfig.from_env().model_copy(update={
        "timeout_seconds": 0.01, "temp_root": tmp_path,
    }))
    assert result.status == VerificationStatus.TIMEOUT
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("output,code,status", [
    ("Semantic processing of module Model\n*** Errors: 1", 0, VerificationStatus.MODEL_INVALID),
    ("Could not find or load main class tla2sany.SANY", 1, VerificationStatus.ENGINE_ERROR),
    ("", 0, VerificationStatus.ENGINE_ERROR),
])
def test_sany_diagnostics_and_missing_class(fixed_model, tmp_path, monkeypatch, output, code, status):
    jar = tmp_path / "test.jar"
    jar.touch()
    monkeypatch.setattr(runner, "_resolve_java", lambda _: "java")
    monkeypatch.setattr(runner, "_run_process", lambda *a: (output, "", code, False))
    result = verify(fixed_model, TLCConfig(tla2tools_jar=jar, temp_root=tmp_path))
    assert result.status == status
    assert list(tmp_path.iterdir()) == [jar]


def test_process_start_error_and_missing_jar(fixed_model, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_resolve_java", lambda _: "java")
    config = TLCConfig(tla2tools_jar=tmp_path / "missing.jar", temp_root=tmp_path)
    assert verify(fixed_model, config).status == VerificationStatus.ENGINE_ERROR
    config.tla2tools_jar.touch()
    def fail(*a, **kw):
        raise OSError("Невозможно запустить Java")
    monkeypatch.setattr(runner.subprocess, "Popen", fail)
    assert verify(fixed_model, config).status == VerificationStatus.ENGINE_ERROR
    assert list(tmp_path.iterdir()) == [config.tla2tools_jar]


def test_sany_and_tlc_share_deadline(fixed_model, tmp_path, monkeypatch):
    jar = tmp_path / "test.jar"
    jar.touch()
    monkeypatch.setattr(runner, "_resolve_java", lambda _: "java")
    ticks = iter([0, 1, 8])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    budgets = []
    def run(command, directory, timeout):
        budgets.append(timeout)
        output = "Semantic processing of module Model" if command[3] == "tla2sany.SANY" else "Model checking completed. No error has been found."
        return output, "", 0, False
    monkeypatch.setattr(runner, "_run_process", run)
    assert verify(fixed_model, TLCConfig(tla2tools_jar=jar, timeout_seconds=10)).status == VerificationStatus.PROPERTY_HOLDS
    assert budgets == [9, 2]


@pytest.mark.parametrize("value", [0, -1, True, 1.5, 2_147_483_648])
def test_invalid_state_limit_is_not_accepted(value):
    with pytest.raises(ValueError):
        TLCConfig(max_states=value)
