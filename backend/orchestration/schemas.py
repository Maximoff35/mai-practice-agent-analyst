"""Contracts for the accepted-model and Java verification pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from analyst import AnalysisResult
from java_runner import JavaArtifact, JavaCheckResult


class ReviewSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    severity: ReviewSeverity
    message: str = Field(min_length=1, max_length=4_000)
    file: str | None = Field(default=None, min_length=1, max_length=240)
    line: int | None = Field(default=None, ge=1)
    rule: str | None = Field(default=None, min_length=1, max_length=120)
    transition: str | None = Field(default=None, min_length=1, max_length=120)


class JavaReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    approved: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    reviewer_model: str | None = Field(default=None, min_length=1, max_length=160)
    artifact_fingerprint: str = Field(min_length=1, max_length=128)
    model_fingerprint: str = Field(min_length=1, max_length=128)
    message: str | None = Field(default=None, max_length=4_000)


class CaseAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    model_fingerprint: str
    analysis: AnalysisResult
    accepted: bool = False


class CaseAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str
    model_fingerprint: str
    accepted: bool = True


class PipelineReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    status: str
    model_fingerprint: str
    artifact: JavaArtifact | None = None
    review: JavaReview | None = None
    compile_and_check: JavaCheckResult | None = None
    message: str | None = None

