import json

import httpx
import pytest

from analyst import MAIProvider, MAIAPIError
from analyst.java_reviewer import JavaReviewer, JavaReviewError
from java_runner import JavaArtifact
from java_runner.identity import fingerprint_artifact, fingerprint_model
from model_checker import validate_model


def review_fixture(fixed_model, verdict, *, actual="review-model", code=200):
    artifact = JavaArtifact(files=[{"path": "Machine.java", "content": "public class Machine {}"}],
                            main_class="Machine", generator_model="generator-model")
    model = validate_model(fixed_model)
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(code, json={"model": actual, "choices": [{"finish_reason": "stop",
                             "message": {"content": json.dumps(verdict) if not isinstance(verdict, str) else verdict}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = JavaReviewer(MAIProvider("secret-key", "requested-review", client=client)).review(
            "Требования", model, artifact, fingerprint_model(model))
    return result, artifact, calls


@pytest.mark.parametrize("approved", [True, False])
def test_review_bound_to_exact_sources_and_actual_role(fixed_model, approved):
    result, artifact, calls = review_fixture(fixed_model, {"approved": approved, "findings": []})
    assert result.approved is approved
    assert result.artifact_fingerprint == fingerprint_artifact(artifact)
    assert result.reviewer_model == "review-model"
    sent = json.loads(calls[0]["messages"][1]["content"])
    assert sent["artifact"]["files"] == [source.model_dump(mode="json") for source in artifact.files]
    assert calls[0]["model"] == "requested-review"
    assert "secret-key" not in json.dumps(sent)


@pytest.mark.parametrize("verdict", [
    "not-json", {"approved": "true"}, {"approved": True, "extra": 1},
    {"approved": False, "findings": [{"severity": "ERROR", "message": "guard", "file": "Unknown.java"}]},
    {"approved": False, "findings": [{"severity": "ERROR", "message": "guard", "file": "Machine.java", "line": 99}]},
    {"approved": False, "findings": [{"severity": "ERROR", "message": "guard", "transition": "Unknown"}]},
])
def test_invalid_review_is_not_approval(fixed_model, verdict):
    with pytest.raises(JavaReviewError):
        review_fixture(fixed_model, verdict)


def test_same_actual_model_cannot_review_own_code(fixed_model):
    with pytest.raises(JavaReviewError, match="разными"):
        review_fixture(fixed_model, {"approved": True}, actual="generator-model")


def test_provider_failure_is_not_approval(fixed_model):
    with pytest.raises(MAIAPIError):
        review_fixture(fixed_model, {"approved": True}, code=503)


@pytest.mark.parametrize("role", ["generator", "reviewer"])
def test_external_role_timeout_is_not_success(fixed_model, role):
    from analyst import JavaGenerator
    model = validate_model(fixed_model)
    artifact = JavaArtifact(files=[{"path": "Machine.java", "content": "class Machine {}"}], main_class="Machine")
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = MAIProvider("secret", "role-model", client=client)
        with pytest.raises(MAIAPIError):
            if role == "generator":
                JavaGenerator(provider).generate("Требования", model, fingerprint_model(model))
            else:
                JavaReviewer(provider).review("Требования", model, artifact, fingerprint_model(model))
