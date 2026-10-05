import json

import httpx
import pytest
from fastapi import HTTPException

from analyst import (
    AnalystAgent,
    FakeLLMProvider,
    OpenRouterAPIError,
    OpenRouterModelError,
    OpenRouterProvider,
    OpenRouterResponseError,
)
from analyst import config as analyst_config
from api.main import get_agent
from model_checker import TraceState, VerificationResult, VerificationStatus


REQUIREMENTS = "Пользователь согласует заявку и может отменить её до исполнения."


def _response(content, model="google/example:free"):
    return {"model": model, "choices": [{"finish_reason": "stop", "message": {"content": content}}]}


def test_openrouter_builds_valid_model_with_structured_request(buggy_model):
    requests = []

    def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        assert payload["model"] == "openrouter/free"
        assert payload["messages"][1]["content"] == REQUIREMENTS
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["provider"]["require_parameters"] is True
        return httpx.Response(200, json=_response(json.dumps(buggy_model)))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OpenRouterProvider("test-key", "openrouter/free", client=client)
        model = provider.build_model(REQUIREMENTS)
    assert model.model_dump(mode="json") == buggy_model
    assert provider.response_models == ["google/example:free"]
    assert len(requests) == 1


def test_openrouter_rejects_invalid_json():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=_response("{broken")))
    with httpx.Client(transport=transport) as client:
        provider = OpenRouterProvider("test-key", "openrouter/free", client=client)
        with pytest.raises(OpenRouterResponseError, match="невалидный JSON"):
            provider.build_model(REQUIREMENTS)


def test_openrouter_rejects_invalid_model(buggy_model):
    buggy_model["initial"].pop("approved")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=_response(json.dumps(buggy_model))))
    with httpx.Client(transport=transport) as client:
        provider = OpenRouterProvider("test-key", "openrouter/free", client=client)
        with pytest.raises(OpenRouterModelError, match="невалидную BehavioralModel"):
            provider.build_model(REQUIREMENTS)


def test_openrouter_reports_api_error_without_key():
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"message": "invalid key"}}))
    with httpx.Client(transport=transport) as client:
        provider = OpenRouterProvider("test-secret", "openrouter/free", client=client)
        with pytest.raises(OpenRouterAPIError, match="HTTP 401") as failure:
            provider.build_model(REQUIREMENTS)
    assert "test-secret" not in str(failure.value)


def test_openrouter_reports_error_payload_even_with_http_200():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"error": {"message": "No endpoints found"}})
    )
    with httpx.Client(transport=transport) as client:
        provider = OpenRouterProvider("test-key", "openrouter/free", client=client)
        with pytest.raises(OpenRouterAPIError, match="No endpoints found"):
            provider.build_model(REQUIREMENTS)


def test_openrouter_explains_checker_result(buggy_model):
    from model_checker import BehavioralModel

    model = BehavioralModel.model_validate(buggy_model)
    result = VerificationResult(
        status=VerificationStatus.PROPERTY_VIOLATED,
        violated_property="NoExecutedAfterCancel",
        counterexample=[
            TraceState(number=1, values={"status": "Created", "approved": False, "cancelled": False}),
            TraceState(number=2, values={"status": "Executed", "approved": True, "cancelled": True}, transition="Execute"),
        ],
        stdout="technical log must not be sent",
    )

    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "openrouter/free"
        assert "response_format" not in payload
        context = json.loads(payload["messages"][1]["content"])
        assert context["requirements"] == REQUIREMENTS
        assert context["behavioral_model"]["initial"]["status"] == "Created"
        assert context["verification_result"]["status"] == "PROPERTY_VIOLATED"
        assert context["counterexample"][1]["transition"] == "Execute"
        assert "technical log must not be sent" not in request.content.decode("utf-8")
        return httpx.Response(200, json=_response("Отменённая заявка всё ещё может быть исполнена."))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OpenRouterProvider("test-key", "openrouter/free", client=client)
        explanation = provider.explain_result(REQUIREMENTS, model, result)
    assert explanation == "Отменённая заявка всё ещё может быть исполнена."


def test_local_env_file_and_environment_override(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('OPENROUTER_API_KEY="file-key"\nOPENROUTER_MODEL=openrouter/free\n', encoding="utf-8")
    monkeypatch.setattr(analyst_config, "ENV_FILE", env_file)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    provider = OpenRouterProvider.from_env()
    assert provider.model == "openrouter/free"
    monkeypatch.setenv("OPENROUTER_MODEL", "test/override")
    assert OpenRouterProvider.from_env().model == "test/override"


def test_provider_selection(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert isinstance(get_agent().provider, FakeLLMProvider)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    assert isinstance(get_agent().provider, OpenRouterProvider)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    with pytest.raises(HTTPException) as failure:
        get_agent()
    assert failure.value.status_code == 503
