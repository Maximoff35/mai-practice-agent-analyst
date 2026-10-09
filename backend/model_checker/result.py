"""Structured outcome of one TLC verification run."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VerificationStatus(StrEnum):
    PROPERTY_HOLDS = "PROPERTY_HOLDS"
    PROPERTY_VIOLATED = "PROPERTY_VIOLATED"
    MODEL_INVALID = "MODEL_INVALID"
    TIMEOUT = "TIMEOUT"
    STATE_LIMIT_REACHED = "STATE_LIMIT_REACHED"
    ENGINE_ERROR = "ENGINE_ERROR"


class TLCStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_states: int | None = None
    distinct_states: int | None = None
    queued_states: int | None = None
    graph_depth: int | None = None


class TraceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    values: dict[str, str | bool | int]
    # Transition from the preceding state to this one, if identifiable.
    transition: str | None = None
    tlc_label: str | None = None


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    message: str | None = None
    violated_property: str | None = None
    counterexample: list[TraceState] = Field(default_factory=list)
    statistics: TLCStatistics = Field(default_factory=TLCStatistics)
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
