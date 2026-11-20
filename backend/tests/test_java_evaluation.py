"""Записи МАИ повторяются без сети; Java проверяется отдельно реальным JDK."""

import json
import os
from pathlib import Path

import httpx
import pytest

from analyst import AnalystAgent, JavaGenerator, MAIProvider
from analyst.java_reviewer import JavaReviewer
from evaluation.run_java_mai import RecordedModelProvider
from java_runner import JavaArtifact, JavaCheckResult, JavaCheckStatus, run_java_module
from java_runner.identity import fingerprint_artifact, fingerprint_model
from model_checker import VerificationResult, validate_model
from orchestration import CaseAcceptance, CasePipeline
from orchestration.schemas import JavaReview


directory = Path(__file__).parents[1] / "evaluation"
record = json.loads((directory / "recorded-java-mai.json").read_text(encoding="utf-8"))
scenarios = {row["id"]: row for row in json.loads((directory / "java-scenarios.json").read_text(encoding="utf-8"))}


@pytest.mark.parametrize("row", record["runs"][1:], ids=lambda row: row["id"])
def test_offline_replay_of_both_actual_models_and_pipeline(row):
    recorded = row["report"]
    model = validate_model(scenarios[row["id"]]["model"])
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload["model"])
        if payload["model"] == recorded["artifact"]["generator_model"]:
            content = recorded["artifact"]
        else:
            content = {key: recorded["review"][key] for key in ["approved", "findings", "message"]}
        return httpx.Response(200, json={"model": payload["model"], "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        pipeline = CasePipeline(
            AnalystAgent(RecordedModelProvider(model.model_dump(mode="json")),
                         lambda _: VerificationResult.model_validate(row["analysis"]["analysis"]["verification_result"])),
            generator=JavaGenerator(MAIProvider("offline", recorded["artifact"]["generator_model"], client=client)),
            reviewer=JavaReviewer(MAIProvider("offline", recorded["review"]["reviewer_model"], client=client)),
            runner=lambda *a: JavaCheckResult.model_validate(recorded["compile_and_check"]),
        )
        case = pipeline.analyze(scenarios[row["id"]]["requirements"])
        pipeline.accept(CaseAcceptance(case_id=case.case_id, model_fingerprint=case.model_fingerprint))
        result = pipeline.generate(case.case_id)
    assert result.status == "READY"
    assert len(calls) == 2 and calls[0] != calls[1]
    assert result.artifact_fingerprint == fingerprint_artifact(result.artifact)
    assert result.model_fingerprint == fingerprint_model(model)


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("JAVA_RUNNER_INTEGRATION"), reason="Нужны локальные Docker/JDK")
@pytest.mark.parametrize("row", record["runs"][1:], ids=lambda row: row["id"])
def test_real_java_replay_of_generated_sources(row):
    result = run_java_module(JavaArtifact.model_validate(row["report"]["artifact"]), scenarios[row["id"]]["model"])
    assert result.status == JavaCheckStatus.PASSED, result
    assert result.checks_run == row["report"]["compile_and_check"]["checks_run"]


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("JAVA_RUNNER_INTEGRATION"), reason="Нужны локальные Docker/JDK")
@pytest.mark.parametrize("row", record["negative_fixtures"], ids=lambda row: row["id"])
def test_false_reviewer_approval_does_not_hide_real_java_defect(row, configured_tlc):
    artifact = JavaArtifact.model_validate(row["artifact"])
    class Generator:
        def generate(self, *args): return artifact
    class WrongReviewer:
        def review(self, requirements, model, source, model_fingerprint):
            return JavaReview(approved=True, findings=[], reviewer_model="forced-false-approval-fixture",
                              artifact_fingerprint=fingerprint_artifact(source), model_fingerprint=model_fingerprint)
    pipeline = CasePipeline(AnalystAgent(RecordedModelProvider(scenarios["application_fixed"]["model"])),
                            generator=Generator(), reviewer=WrongReviewer())
    case = pipeline.analyze(scenarios["application_fixed"]["requirements"])
    pipeline.accept(CaseAcceptance(case_id=case.case_id, model_fingerprint=case.model_fingerprint))
    result = pipeline.generate(case.case_id)
    assert result.status == "JAVA_CHECK_FAILED"
    assert result.compile_and_check.status.value == row["check"]["status"]
    assert pipeline.report(case.case_id).status == "JAVA_CHECK_FAILED"
