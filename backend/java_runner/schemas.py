"""Contracts for generated Java source artifacts and runner results."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JavaSourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=1_000_000)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or value != path.as_posix()
            or "\\" in value
            or ":" in value
            or any(part in {"", ".", ".."} or not part or not all(c.isascii() and (c.isalnum() or c in "_$.-") for c in part) for part in value.split("/"))
            or path.suffix != ".java"
            or any(part.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))} for part in path.parts)
        ):
            raise ValueError("Java source path must be a relative .java path without traversal")
        return value


class JavaArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    files: list[JavaSourceFile] = Field(min_length=1, max_length=32)
    main_class: str = Field(min_length=1, max_length=240, pattern=r"^[A-Za-z_$][A-Za-z0-9_$.]*$")
    model_fingerprint: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("files")
    @classmethod
    def validate_unique_paths(cls, value: list[JavaSourceFile]) -> list[JavaSourceFile]:
        paths = [item.path for item in value]
        if len(paths) != len(set(path.casefold() for path in paths)):
            raise ValueError("Java artifact contains duplicate source paths")
        if sum(len(item.content.encode("utf-8")) for item in value) > 2_000_000:
            raise ValueError("Суммарный размер исходников превышает 2 MB")
        return value


class JavaCheckStatus(StrEnum):
    PASSED = "PASSED"
    COMPILE_ERROR = "COMPILE_ERROR"
    BEHAVIOR_VIOLATED = "BEHAVIOR_VIOLATED"
    TIMEOUT = "TIMEOUT"
    OUTPUT_LIMIT_REACHED = "OUTPUT_LIMIT_REACHED"
    CHECK_LIMIT_REACHED = "CHECK_LIMIT_REACHED"
    ENVIRONMENT_UNAVAILABLE = "ENVIRONMENT_UNAVAILABLE"
    INVALID_ARTIFACT = "INVALID_ARTIFACT"
    RUNNER_ERROR = "RUNNER_ERROR"


class JavaCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: JavaCheckStatus
    message: str | None = None
    model_fingerprint: str | None = None
    artifact_fingerprint: str | None = None
    compilation: str = "NOT_RUN"
    coverage: str = "NOT_COMPLETED"
    checks_run: int = 0
    failed_check: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
