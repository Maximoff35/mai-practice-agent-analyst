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
            or "\\" in value
            or ":" in value
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.suffix != ".java"
        ):
            raise ValueError("Java source path must be a relative .java path without traversal")
        return value


class JavaArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    files: list[JavaSourceFile] = Field(min_length=1, max_length=32)
    main_class: str = Field(min_length=1, max_length=240, pattern=r"^[A-Za-z_$][A-Za-z0-9_$.]*$")
    model_fingerprint: str | None = Field(default=None, min_length=1, max_length=128)
    instruction: str | None = Field(default=None, max_length=4_000)

    @field_validator("files")
    @classmethod
    def validate_unique_paths(cls, value: list[JavaSourceFile]) -> list[JavaSourceFile]:
        paths = [item.path for item in value]
        if len(paths) != len(set(paths)):
            raise ValueError("Java artifact contains duplicate source paths")
        return value


class JavaCheckStatus(StrEnum):
    PASSED = "PASSED"
    COMPILE_ERROR = "COMPILE_ERROR"
    BEHAVIOR_VIOLATED = "BEHAVIOR_VIOLATED"
    TIMEOUT = "TIMEOUT"
    OUTPUT_LIMIT_REACHED = "OUTPUT_LIMIT_REACHED"
    ENVIRONMENT_UNAVAILABLE = "ENVIRONMENT_UNAVAILABLE"
    INVALID_ARTIFACT = "INVALID_ARTIFACT"
    RUNNER_ERROR = "RUNNER_ERROR"


class JavaCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: JavaCheckStatus
    message: str | None = None
    model_fingerprint: str | None = None
    checks_run: int = 0
    failed_check: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
