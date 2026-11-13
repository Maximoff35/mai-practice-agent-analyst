"""Stateful orchestration of accepted models and Java verification stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Protocol
from uuid import uuid4

from analyst import AnalysisResult, AnalystAgent
from java_runner import JavaArtifact, JavaCheckResult, JavaCheckStatus, run_java_module
from model_checker import BehavioralModel, VerificationStatus

from .schemas import CaseAcceptance, CaseAnalysis, JavaReview, PipelineReport, ReviewSeverity


class PipelineError(ValueError):
    """A pipeline operation is not valid for the current case state."""


class CaseNotFoundError(PipelineError):
    """The requested case does not exist in this process."""


class ArtifactGenerator(Protocol):
    def generate(
        self,
        requirements: str,
        model: BehavioralModel,
        model_fingerprint: str,
    ) -> JavaArtifact: ...


class Reviewer(Protocol):
    def review(
        self,
        requirements: str,
        model: BehavioralModel,
        artifact: JavaArtifact,
        model_fingerprint: str,
    ) -> JavaReview: ...


class UnavailableGenerator:
    def generate(self, requirements: str, model: BehavioralModel, model_fingerprint: str) -> JavaArtifact:
        raise PipelineError("Генератор Java не настроен")


class UnavailableReviewer:
    def review(
        self,
        requirements: str,
        model: BehavioralModel,
        artifact: JavaArtifact,
        model_fingerprint: str,
    ) -> JavaReview:
        raise PipelineError("Reviewer Java не настроен")


@dataclass
class CaseState:
    case_id: str
    requirements: str
    model: BehavioralModel
    analysis: AnalysisResult
    model_fingerprint: str
    accepted: bool = False
    artifact: JavaArtifact | None = None
    review: JavaReview | None = None
    check: JavaCheckResult | None = None


def fingerprint_model(model: BehavioralModel) -> str:
    encoded = json.dumps(model.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def fingerprint_artifact(artifact: JavaArtifact) -> str:
    payload = {
        "main_class": artifact.main_class,
        "files": [item.model_dump(mode="json") for item in artifact.files],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class CasePipeline:
    agent: AnalystAgent
    generator: ArtifactGenerator = field(default_factory=UnavailableGenerator)
    reviewer: Reviewer = field(default_factory=UnavailableReviewer)
    runner: object = run_java_module
    cases: dict[str, CaseState] = field(default_factory=dict)

    def analyze(self, requirements: str) -> CaseAnalysis:
        analysis = self.agent.analyze(requirements)
        case_id = uuid4().hex
        model_fingerprint = fingerprint_model(analysis.behavioral_model)
        self.cases[case_id] = CaseState(
            case_id=case_id,
            requirements=requirements,
            model=analysis.behavioral_model,
            analysis=analysis,
            model_fingerprint=model_fingerprint,
        )
        return CaseAnalysis(case_id=case_id, model_fingerprint=model_fingerprint, analysis=analysis)

    def _case(self, case_id: str) -> CaseState:
        try:
            return self.cases[case_id]
        except KeyError as error:
            raise CaseNotFoundError("Кейс не найден или срок его хранения истёк") from error

    def accept(self, acceptance: CaseAcceptance) -> CaseAnalysis:
        case = self._case(acceptance.case_id)
        if acceptance.model_fingerprint != case.model_fingerprint:
            raise PipelineError("Версия модели не совпадает с сохранённым анализом")
        if case.analysis.verification_result.status != VerificationStatus.PROPERTY_HOLDS:
            raise PipelineError("Генерация разрешена только после успешной проверки всех свойств")
        case.accepted = True
        return CaseAnalysis(
            case_id=case.case_id,
            model_fingerprint=case.model_fingerprint,
            analysis=case.analysis,
            accepted=True,
        )

    def generate(self, case_id: str) -> PipelineReport:
        case = self._case(case_id)
        if not case.accepted:
            raise PipelineError("Сначала явно примите модель после успешной проверки")
        try:
            artifact = self.generator.generate(case.requirements, case.model, case.model_fingerprint)
            artifact = JavaArtifact.model_validate(artifact)
            artifact_fingerprint = fingerprint_artifact(artifact)
            if artifact.model_fingerprint != case.model_fingerprint:
                raise PipelineError("Артефакт ссылается на другую версию модели")
            case.artifact = artifact
            review = JavaReview.model_validate(
                self.reviewer.review(
                    case.requirements,
                    case.model,
                    artifact,
                    case.model_fingerprint,
                )
            )
            if (
                review.model_fingerprint != case.model_fingerprint
                or review.artifact_fingerprint != artifact_fingerprint
            ):
                raise PipelineError("Результат reviewer относится к другой модели или артефакту")
            case.review = review
            if not review.approved or any(item.severity == ReviewSeverity.ERROR for item in review.findings):
                return self._report(case, "REVIEW_REJECTED", "Reviewer отклонил Java-артефакт")
            check = self.runner(artifact, case.model)
            case.check = JavaCheckResult.model_validate(check)
            if case.check.status != JavaCheckStatus.PASSED:
                return self._report(case, "JAVA_CHECK_FAILED", "Java-артефакт не прошёл компиляцию или поведенческую проверку")
            return self._report(case, "READY", "Java-артефакт прошёл reviewer и поведенческую проверку")
        except PipelineError:
            raise
        except Exception as error:
            return self._report(case, "PIPELINE_ERROR", str(error))

    def _report(self, case: CaseState, status: str, message: str) -> PipelineReport:
        return PipelineReport(
            case_id=case.case_id,
            status=status,
            model_fingerprint=case.model_fingerprint,
            artifact=case.artifact,
            review=case.review,
            compile_and_check=case.check,
            message=message,
        )

    def report(self, case_id: str) -> PipelineReport:
        case = self._case(case_id)
        if case.check is not None:
            status = "READY" if case.check.status == JavaCheckStatus.PASSED else "JAVA_CHECK_FAILED"
        elif case.review is not None:
            status = "REVIEW_REJECTED" if not case.review.approved else "REVIEWED"
        elif case.artifact is not None:
            status = "GENERATED"
        elif case.accepted:
            status = "ACCEPTED"
        else:
            status = "ANALYZED"
        return self._report(case, status, None)
