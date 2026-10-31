"""Run the real TLC Java process in an isolated temporary directory."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .parser import parse_tlc_output
from .references import attach_result_references
from .result import PropertyResult, VerificationResult, VerificationStatus
from .schemas import BehavioralModel
from .tla import generate_tla
from .validator import ModelValidationError, validate_model


class TLCConfig(BaseModel):
    java_executable: str = "java"
    tla2tools_jar: Path | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)
    temp_root: Path | None = None

    @classmethod
    def from_env(cls) -> "TLCConfig":
        return cls(
            java_executable=os.getenv("MODEL_CHECKER_JAVA", "java"),
            tla2tools_jar=os.getenv("MODEL_CHECKER_TLA2TOOLS_JAR") or None,
            timeout_seconds=float(os.getenv("MODEL_CHECKER_TIMEOUT_SECONDS", "60")),
            temp_root=os.getenv("MODEL_CHECKER_TEMP_DIR") or None,
        )


def _resolve_java(executable: str) -> str | None:
    found = shutil.which(executable)
    if found:
        return found
    path = Path(executable)
    return str(path.resolve()) if path.is_file() else None


def _verify_single(model: BehavioralModel | dict[str, Any], config: TLCConfig | None = None) -> VerificationResult:
    """Validate, generate, run TLC, and return a structured result."""
    try:
        parsed_model = validate_model(model)
        files = generate_tla(parsed_model)
    except (ValidationError, ModelValidationError, ValueError) as error:
        return VerificationResult(status=VerificationStatus.MODEL_INVALID, message=str(error))

    config = config or TLCConfig.from_env()
    java = _resolve_java(config.java_executable)
    if not java:
        return VerificationResult(status=VerificationStatus.ENGINE_ERROR, message="Java executable not found")
    if config.tla2tools_jar is None or not config.tla2tools_jar.is_file():
        return VerificationResult(status=VerificationStatus.ENGINE_ERROR, message="tla2tools.jar not found")

    jar = str(config.tla2tools_jar.resolve())
    try:
        with tempfile.TemporaryDirectory(prefix="model-checker-", dir=config.temp_root) as temporary:
            directory = Path(temporary)
            (directory / "Model.tla").write_text(files.tla, encoding="utf-8")
            (directory / "Model.cfg").write_text(files.cfg, encoding="utf-8")
            command = [java, "-cp", jar, "tlc2.TLC", "-workers", "1", "-config", "Model.cfg", "Model.tla"]
            process = subprocess.Popen(
                command,
                cwd=directory,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            try:
                stdout, stderr = process.communicate(timeout=config.timeout_seconds)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                timed_out = True
    except OSError as error:
        return VerificationResult(status=VerificationStatus.ENGINE_ERROR, message=str(error))
    return parse_tlc_output(stdout, stderr, process.returncode, model=parsed_model, timed_out=timed_out)


def verify(model: BehavioralModel | dict[str, Any], config: TLCConfig | None = None) -> VerificationResult:
    """Preserve legacy invariant checks; isolate reachability and deadlock properties."""
    try:
        parsed_model = validate_model(model)
    except (ValidationError, ModelValidationError, ValueError) as error:
        return VerificationResult(status=VerificationStatus.MODEL_INVALID, message=str(error))
    if not any(prop.type in {"reachable", "deadlock_free"} for prop in parsed_model.properties):
        return _verify_single(parsed_model, config)

    config = config or TLCConfig.from_env()
    deadline = time.monotonic() + config.timeout_seconds
    results: list[VerificationResult] = []
    property_results: list[PropertyResult] = []
    for prop in parsed_model.properties:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result = VerificationResult(status=VerificationStatus.TIMEOUT, message="Общий лимит времени проверки исчерпан")
        else:
            single_model = parsed_model.model_copy(update={"properties": [prop]})
            result = _verify_single(single_model, config.model_copy(update={"timeout_seconds": remaining}))
        results.append(result)
        property_results.append(PropertyResult(
            property_name=prop.name, property_type=prop.type, status=result.status,
            message=result.message, counterexample=result.counterexample, witness=result.witness,
            deadlock_path=result.deadlock_path,
            related_requirements=result.related_requirements, statistics=result.statistics,
        ))

    # A definite violation remains visible even if another property's search was interrupted.
    precedence = [VerificationStatus.PROPERTY_VIOLATED, VerificationStatus.MODEL_INVALID,
                  VerificationStatus.ENGINE_ERROR, VerificationStatus.TIMEOUT, VerificationStatus.STATE_LIMIT_REACHED,
                  VerificationStatus.PROPERTY_HOLDS]
    status = next(status for status in precedence if any(result.status == status for result in results))
    selected = next(index for index, result in enumerate(results) if result.status == status)
    representative = results[selected]
    return attach_result_references(VerificationResult(
        status=status,
        message="; ".join(f"{item.property_name}: {item.status.value}" for item in property_results),
        violated_property=parsed_model.properties[selected].name if status == VerificationStatus.PROPERTY_VIOLATED else None,
        counterexample=representative.counterexample,
        witness=representative.witness if len(results) == 1 else [],
        deadlock_path=representative.deadlock_path,
        property_results=property_results,
        statistics=representative.statistics if len(results) == 1 else {},
        stdout="\n".join(result.stdout for result in results),
        stderr="\n".join(result.stderr for result in results),
        exit_code=representative.exit_code,
    ), parsed_model)
