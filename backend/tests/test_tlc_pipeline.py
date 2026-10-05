from pathlib import Path
import subprocess

import pytest

from model_checker import TLCConfig, VerificationStatus, verify
from model_checker.parser import parse_tlc_output
from model_checker.validator import validate_model


VIOLATION_OUTPUT = '''
Error: Invariant Property_NoExecutedAfterCancel is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ v_status = "Created"
/\\ v_approved = FALSE
/\\ v_cancelled = FALSE

State 2: <Next line 20, col 3 to line 20, col 12 of module Model>
/\\ v_status = "Approved"
/\\ v_approved = TRUE
/\\ v_cancelled = FALSE

State 3: <Next line 20, col 3 to line 20, col 12 of module Model>
/\\ v_status = "Cancelled"
/\\ v_approved = TRUE
/\\ v_cancelled = TRUE

State 4: <Next line 20, col 3 to line 20, col 12 of module Model>
/\\ v_status = "Executed"
/\\ v_approved = TRUE
/\\ v_cancelled = TRUE

8 states generated, 4 distinct states found, 0 states left on queue.
The depth of the complete state graph search is 4.
Finished in 01s
'''

SUCCESS_OUTPUT = '''
10 states generated, 4 distinct states found, 0 states left on queue.
The depth of the complete state graph search is 4.
Model checking completed. No error has been found.
Finished in 01s
'''


def test_parse_violation_and_infer_transitions(buggy_model):
    result = parse_tlc_output(VIOLATION_OUTPUT, "", 12, model=validate_model(buggy_model))
    assert result.status == VerificationStatus.PROPERTY_VIOLATED
    assert result.violated_property == "NoExecutedAfterCancel"
    assert [state.values["status"] for state in result.counterexample] == [
        "Created", "Approved", "Cancelled", "Executed"
    ]
    assert [state.transition for state in result.counterexample] == [
        None, "Approve", "Cancel", "Execute"
    ]
    assert result.counterexample[2].values["approved"] is True
    assert result.statistics.generated_states == 8
    assert result.statistics.distinct_states == 4
    assert result.statistics.graph_depth == 4


@pytest.mark.parametrize(
    ("output", "exit_code", "timed_out", "status"),
    [
        (SUCCESS_OUTPUT, 0, False, VerificationStatus.PROPERTY_HOLDS),
        (SUCCESS_OUTPUT, 1, False, VerificationStatus.ENGINE_ERROR),
        ("Finished in 01s", 0, False, VerificationStatus.ENGINE_ERROR),
        (SUCCESS_OUTPUT, None, True, VerificationStatus.TIMEOUT),
        (SUCCESS_OUTPUT + "State limit reached", 0, False, VerificationStatus.STATE_LIMIT_REACHED),
        ("Semantic error in module Model", 1, False, VerificationStatus.MODEL_INVALID),
        ("Exception in thread main", 1, False, VerificationStatus.ENGINE_ERROR),
    ],
)
def test_completion_classification(output, exit_code, timed_out, status):
    result = parse_tlc_output(output, "", exit_code, timed_out=timed_out)
    assert result.status == status


def test_invalid_input_does_not_start_tlc(buggy_model, monkeypatch):
    buggy_model["initial"].pop("approved")
    monkeypatch.setattr("model_checker.runner.subprocess.Popen", lambda *args, **kwargs: pytest.fail("TLC started"))
    result = verify(buggy_model)
    assert result.status == VerificationStatus.MODEL_INVALID


def test_runner_writes_files_and_runs_subprocess(fixed_model, tmp_path, monkeypatch):
    jar = tmp_path / "tla2tools.jar"
    jar.write_bytes(b"test placeholder")
    monkeypatch.setattr("model_checker.runner._resolve_java", lambda _: "java-test")

    class FakeProcess:
        returncode = 0

        def __init__(self, command, **kwargs):
            assert command[:4] == ["java-test", "-cp", str(jar), "tlc2.TLC"]
            assert command[-1] == "Model.tla"
            directory = Path(kwargs["cwd"])
            assert "Step_Cancel" in (directory / "Model.tla").read_text(encoding="utf-8")
            assert "INVARIANT Property_NoExecutedAfterCancel" in (directory / "Model.cfg").read_text(encoding="utf-8")

        def communicate(self, timeout=None):
            assert timeout == 5
            return SUCCESS_OUTPUT, ""

    monkeypatch.setattr("model_checker.runner.subprocess.Popen", FakeProcess)
    result = verify(fixed_model, TLCConfig(java_executable="java-test", tla2tools_jar=jar, timeout_seconds=5, temp_root=tmp_path))
    assert result.status == VerificationStatus.PROPERTY_HOLDS
    assert result.statistics.distinct_states == 4


def test_runner_kills_timed_out_process(fixed_model, tmp_path, monkeypatch):
    jar = tmp_path / "tla2tools.jar"
    jar.write_bytes(b"test placeholder")
    monkeypatch.setattr("model_checker.runner._resolve_java", lambda _: "java-test")
    killed = []

    class HungProcess:
        returncode = None

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("java-test", timeout)
            self.returncode = -9
            return SUCCESS_OUTPUT, ""

        def kill(self):
            killed.append(True)

    monkeypatch.setattr("model_checker.runner.subprocess.Popen", HungProcess)
    result = verify(fixed_model, TLCConfig(java_executable="java-test", tla2tools_jar=jar, timeout_seconds=0.1, temp_root=tmp_path))
    assert killed == [True]
    assert result.status == VerificationStatus.TIMEOUT


def test_missing_runtime_is_engine_error(fixed_model, tmp_path):
    result = verify(fixed_model, TLCConfig(java_executable=str(tmp_path / "not-java"), tla2tools_jar=tmp_path / "not-jar"))
    assert result.status == VerificationStatus.ENGINE_ERROR
