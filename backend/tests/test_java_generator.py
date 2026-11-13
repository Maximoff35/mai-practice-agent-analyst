import json

import httpx
import pytest

from analyst import JavaGenerationError, JavaGenerator, MAIAPIError, MAIProvider
from model_checker import BehavioralModel
from orchestration.pipeline import fingerprint_model


def completion(content, **overrides):
    return {
        "model": "generator-response",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        **overrides,
    }


def generator_artifact(model_fingerprint):
    return {
        "model_fingerprint": model_fingerprint,
        "main_class": "Machine",
        "files": [{"path": "Machine.java", "content": "public class Machine {}"}],
        "instruction": "READY/SNAPSHOT/FIRE",
    }


def test_java_generator_sends_model_and_uses_separate_model(buggy_model):
    requests = []
    model = BehavioralModel.model_validate(buggy_model)
    fingerprint = fingerprint_model(model)
    artifact = generator_artifact(fingerprint)

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion(json.dumps(artifact)))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generator = JavaGenerator(MAIProvider("test-secret", "generator-model", client=client))
        result = generator.generate("Требования", model, fingerprint)

    assert result.model_fingerprint == fingerprint
    assert requests[0]["model"] == "generator-model"
    context = json.loads(requests[0]["messages"][1]["content"])
    assert context["requirements"] == "Требования"
    assert context["model_fingerprint"] == fingerprint
    assert context["behavioral_model"] == buggy_model
    assert requests[0]["response_format"] == {"type": "json_object"}


def test_java_generator_rejects_mismatched_model_fingerprint(buggy_model):
    model = BehavioralModel.model_validate(buggy_model)
    artifact = generator_artifact("other-model")
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=completion(json.dumps(artifact)))
    )) as client:
        generator = JavaGenerator(MAIProvider("test-secret", "generator-model", client=client))

        with pytest.raises(JavaGenerationError, match="другой версии"):
            generator.generate(
                "Требования",
                model,
                "expected-model",
            )


@pytest.mark.parametrize("content", [
    "not-json",
    json.dumps({"model_fingerprint": "m", "main_class": "Machine", "files": []}),
    json.dumps({
        "model_fingerprint": "m",
        "main_class": "Machine",
        "files": [{"path": "../Machine.java", "content": "class Machine {}"}],
    }),
])
def test_java_generator_rejects_invalid_structured_response(content, buggy_model):
    model = BehavioralModel.model_validate(buggy_model)
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=completion(content))
    )) as client:
        generator = JavaGenerator(MAIProvider("test-secret", "generator-model", client=client))

        with pytest.raises(JavaGenerationError):
            generator.generate(
                "Требования",
                model,
                "m",
            )


def test_java_generator_preserves_provider_errors(buggy_model):
    model = BehavioralModel.model_validate(buggy_model)
    def handler(request):
        return httpx.Response(503, json={"error": {"message": "secret"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        generator = JavaGenerator(MAIProvider("test-secret", "generator-model", client=client))

        with pytest.raises(MAIAPIError) as failure:
            generator.generate(
                "Требования",
                model,
                "m",
            )

    assert "secret" not in str(failure.value)
