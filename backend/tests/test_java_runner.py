from pathlib import Path

import pytest

from java_runner import (
    JavaArtifact,
    JavaCheckStatus,
    JavaRunnerConfig,
    JavaSourceFile,
    run_java_module,
)


JAVA_MACHINE = """
import java.io.BufferedReader;
import java.io.InputStreamReader;

public class Machine {
  static String status = "Created";
  static boolean approved = false;
  static boolean cancelled = false;

  static void state() {
    System.out.println("STATE status=" + status + ";approved=" + approved + ";cancelled=" + cancelled);
  }

  public static void main(String[] args) throws Exception {
    System.out.println("READY");
    BufferedReader input = new BufferedReader(new InputStreamReader(System.in));
    String line;
    while ((line = input.readLine()) != null) {
      if (line.equals("SNAPSHOT")) {
        state();
      } else if (line.startsWith("FIRE ")) {
        String event = line.substring(5);
        if (event.equals("Approve") && status.equals("Created")) {
          status = "Approved";
          approved = true;
          System.out.println("APPLIED");
          state();
        } else if (event.equals("Cancel") && (status.equals("Created") || status.equals("Approved"))) {
          status = "Cancelled";
          cancelled = true;
          System.out.println("APPLIED");
          state();
        } else if (event.equals("Execute") && approved) {
          status = "Executed";
          System.out.println("APPLIED");
          state();
        } else {
          System.out.println("REJECTED");
        }
      }
      System.out.flush();
    }
  }
}
"""

JAVA_MACHINE_FIXED = JAVA_MACHINE.replace(
    'cancelled = true;\n          System.out.println("APPLIED");',
    'cancelled = true;\n          approved = false;\n          System.out.println("APPLIED");',
)


def _artifact(content=JAVA_MACHINE):
    return JavaArtifact(
        files=[JavaSourceFile(path="Machine.java", content=content)],
        main_class="Machine",
        model_fingerprint="model-1",
    )


def test_java_artifact_rejects_traversal():
    with pytest.raises(ValueError, match="traversal"):
        JavaSourceFile(path="../Machine.java", content=JAVA_MACHINE)


def test_java_runner_reports_missing_environment(fixed_model, tmp_path, monkeypatch):
    monkeypatch.setattr("java_runner.runner._resolve", lambda _: None)

    result = run_java_module(_artifact(), fixed_model, JavaRunnerConfig(temp_root=tmp_path))

    assert result.status == JavaCheckStatus.ENVIRONMENT_UNAVAILABLE
    assert result.model_fingerprint == "model-1"
    assert list(tmp_path.iterdir()) == []


def test_java_runner_compiles_and_checks_fixture(buggy_model, tmp_path):
    if not __import__("shutil").which("javac") or not __import__("shutil").which("java"):
        pytest.skip("JDK is not installed")

    result = run_java_module(
        _artifact(),
        buggy_model,
        JavaRunnerConfig(temp_root=tmp_path, timeout_seconds=5),
    )

    assert result.status == JavaCheckStatus.PASSED, result.stderr or result.stdout
    assert result.checks_run > 0
    assert list(tmp_path.iterdir()) == []


def test_java_runner_accepts_fixed_fixture(fixed_model, tmp_path):
    if not __import__("shutil").which("javac") or not __import__("shutil").which("java"):
        pytest.skip("JDK is not installed")

    result = run_java_module(
        _artifact(JAVA_MACHINE_FIXED),
        fixed_model,
        JavaRunnerConfig(temp_root=tmp_path, timeout_seconds=5),
    )

    assert result.status == JavaCheckStatus.PASSED, result.stderr or result.stdout


def test_java_runner_detects_removed_guard(buggy_model, tmp_path):
    if not __import__("shutil").which("javac") or not __import__("shutil").which("java"):
        pytest.skip("JDK is not installed")
    broken = JAVA_MACHINE.replace(
        'event.equals("Execute") && approved',
        'event.equals("Execute")',
    )

    result = run_java_module(
        _artifact(broken),
        buggy_model,
        JavaRunnerConfig(temp_root=tmp_path, timeout_seconds=5),
    )

    assert result.status == JavaCheckStatus.BEHAVIOR_VIOLATED
    assert result.failed_check == "Execute"
    assert list(tmp_path.iterdir()) == []


