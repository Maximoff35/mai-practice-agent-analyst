"""Старое READY, ложное принятие и подменённые результаты не проходят API."""

import io
import json
from zipfile import ZipFile

import pytest

from orchestration import CaseAcceptance, PipelineError, CaseNotFoundError
from test_orchestration import make_pipeline, REQUIREMENTS, Generator, passed_runner


def accepted(pipeline):
    case = pipeline.analyze(REQUIREMENTS)
    pipeline.accept(CaseAcceptance(case_id=case.case_id, model_fingerprint=case.model_fingerprint))
    return case


def test_false_acceptance_and_mutated_client_model():
    pipeline = make_pipeline()
    case = pipeline.analyze(REQUIREMENTS)
    case.analysis.behavioral_model.initial["approved"] = True
    assert pipeline.cases[case.case_id].model.initial["approved"] is False
    with pytest.raises(PipelineError, match="accepted=true"):
        pipeline.accept(CaseAcceptance(case_id=case.case_id, model_fingerprint=case.model_fingerprint, accepted=False))


def test_failed_retry_clears_old_ready_and_does_not_leak_secret():
    pipeline = make_pipeline()
    case = accepted(pipeline)
    assert pipeline.generate(case.case_id).status == "READY"
    class Fails:
        def generate(self, *args):
            raise RuntimeError("secret-provider-key")
    pipeline.generator = Fails()
    result = pipeline.generate(case.case_id)
    assert result.status == pipeline.report(case.case_id).status == "PIPELINE_ERROR"
    assert result.artifact is result.review is result.compile_and_check is None
    assert "secret-provider-key" not in result.model_dump_json()


@pytest.mark.parametrize("bad_field", ["model_fingerprint", "artifact_fingerprint", "coverage", "compilation"])
def test_forged_java_evidence_is_not_ready(bad_field):
    def runner(artifact, model):
        result = passed_runner(artifact, model)
        setattr(result, bad_field, "forged")
        return result
    pipeline = make_pipeline(runner=runner)
    case = accepted(pipeline)
    assert pipeline.generate(case.case_id).status == "PIPELINE_ERROR"
    assert pipeline.report(case.case_id).status == "PIPELINE_ERROR"


def test_download_is_bound_to_stored_artifact_and_delete_expires_case():
    pipeline = make_pipeline()
    case = accepted(pipeline)
    result = pipeline.generate(case.case_id)
    with ZipFile(io.BytesIO(pipeline.download(case.case_id))) as archive:
        report = json.loads(archive.read("report.json"))
        assert report["artifact_fingerprint"] == result.artifact_fingerprint
        assert archive.read("sources/Machine.java").decode() == result.artifact.files[0].content
    pipeline.delete(case.case_id)
    with pytest.raises(CaseNotFoundError):
        pipeline.report(case.case_id)


def test_expiry_capacity_and_duplicate_generation():
    pipeline = make_pipeline()
    pipeline.max_cases = 1
    case = accepted(pipeline)
    with pytest.raises(PipelineError, match="заполнено"):
        pipeline.analyze(REQUIREMENTS)
    state = pipeline.cases[case.case_id]
    state.lock.acquire()
    try:
        with pytest.raises(PipelineError, match="уже выполняется"):
            pipeline.generate(case.case_id)
    finally:
        state.lock.release()
    state.created_at -= pipeline.ttl_seconds + 1
    with pytest.raises(CaseNotFoundError):
        pipeline.report(case.case_id)


def test_delete_during_generation_revokes_pending_result():
    pipeline = make_pipeline()
    case = accepted(pipeline)
    class DeletingGenerator(Generator):
        def generate(self, *args):
            pipeline.delete(case.case_id)
            return super().generate(*args)
    pipeline.generator = DeletingGenerator()
    result = pipeline.generate(case.case_id)
    assert result.status == "PIPELINE_ERROR"
    assert result.artifact is result.review is result.compile_and_check is None
    with pytest.raises(CaseNotFoundError):
        pipeline.report(case.case_id)
