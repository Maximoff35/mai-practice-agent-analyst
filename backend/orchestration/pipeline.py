"""Stateful orchestration of accepted models and Java verification stages."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import io
import time
from threading import Lock
from zipfile import ZipFile, ZIP_DEFLATED
from typing import Protocol
from uuid import uuid4

from analyst import AnalysisResult, AnalystAgent
from java_runner import JavaArtifact, JavaCheckResult, JavaCheckStatus, run_java_module
from java_runner.identity import fingerprint_artifact, fingerprint_model
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
    status: str = "ANALYZED"
    message: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    lock: object = field(default_factory=Lock, repr=False)


@dataclass
class CasePipeline:
    agent: AnalystAgent
    generator: ArtifactGenerator = field(default_factory=UnavailableGenerator)
    reviewer: Reviewer = field(default_factory=UnavailableReviewer)
    runner: object = run_java_module
    cases: dict[str, CaseState] = field(default_factory=dict)
    ttl_seconds: float = 3600
    max_cases: int = 64
    store_lock: object = field(default_factory=Lock, repr=False)

    def _prune(self):
        now = time.monotonic()
        for identifier, case in list(self.cases.items()):
            if now - case.created_at >= self.ttl_seconds and not case.lock.locked():
                del self.cases[identifier]

    def analyze(self, requirements: str) -> CaseAnalysis:
        with self.store_lock:
            self._prune()
            if len(self.cases) >= self.max_cases:
                raise PipelineError("Хранилище кейсов заполнено; удалите старый кейс")
        analysis = self.agent.analyze(requirements)
        case_id = uuid4().hex
        model_fingerprint = fingerprint_model(analysis.behavioral_model)
        with self.store_lock:
            self._prune()
            if len(self.cases) >= self.max_cases:
                raise PipelineError("Хранилище кейсов заполнено")
            self.cases[case_id] = CaseState(case_id, requirements, analysis.behavioral_model,
                                            analysis, model_fingerprint)
        return CaseAnalysis(case_id=case_id, model_fingerprint=model_fingerprint, analysis=analysis.model_copy(deep=True))

    def _case(self, case_id: str) -> CaseState:
        with self.store_lock:
            self._prune()
            try:
                return self.cases[case_id]
            except KeyError as error:
                raise CaseNotFoundError("Кейс не найден или срок его хранения истёк") from error

    def accept(self, acceptance: CaseAcceptance) -> CaseAnalysis:
        case = self._case(acceptance.case_id)
        if not acceptance.accepted:
            raise PipelineError("Необходимо явное accepted=true")
        if acceptance.model_fingerprint != case.model_fingerprint or fingerprint_model(case.model) != case.model_fingerprint:
            raise PipelineError("Версия модели не совпадает с сохранённым анализом")
        verification = case.analysis.verification_result
        if verification.status != VerificationStatus.PROPERTY_HOLDS or any(item.status != VerificationStatus.PROPERTY_HOLDS for item in verification.property_results):
            raise PipelineError("Генерация разрешена только после успешной проверки всех свойств")
        case.accepted = True
        if case.status == "ANALYZED":
            case.status = "ACCEPTED"
        return CaseAnalysis(
            case_id=case.case_id,
            model_fingerprint=case.model_fingerprint,
            analysis=case.analysis.model_copy(deep=True),
            accepted=True,
        )

    def generate(self, case_id: str) -> PipelineReport:
        case = self._case(case_id)
        if not case.accepted:
            raise PipelineError("Сначала явно примите модель после успешной проверки")
        if fingerprint_model(case.model) != case.model_fingerprint:
            case.accepted = False
            raise PipelineError("Модель изменилась; необходим новый анализ и принятие")
        if not case.lock.acquire(blocking=False):
            raise PipelineError("Генерация этого кейса уже выполняется")
        case.artifact = case.review = case.check = None
        case.status, case.message = "GENERATING", None
        try:
            artifact = self.generator.generate(case.requirements, case.model, case.model_fingerprint)
            artifact = JavaArtifact.model_validate(artifact).model_copy(deep=True)
            artifact_fingerprint = fingerprint_artifact(artifact)
            if artifact.model_fingerprint != case.model_fingerprint:
                raise PipelineError("Артефакт ссылается на другую версию модели")
            case.artifact = artifact
            case.status = "GENERATED"
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
            paths = {source.path: len(source.content.splitlines()) for source in artifact.files}
            for finding in review.findings:
                if finding.file is not None and (finding.file not in paths or (finding.line is not None and finding.line > paths[finding.file])):
                    raise PipelineError("Reviewer указал несуществующий файл/строку")
            if not review.approved or any(item.severity == ReviewSeverity.ERROR for item in review.findings):
                return self._report(case, "REVIEW_REJECTED", "Reviewer отклонил Java-артефакт")
            case.status = "REVIEWED"
            check = self.runner(artifact, case.model)
            case.check = JavaCheckResult.model_validate(check)
            if case.check.model_fingerprint != case.model_fingerprint or case.check.artifact_fingerprint != artifact_fingerprint:
                raise PipelineError("Проверка Java относится к другой модели или исходникам")
            if case.check.status != JavaCheckStatus.PASSED:
                return self._report(case, "JAVA_CHECK_FAILED", "Java-артефакт не прошёл компиляцию или поведенческую проверку")
            if case.check.compilation != "PASSED" or case.check.coverage != "COMPLETE_STATE_EVENT":
                raise PipelineError("Недостаточно свидетельств компиляции и покрытия")
            if fingerprint_model(case.model) != case.model_fingerprint or fingerprint_artifact(artifact) != artifact_fingerprint:
                raise PipelineError("Модель или исходники изменились во время проверки")
            return self._report(case, "READY", "Java-артефакт прошёл reviewer и поведенческую проверку")
        except Exception:
            return self._report(case, "PIPELINE_ERROR", "Этап Java не завершён; проверьте настройки и соответствие версий")
        finally:
            case.lock.release()

    def _report(self, case: CaseState, status: str, message: str | None, *, persist: bool = True) -> PipelineReport:
        if persist:
            case.status, case.message = status, message
        return PipelineReport(
            case_id=case.case_id,
            status=status,
            model_fingerprint=case.model_fingerprint,
            artifact=case.artifact.model_copy(deep=True) if case.artifact else None,
            artifact_fingerprint=fingerprint_artifact(case.artifact) if case.artifact else None,
            review=case.review.model_copy(deep=True) if case.review else None,
            compile_and_check=case.check.model_copy(deep=True) if case.check else None,
            message=message,
        )

    def report(self, case_id: str) -> PipelineReport:
        case = self._case(case_id)
        # Не выводим READY из старого check после ошибки нового запуска.
        return self._report(case, case.status, case.message, persist=False)

    def delete(self, case_id: str):
        case = self._case(case_id)
        if not case.lock.acquire(blocking=False):
            raise PipelineError("Кейс занят; повторите удаление после завершения")
        try:
            with self.store_lock:
                self.cases.pop(case_id, None)
        finally:
            case.lock.release()

    def download(self, case_id: str) -> bytes:
        case = self._case(case_id)
        if not case.lock.acquire(blocking=False):
            raise PipelineError("Дождитесь окончания генерации")
        try:
            if case.artifact is None:
                raise PipelineError("Исходники ещё не сгенерированы")
            buffer = io.BytesIO()
            with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
                for source in case.artifact.files:
                    archive.writestr("sources/" + source.path, source.content)
                archive.writestr("report.json", self.report(case_id).model_dump_json(indent=2))
                archive.writestr("model.json", case.model.model_dump_json(indent=2))
                archive.writestr("README.txt", "Сгенерированный Java-модуль. Статус и отпечатки — report.json.\n"
                                 "LLM-ревью и тесты не доказывают эквивалентность Java.\n"
                                 + (getattr(case.artifact, "instruction", None) or ""))
            return buffer.getvalue()
        finally:
            case.lock.release()
