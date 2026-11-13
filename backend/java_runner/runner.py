"""Bounded javac/java runner for generated state-machine modules.

The generated main class must implement this line protocol:

    stdout: READY
    stdin:  SNAPSHOT
    stdout: STATE key=value;key=value
    stdin:  FIRE EventName
    stdout: APPLIED and then STATE, or REJECTED

The runner owns every command and never executes shell text supplied by an
artifact. Each behavioral check starts a fresh JVM, so a failed process cannot
poison later checks.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

from model_checker.schemas import BehavioralModel, BooleanVariable, EnumVariable, IntegerVariable
from model_checker.validator import validate_model

from .schemas import JavaArtifact, JavaCheckResult, JavaCheckStatus


_STATE = re.compile(r"^STATE(?:\s+|$)(.*)$")
_PAIR = re.compile(r"^([^=;]+)=(.*)$")


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class JavaRunnerConfig:
    def __init__(
        self,
        *,
        javac_executable: str = "javac",
        java_executable: str = "java",
        timeout_seconds: float = 10.0,
        max_checks: int = 1_000,
        max_output_bytes: int = 256_000,
        temp_root: Path | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_checks <= 0 or max_output_bytes <= 0:
            raise ValueError("Java runner limits must be positive")
        self.javac_executable = javac_executable
        self.java_executable = java_executable
        self.timeout_seconds = timeout_seconds
        self.max_checks = max_checks
        self.max_output_bytes = max_output_bytes
        self.temp_root = temp_root


def _resolve(executable: str) -> str | None:
    found = shutil.which(executable)
    if found:
        return found
    path = Path(executable)
    return str(path.resolve()) if path.is_file() else None


def _safe_environment() -> dict[str, str]:
    allowed = {"PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "JAVA_HOME"}
    return {key: value for key, value in os.environ.items() if key in allowed}


def _validate_source_policy(artifact: JavaArtifact) -> str | None:
    forbidden = (
        "import java.net",
        "import java.nio.file",
        "import java.lang.reflect",
        "ProcessBuilder",
        "Runtime.getRuntime",
        "System.getenv",
    )
    for source in artifact.files:
        if any(token in source.content for token in forbidden):
            return f"Java source {source.path!r} uses a forbidden runtime capability"
    return None


def _evaluate(node: Any, state: dict[str, Any]) -> Any:
    if not isinstance(node, dict):
        return node
    operator, args = next(iter(node.items()))
    if operator == "var":
        return state[args]
    if operator == "eq":
        return _evaluate(args[0], state) == _evaluate(args[1], state)
    if operator == "in":
        return _evaluate(args[0], state) in args[1]
    if operator == "and":
        return all(_evaluate(item, state) for item in args)
    if operator == "or":
        return any(_evaluate(item, state) for item in args)
    if operator == "not":
        return not _evaluate(args, state)
    raise ValueError(f"unsupported expression operator {operator!r}")


def _expected_state(model: BehavioralModel, state: dict[str, Any], transition_name: str) -> dict[str, Any]:
    transition = next(item for item in model.transitions if item.name == transition_name)
    expected = state.copy()
    for effect in transition.effects:
        target, source = effect.set
        expected[target] = _evaluate(source.root, state)
    return expected


def _within(value: Any, variable: Any) -> bool:
    if isinstance(variable, EnumVariable):
        return isinstance(value, str) and value in variable.values
    if isinstance(variable, BooleanVariable):
        return type(value) is bool
    return type(value) is int and variable.min <= value <= variable.max


def _parse_state(line: str, model: BehavioralModel) -> dict[str, Any] | None:
    match = _STATE.match(line.strip())
    if not match:
        return None
    values: dict[str, Any] = {}
    for raw_pair in match.group(1).split(";"):
        pair = _PAIR.fullmatch(raw_pair.strip())
        if not pair:
            return None
        key, raw_value = pair.groups()
        variable = next((item for item in model.variables if item.name == key), None)
        if variable is None:
            return None
        if isinstance(variable, BooleanVariable):
            if raw_value not in {"true", "false"}:
                return None
            value: Any = raw_value == "true"
        elif isinstance(variable, IntegerVariable):
            try:
                value = int(raw_value)
            except ValueError:
                return None
        else:
            value = raw_value
        values[key] = value
    if set(values) != {item.name for item in model.variables}:
        return None
    return values


def _run_script(
    java: str,
    artifact: JavaArtifact,
    model: BehavioralModel,
    classes: Path,
    commands: list[str],
    config: JavaRunnerConfig,
) -> tuple[JavaCheckStatus | None, list[str], str, int | None]:
    process = subprocess.Popen(
        [java, "-cp", str(classes), artifact.main_class],
        cwd=classes,
        env=_safe_environment(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(
            "\n".join(commands) + "\n",
            timeout=config.timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        process.kill()
        stdout, stderr = process.communicate()
        return (
            JavaCheckStatus.TIMEOUT,
            _text(stdout).splitlines(),
            _text(stderr),
            process.returncode,
        )
    output = stdout.encode("utf-8", errors="replace")
    if len(output) > config.max_output_bytes:
        process.kill()
        return JavaCheckStatus.OUTPUT_LIMIT_REACHED, stdout.splitlines(), stderr, process.returncode
    if process.returncode != 0:
        return JavaCheckStatus.RUNNER_ERROR, stdout.splitlines(), stderr, process.returncode
    return None, stdout.splitlines(), stderr, process.returncode


def _check_path(
    java: str,
    artifact: JavaArtifact,
    model: BehavioralModel,
    classes: Path,
    path: tuple[str, ...],
    current: dict[str, Any],
    transition_name: str,
    expected: dict[str, Any],
    config: JavaRunnerConfig,
) -> tuple[JavaCheckStatus | None, str | None, str, str, int | None]:
    status, lines, stderr, exit_code = _run_script(
        java, artifact, model, classes,
        ["SNAPSHOT", *(f"FIRE {item}" for item in path), f"FIRE {transition_name}"],
        config,
    )
    if status:
        return status, transition_name, "\n".join(lines), stderr, exit_code
    if not lines or lines[0] != "READY":
        return JavaCheckStatus.RUNNER_ERROR, "startup", "\n".join(lines), stderr, exit_code
    state_lines = [line for line in lines if line.startswith("STATE")]
    initial = _parse_state(state_lines[0], model) if state_lines else None
    if initial != model.initial:
        return JavaCheckStatus.BEHAVIOR_VIOLATED, "initial", "\n".join(lines), stderr, exit_code
    path_state = model.initial
    for index, event in enumerate(path):
        applied_index = 2 + index * 2
        state_index = applied_index + 1
        if state_index >= len(lines) or lines[applied_index] != "APPLIED":
            return JavaCheckStatus.BEHAVIOR_VIOLATED, event, "\n".join(lines), stderr, exit_code
        path_state = _expected_state(model, path_state, event)
        if _parse_state(lines[state_index], model) != path_state:
            return JavaCheckStatus.BEHAVIOR_VIOLATED, event, "\n".join(lines), stderr, exit_code
    command_index = 2 + len(path) * 2
    if command_index >= len(lines):
        return JavaCheckStatus.BEHAVIOR_VIOLATED, transition_name, "\n".join(lines), stderr, exit_code
    allowed = bool(_evaluate(
        next(item for item in model.transitions if item.name == transition_name).guard.root,
        current,
    ))
    response = lines[command_index]
    if not allowed and response == "REJECTED":
        return None, None, "\n".join(lines), stderr, exit_code
    if allowed and response == "APPLIED":
        actual = _parse_state(lines[command_index + 1], model) if command_index + 1 < len(lines) else None
        if actual == expected and all(_within(actual[name], variable) for name, variable in (
            (item.name, item) for item in model.variables
        )):
            return None, None, "\n".join(lines), stderr, exit_code
    return JavaCheckStatus.BEHAVIOR_VIOLATED, transition_name, "\n".join(lines), stderr, exit_code


def run_java_module(
    artifact: JavaArtifact | dict[str, Any],
    model: BehavioralModel | dict[str, Any],
    config: JavaRunnerConfig | None = None,
) -> JavaCheckResult:
    """Compile and behaviorally check one generated Java artifact."""
    config = config or JavaRunnerConfig()
    try:
        parsed_artifact = artifact if isinstance(artifact, JavaArtifact) else JavaArtifact.model_validate(artifact)
        parsed_model = validate_model(model)
    except Exception as error:
        return JavaCheckResult(status=JavaCheckStatus.INVALID_ARTIFACT, message=str(error))
    policy_error = _validate_source_policy(parsed_artifact)
    if policy_error:
        return JavaCheckResult(
            status=JavaCheckStatus.INVALID_ARTIFACT,
            message=policy_error,
            model_fingerprint=parsed_artifact.model_fingerprint,
        )

    javac = _resolve(config.javac_executable)
    java = _resolve(config.java_executable)
    if not javac or not java:
        return JavaCheckResult(
            status=JavaCheckStatus.ENVIRONMENT_UNAVAILABLE,
            message="javac and java are required",
            model_fingerprint=parsed_artifact.model_fingerprint,
        )
    try:
        with tempfile.TemporaryDirectory(prefix="java-runner-", dir=config.temp_root) as temporary:
            root = Path(temporary)
            source_root = root / "sources"
            classes = root / "classes"
            classes.mkdir()
            source_paths: list[str] = []
            for source in parsed_artifact.files:
                target = source_root / source.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.content, encoding="utf-8")
                source_paths.append(str(target))
            compile_process = subprocess.run(
                [javac, "-encoding", "UTF-8", "-d", str(classes), *source_paths],
                cwd=root,
                env=_safe_environment(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.timeout_seconds,
            )
            if compile_process.returncode != 0:
                return JavaCheckResult(
                    status=JavaCheckStatus.COMPILE_ERROR,
                    message="javac rejected the generated sources",
                    model_fingerprint=parsed_artifact.model_fingerprint,
                    stdout=compile_process.stdout[:config.max_output_bytes],
                    stderr=compile_process.stderr[:config.max_output_bytes],
                    exit_code=compile_process.returncode,
                )

            initial = parsed_model.initial
            queue: deque[tuple[dict[str, Any], tuple[str, ...]]] = deque([(initial, ())])
            seen = {tuple(sorted(initial.items()))}
            checks = 0
            last_stdout = ""
            last_stderr = ""
            last_exit: int | None = None
            while queue:
                state, path = queue.popleft()
                for transition in parsed_model.transitions:
                    checks += 1
                    if checks > config.max_checks:
                        return JavaCheckResult(
                            status=JavaCheckStatus.OUTPUT_LIMIT_REACHED,
                            message="Java behavior check limit reached",
                            model_fingerprint=parsed_artifact.model_fingerprint,
                            checks_run=checks,
                        )
                    expected = _expected_state(parsed_model, state, transition.name)
                    status, failed, stdout, stderr, exit_code = _check_path(
                        java, parsed_artifact, parsed_model, classes, path,
                        state, transition.name, expected, config,
                    )
                    last_stdout, last_stderr, last_exit = stdout, stderr, exit_code
                    if status:
                        return JavaCheckResult(
                            status=status,
                            message="Java module does not match BehavioralModel",
                            model_fingerprint=parsed_artifact.model_fingerprint,
                            checks_run=checks,
                            failed_check=failed,
                            stdout=stdout[:config.max_output_bytes],
                            stderr=stderr[:config.max_output_bytes],
                            exit_code=exit_code,
                        )
                    if bool(_evaluate(transition.guard.root, state)):
                        key = tuple(sorted(expected.items()))
                        if key not in seen:
                            seen.add(key)
                            queue.append((expected, path + (transition.name,)))
            return JavaCheckResult(
                status=JavaCheckStatus.PASSED,
                model_fingerprint=parsed_artifact.model_fingerprint,
                checks_run=checks,
                stdout=last_stdout[:config.max_output_bytes],
                stderr=last_stderr[:config.max_output_bytes],
                exit_code=last_exit,
            )
    except subprocess.TimeoutExpired as error:
        return JavaCheckResult(
            status=JavaCheckStatus.TIMEOUT,
            message="Java compilation exceeded the time limit",
            model_fingerprint=parsed_artifact.model_fingerprint,
            stdout=_text(error.stdout)[:config.max_output_bytes],
            stderr=_text(error.stderr)[:config.max_output_bytes],
        )
    except OSError as error:
        return JavaCheckResult(
            status=JavaCheckStatus.RUNNER_ERROR,
            message=str(error),
            model_fingerprint=parsed_artifact.model_fingerprint,
        )
