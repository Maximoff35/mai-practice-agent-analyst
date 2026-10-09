"""Orchestration between a model provider and the deterministic checker."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from model_checker import BehavioralModel, TraceState, VerificationResult, verify

from .provider import LLMProvider


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: str
    behavioral_model: BehavioralModel
    verification_result: VerificationResult
    counterexample: list[TraceState] | None = None
    explanation: str


class AnalystAgent:
    def __init__(
        self,
        provider: LLMProvider,
        checker: Callable[[BehavioralModel], VerificationResult] = verify,
    ) -> None:
        self.provider = provider
        self.checker = checker

    def analyze(self, requirements: str) -> AnalysisResult:
        model = self.provider.build_model(requirements)
        verification = self.checker(model)
        explanation = self.provider.explain_result(requirements, model, verification)
        return AnalysisResult(
            requirements=requirements,
            behavioral_model=model,
            verification_result=verification,
            counterexample=verification.counterexample or None,
            explanation=explanation,
        )
