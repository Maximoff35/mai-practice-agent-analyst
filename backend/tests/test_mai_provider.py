import json

import httpx
import pytest
from fastapi.testclient import TestClient

from analyst import AnalystAgent, MAIAPIError, MAIConfigurationError, MAIProvider, MAIResponseError
from analyst import config as analyst_config
from api.main import app, get_agent
from model_checker import VerificationResult, VerificationStatus


def completion(content, **overrides):
    return {"model": "test-model", "choices": [{"message": {"content": content}, "finish_reason": "stop"}], **overrides}


def test_mai_builds_and_explains_through_documented_api(buggy_model):
    requests = []

    def handler(request):
        requests.append(request)
        assert str(request.url) == "https://api-ai.mai.ru/v1/chat/completions"
        assert request.headers["x-litellm-api-key"] == "test-secret"
        assert request.extensions["timeout"]["read"] == 12
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["stream"] is False
        assert "provider" not in payload  # OpenRouter-specific options must not leak here.
        if len(requests) == 1:
            assert payload["response_format"] == {"type": "json_object"}
            assert payload["messages"][1]["content"] == "Требования"
            return httpx.Response(200, json=completion(json.dumps(buggy_model)))
        assert "response_format" not in payload
        context = json.loads(payload["messages"][1]["content"])
        assert context["verification_result"]["status"] == "PROPERTY_HOLDS"
        assert "stdout" not in context["verification_result"]
        assert "stderr" not in context["verification_result"]
        return httpx.Response(200, json=completion("Свойство не нарушено в конечной модели."))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = MAIProvider("test-secret", "test-model", timeout_seconds=12, client=client)
        result = AnalystAgent(
            provider, lambda model: VerificationResult(status=VerificationStatus.PROPERTY_HOLDS, stdout="private log")
        ).analyze("Требования")
    assert result.behavioral_model.model_dump(mode="json") == buggy_model
    assert result.explanation == "Свойство не нарушено в конечной модели."
    assert provider.response_models == ["test-model", "test-model"]
    assert len(requests) == 2


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_mai_http_errors_do_not_expose_response_or_key(status):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": {"message": "test-secret"}})
    )) as client:
        with pytest.raises(MAIAPIError, match=f"HTTP {status}") as failure:
            MAIProvider("test-secret", "test-model", client=client).build_model("Требования")
    assert "test-secret" not in str(failure.value)


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_mai_transport_errors_are_sanitized(error_type):
    def handler(request):
        raise error_type("test-secret", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MAIAPIError, match=error_type.__name__) as failure:
            MAIProvider("test-secret", "test-model", client=client).build_model("Требования")
    assert "test-secret" not in str(failure.value)


@pytest.mark.parametrize("body", [
    {}, [], None, {"choices": []}, completion(""), completion(None), completion("{broken"),
    completion("{}"), completion('{"secret":"test-secret"}'),
    completion("{}", choices=[{"message": {"content": "{}"}, "finish_reason": "length"}]),
])
def test_mai_rejects_invalid_responses_before_checker(body):
    def checker(model):
        pytest.fail("Невалидная модель не должна дойти до TLC")

    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
        with pytest.raises(MAIResponseError) as failure:
            AnalystAgent(MAIProvider("test-secret", "test-model", client=client), checker).analyze("Требования")
    assert "test-secret" not in str(failure.value)


def test_mai_rejects_semantically_invalid_model(buggy_model):
    buggy_model["transitions"][0]["guard"] = {"eq": [{"var": "unknown"}, True]}
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=completion(json.dumps(buggy_model)))
    )) as client:
        with pytest.raises(MAIResponseError):
            MAIProvider("test-secret", "test-model", client=client).build_model("Требования")


def test_mai_rejects_boolean_bounds_seen_in_live_response(buggy_model):
    buggy_model["variables"][1].update(min=False, max=True)
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=completion(json.dumps(buggy_model)))
    )) as client:
        with pytest.raises(MAIResponseError):
            MAIProvider("test-secret", "test-model", client=client).build_model("Требования")


def test_mai_rejects_error_payload_and_non_json():
    for response in [httpx.Response(200, json={"error": "test-secret"}), httpx.Response(200, text="not json")]:
        with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
            with pytest.raises((MAIAPIError, MAIResponseError)) as failure:
                MAIProvider("test-secret", "test-model", client=client).build_model("Требования")
        assert "test-secret" not in str(failure.value)


@pytest.mark.parametrize("settings", [
    {"api_key": ""}, {"model": ""}, {"timeout_seconds": 0}, {"timeout_seconds": float("nan")},
    {"base_url": "http://example.com"}, {"base_url": "https://example.com/?key=secret"},
])
def test_mai_configuration_is_validated(settings):
    with pytest.raises(MAIConfigurationError):
        MAIProvider(**({"api_key": "test-secret", "model": "test-model"} | settings))


def test_mai_configuration_and_api_selection(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('MAI_API_KEY="file-key"\nMAI_MODEL=file-model\n', encoding="utf-8")
    monkeypatch.setattr(analyst_config, "ENV_FILE", env_file)
    for name in ["MAI_API_KEY", "MAI_MODEL", "MAI_BASE_URL", "MAI_TIMEOUT_SECONDS"]:
        monkeypatch.delenv(name, raising=False)
    assert MAIProvider.from_env().model == "file-model"
    monkeypatch.setenv("LLM_PROVIDER", "mai")
    monkeypatch.setenv("MAI_MODEL", "override-model")
    assert isinstance(get_agent().provider, MAIProvider)
    assert get_agent().provider.model == "override-model"
    monkeypatch.setenv("MAI_API_KEY", "")
    response = TestClient(app).post("/api/analyze", json={"requirements": "Требования"})
    assert response.status_code == 503
    assert "MAI_API_KEY" in response.json()["detail"]
    monkeypatch.setenv("MAI_API_KEY", "test-secret")
    monkeypatch.setenv("MAI_TIMEOUT_SECONDS", "invalid")
    assert TestClient(app).post("/api/analyze", json={"requirements": "Требования"}).status_code == 503


def test_mai_build_error_returns_502():
    class UnavailableProvider:
        def build_model(self, requirements):
            raise MAIAPIError("API МАИ вернул HTTP 401")

    app.dependency_overrides[get_agent] = lambda: AnalystAgent(UnavailableProvider())
    try:
        response = TestClient(app).post("/api/analyze", json={"requirements": "Требования"})
    finally:
        app.dependency_overrides.pop(get_agent, None)
    assert response.status_code == 502
    assert "behavioral_model" not in response.json()