def test_java_runner_detects_wrong_effect(fixed_model, tmp_path):
    if not __import__("shutil").which("javac") or not __import__("shutil").which("java"):
        pytest.skip("JDK is not installed")

    result = run_java_module(
        _artifact(),
        fixed_model,
        JavaRunnerConfig(temp_root=tmp_path, timeout_seconds=5),
    )

    assert result.status == JavaCheckStatus.BEHAVIOR_VIOLATED
    assert result.failed_check == "Cancel"
    assert list(tmp_path.iterdir()) == []


def test_java_runner_detects_wrong_initial_state(buggy_model, tmp_path):
    if not __import__("shutil").which("javac") or not __import__("shutil").which("java"):
        pytest.skip("JDK is not installed")
    wrong_initial = JAVA_MACHINE.replace('static String status = "Created";', 'static String status = "Approved";')

    result = run_java_module(
        _artifact(wrong_initial),
        buggy_model,
        JavaRunnerConfig(temp_root=tmp_path, timeout_seconds=5),
    )

    assert result.status == JavaCheckStatus.BEHAVIOR_VIOLATED
    assert result.failed_check == "initial"
    assert list(tmp_path.iterdir()) == []


def test_java_runner_rejects_forbidden_capability(fixed_model, tmp_path):
    source = JAVA_MACHINE.replace(
        "import java.io.BufferedReader;",
        "import java.net.Socket;\nimport java.io.BufferedReader;",
    )

    result = run_java_module(
        _artifact(source),
        fixed_model,
        JavaRunnerConfig(temp_root=tmp_path),
    )

    assert result.status == JavaCheckStatus.INVALID_ARTIFACT
    assert "forbidden" in result.message
    assert list(tmp_path.iterdir()) == []


def test_java_runner_reports_timeout(buggy_model, tmp_path):
    if not __import__("shutil").which("javac") or not __import__("shutil").which("java"):
        pytest.skip("JDK is not installed")
    hanging = JAVA_MACHINE.replace(
        'if (line.equals("SNAPSHOT")) {\n        state();',
        'if (line.equals("SNAPSHOT")) {\n        while (true) {}',
    )

    result = run_java_module(
        _artifact(hanging),
        buggy_model,
        JavaRunnerConfig(temp_root=tmp_path, timeout_seconds=0.2),
    )

    assert result.status == JavaCheckStatus.TIMEOUT
    assert list(tmp_path.iterdir()) == []


def test_java_runner_reports_output_limit(buggy_model, tmp_path):
    if not __import__("shutil").which("javac") or not __import__("shutil").which("java"):
        pytest.skip("JDK is not installed")
    noisy = JAVA_MACHINE.replace(
        'if (line.equals("SNAPSHOT")) {\n        state();',
        'if (line.equals("SNAPSHOT")) {\n        System.out.println("x".repeat(10000));',
    )

    result = run_java_module(
        _artifact(noisy),
        buggy_model,
        JavaRunnerConfig(temp_root=tmp_path, max_output_bytes=1000),
    )

    assert result.status == JavaCheckStatus.OUTPUT_LIMIT_REACHED
    assert list(tmp_path.iterdir()) == []


def test_java_runner_reports_compile_error(buggy_model, tmp_path):
    if not __import__("shutil").which("javac"):
        pytest.skip("JDK is not installed")

    result = run_java_module(
        _artifact("public class Machine { syntax error }"),
        buggy_model,
        JavaRunnerConfig(temp_root=tmp_path, timeout_seconds=5),
    )

    assert result.status == JavaCheckStatus.COMPILE_ERROR
    assert result.stderr
    assert list(tmp_path.iterdir()) == []
