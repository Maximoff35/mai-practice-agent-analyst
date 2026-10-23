import json

import httpx
import pytest
from fastapi.testclient import TestClient

from analyst import AnalystAgent, MAIProvider, MAIResponseError, OpenRouterModelError, OpenRouterProvider
from api.main import app, get_agent
from model_checker import SourceReferenceValidationError, validate_model, validate_source_references, verify


@pytest.mark.parametrize("text,fragment", [
    ("[REQ-1] approve [REQ-1] cancel", "approve"),
    ("[REQ-1] approve [REQ-2] cancel", "cancel"),
    ("[REQ-1] approve", " "),
    ("[REQ-2] approve", "approve"),
])
def test_unconfirmed_reference_is_rejected(buggy_model, text, fragment):
    buggy_model["transitions"][0]["source_reference"] = {"id": "REQ-1", "fragment": fragment}
    with pytest.raises(SourceReferenceValidationError):
        validate_source_references(validate_model(buggy_model), text)


@pytest.mark.parametrize("provider_class,error_class", [
    (MAIProvider, MAIResponseError), (OpenRouterProvider, OpenRouterModelError),
])
def test_both_providers_validate_references(buggy_model, provider_class, error_class):
    buggy_model["properties"][0]["source_reference"] = {"id": "REQ-1", "fragment": "Запрет"}
    def handler(request):
        assert "source_reference" in json.loads(request.content)["messages"][0]["content"]
        return httpx.Response(200, json={"choices": [{
            "message": {"content": json.dumps(buggy_model)}, "finish_reason": "stop",
        }]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = provider_class("test-key", "test-model", client=client)
        assert provider.build_model("[REQ-1] Запрет").properties[0].source_reference.id == "REQ-1"
        with pytest.raises(error_class):
            provider.build_model("[REQ-2] Запрет")


@pytest.mark.integration
def test_api_returns_references_with_real_tlc_and_failed_explanation(buggy_model, configured_tlc):
    from model_checker import BehavioralModel
    buggy_model["properties"][0]["source_reference"] = {"id": "R1", "fragment": "Не исполнять отменённую заявку"}
    buggy_model["transitions"][1]["source_reference"] = {"id": "R2", "fragment": "Отмена сохраняет approved"}
    class Provider:
        def build_model(self, requirements):
            return BehavioralModel.model_validate(buggy_model)
        def explain_result(self, requirements, model, result):
            raise RuntimeError("LLM unavailable")
    app.dependency_overrides[get_agent] = lambda: AnalystAgent(Provider(), verify)
    try:
        response = TestClient(app).post("/api/analyze", json={
            "requirements": "[R1] Не исполнять отменённую заявку. [R2] Отмена сохраняет approved.",
        })
    finally:
        app.dependency_overrides.pop(get_agent, None)
    assert response.status_code == 200
    body = response.json()
    assert body["verification_result"]["status"] == "PROPERTY_VIOLATED"
    assert [ref["id"] for ref in body["related_requirements"]] == ["R1", "R2"]
    assert body["counterexample"][2]["related_requirements"][0]["id"] == "R2"
    assert "Шаблонное сообщение" in body["explanation"]
