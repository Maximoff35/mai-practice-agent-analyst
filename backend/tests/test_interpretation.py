"""API переносит самооценку LLM без автоматического исправления модели."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from analyst import AnalystAgent, MAIProvider
from api.main import app, get_agent
from model_checker import VerificationResult, VerificationStatus, validate_model


@pytest.mark.parametrize("requirements,assumptions,questions", [
    ("Изначально Created, Execute при approved=true; запрет исполнения отменённой заявки.", [], []),
    ("Заявка после согласования может быть исполнена. Пользователь может отменить заявку до исполнения.",
     ["Начальное состояние Created предположено.", "Execute разрешён только из Approved: предположение."],
     ["Каково начальное состояние?", "Можно ли исполнять после отмены?"]),
    ("Заявку можно исполнить. Проверь, что всё безопасно.", ["Конкретный запрет безопасности предложен агентом."],
     ["Что считать безопасным поведением?", "Каковы guards и effects?"]),
])
def test_api_keeps_interpretation_and_model(fixed_model, requirements, assumptions, questions):
    original = json.loads(json.dumps(fixed_model))
    name = fixed_model["properties"][0]["name"]
    fixed_model["interpretation"] = {
        "assumptions": assumptions, "questions": questions,
        "property_rationale": {name: "Проверка запрета исполнения отменённой заявки."},
    }

    def handler(request):
        payload = json.loads(request.content)
        content = json.dumps(fixed_model) if "response_format" in payload else "Проверьте предположения агента."
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        agent = AnalystAgent(MAIProvider("offline", "test", client=client),
                             lambda _: VerificationResult(status=VerificationStatus.PROPERTY_HOLDS))
        app.dependency_overrides[get_agent] = lambda: agent
        try:
            response = TestClient(app).post("/api/analyze", json={"requirements": requirements})
        finally:
            app.dependency_overrides.clear()
    assert response.status_code == 200
    model = response.json()["behavioral_model"]
    assert model.pop("interpretation") == fixed_model["interpretation"]
    assert model == original


def test_unknown_property_rationale_is_invalid(fixed_model):
    fixed_model["interpretation"] = {"property_rationale": {"Unknown": "Неизвестное свойство"}}
    with pytest.raises(ValueError, match="unknown properties"):
        validate_model(fixed_model)
