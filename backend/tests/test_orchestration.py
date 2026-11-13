import pytest
from fastapi.testclient import TestClient

from analyst import AnalystAgent, FakeLLMProvider
from java_runner import JavaArtifact, JavaCheckResult, JavaCheckStatus, JavaSourceFile
from orchestration import CaseAcceptance, CasePipeline, PipelineError
from orchestration.pipeline import fingerprint_artifact
from orchestration.schemas import JavaReview, ReviewSeverity
from model_checker import VerificationResult, VerificationStatus
from api.main import app, get_pipeline


REQUIREMENTS = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения. "
    "При отмене заявки approved = false."
)


def _artifact(model_fingerprint: str) -> JavaArtifact:
    return JavaArtifact(
        files=[JavaSourceFile(path="Machine.java", content="class Machine {}")],
        main_class="Machine",
        model_fingerprint=model_fingerprint,
    )


class Generator:
    def generate(self, requirements, model, model_fingerprint):
        return _artifact(model_fingerprint)


class Reviewer:
    def __init__(self, approved=True):
        self.approved = approved

    def review(self, requirements, model, artifact, model_fingerprint):
        return JavaReview(
            approved=self.approved,
            findings=[] if self.approved else [
                {"severity": ReviewSeverity.ERROR, "message": "guard не проверен"}
            ],
            reviewer_model="reviewer-test",
            artifact_fingerprint=fingerprint_artifact(artifact),
            model_fingerprint=model_fingerprint,
        )


def passed_runner(artifact, model):
    return JavaCheckResult(status=JavaCheckStatus.PASSED, checks_run=1)


def failed_runner(artifact, model):
    return JavaCheckResult(
        status=JavaCheckStatus.BEHAVIOR_VIOLATED,
        message="Execute разрешён после Cancel",
        failed_check="Execute",
    )


def make_pipeline(checker=None, reviewer=None, runner=passed_runner):
    agent = AnalystAgent(
        FakeLLMProvider(),
        checker=checker or (lambda model: VerificationResult(status=VerificationStatus.PROPERTY_HOLDS)),
    )
    return CasePipeline(
        agent=agent,
        generator=Generator(),
        reviewer=reviewer or Reviewer(),
        runner=runner,
    )


def test_pipeline_requires_explicit_acceptance():
    pipeline = make_pipeline()
    case = pipeline.analyze(REQUIREMENTS)

    with pytest.raises(PipelineError, match="примите модель"):
        pipeline.generate(case.case_id)


def test_pipeline_rejects_forged_model_fingerprint():
    pipeline = make_pipeline()
    case = pipeline.analyze(REQUIREMENTS)

    with pytest.raises(PipelineError, match="Версия модели"):
        pipeline.accept(CaseAcceptance(case_id=case.case_id, model_fingerprint="forged"))


def test_pipeline_does_not_accept_violated_model():
    pipeline = make_pipeline(
        checker=lambda model: VerificationResult(status=VerificationStatus.PROPERTY_VIOLATED),
    )
    case = pipeline.analyze(REQUIREMENTS)

    with pytest.raises(PipelineError, match="успешной проверки"):
        pipeline.accept(CaseAcceptance(case_id=case.case_id, model_fingerprint=case.model_fingerprint))


def test_pipeline_ready_result_is_bound_to_one_model_and_artifact():
    pipeline = make_pipeline()
    case = pipeline.analyze(REQUIREMENTS)
    pipeline.accept(CaseAcceptance(case_id=case.case_id, model_fingerprint=case.model_fingerprint))

    report = pipeline.generate(case.case_id)

    assert report.status == "READY"
    assert report.artifact.model_fingerprint == case.model_fingerprint
    assert report.review.artifact_fingerprint == fingerprint_artifact(report.artifact)
    assert report.compile_and_check.status == JavaCheckStatus.PASSED


def test_reviewer_rejection_stops_before_java_runner():
    calls = []
    pipeline = make_pipeline(reviewer=Reviewer(approved=False), runner=lambda *args: calls.append(args))
    case = pipeline.analyze(REQUIREMENTS)
    pipeline.accept(CaseAcceptance(case_id=case.case_id, model_fingerprint=case.model_fingerprint))

    report = pipeline.generate(case.case_id)

    assert report.status == "REVIEW_REJECTED"
    assert report.compile_and_check is None
    assert calls == []


def test_java_failure_is_not_reported_as_ready():
    pipeline = make_pipeline(runner=failed_runner)
    case = pipeline.analyze(REQUIREMENTS)
    pipeline.accept(CaseAcceptance(case_id=case.case_id, model_fingerprint=case.model_fingerprint))

    report = pipeline.generate(case.case_id)

    assert report.status == "JAVA_CHECK_FAILED"
    assert report.compile_and_check.status == JavaCheckStatus.BEHAVIOR_VIOLATED


def test_pipeline_api_keeps_case_server_side_and_runs_stages():
    pipeline = make_pipeline()
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    try:
        client = TestClient(app)
        response = client.post("/api/v2/cases", json={"requirements": REQUIREMENTS})
        assert response.status_code == 200
        case = response.json()

        accepted = client.post(
            f"/api/v2/cases/{case['case_id']}/accept",
            json={
                "case_id": case["case_id"],
                "model_fingerprint": case["model_fingerprint"],
            },
        )
        assert accepted.status_code == 200

        generated = client.post(f"/api/v2/cases/{case['case_id']}/generate")
        assert generated.status_code == 200
        assert generated.json()["status"] == "READY"
    finally:
        app.dependency_overrides.pop(get_pipeline, None)
