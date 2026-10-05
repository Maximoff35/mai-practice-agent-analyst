from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from analyst import AnalystAgent, FakeLLMProvider
from api.main import app
from model_checker import VerificationResult, VerificationStatus


DEMO_REQUIREMENTS = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)
FIXED_REQUIREMENTS = DEMO_REQUIREMENTS + " При отмене заявки approved = false."


def test_fake_provider_matches_acceptance_fixtures(buggy_model, fixed_model):
    provider = FakeLLMProvider()
    assert provider.build_model(DEMO_REQUIREMENTS).model_dump(mode="json") == buggy_model
    assert provider.build_model(FIXED_REQUIREMENTS).model_dump(mode="json") == fixed_model


def test_agent_calls_checker_once_and_returns_structured_result():
    calls = []

    def checker(model):
        calls.append(model)
        return VerificationResult(status=VerificationStatus.PROPERTY_HOLDS)

    result = AnalystAgent(FakeLLMProvider(), checker=checker).analyze(FIXED_REQUIREMENTS)
    assert len(calls) == 1
    assert result.behavioral_model == calls[0]
    assert result.verification_result.status == VerificationStatus.PROPERTY_HOLDS
    assert result.counterexample is None
    assert "не нашёл" in result.explanation


def test_agent_accepts_another_provider_without_changes(buggy_model):
    class OtherProvider:
        def build_model(self, requirements):
            from model_checker import BehavioralModel

            return BehavioralModel.model_validate(buggy_model)

        def explain_result(self, requirements, model, result):
            return "Объяснение другого провайдера"

    agent = AnalystAgent(
        OtherProvider(),
        checker=lambda model: VerificationResult(status=VerificationStatus.PROPERTY_HOLDS),
    )
    result = agent.analyze("Любой текст")
    assert result.explanation == "Объяснение другого провайдера"


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("payload", [{}, {"requirements": "   "}])
def test_analyze_rejects_empty_requirements(payload):
    response = TestClient(app).post("/api/analyze", json=payload)
    assert response.status_code == 422


def test_fake_provider_rejects_unrelated_requirements():
    response = TestClient(app).post("/api/analyze", json={"requirements": "Проверить движение лифта"})
    assert response.status_code == 422
    assert "демонстрационный сценарий" in response.json()["detail"]


@pytest.fixture
def configured_tlc(monkeypatch):
    tools = Path(__file__).parents[1] / ".tools"
    java = tools / "java" / "bin" / "java.exe"
    jar = tools / "tla2tools.jar"
    if not java.is_file() or not jar.is_file():
        pytest.skip("Локальные Java и TLC не настроены")
    monkeypatch.setenv("MODEL_CHECKER_JAVA", str(java))
    monkeypatch.setenv("MODEL_CHECKER_TLA2TOOLS_JAR", str(jar))
    monkeypatch.setenv("MODEL_CHECKER_TEMP_DIR", str(tools))


@pytest.mark.integration
def test_analyze_buggy_model_with_real_tlc(configured_tlc):
    response = TestClient(app).post("/api/analyze", json={"requirements": DEMO_REQUIREMENTS})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requirements"] == DEMO_REQUIREMENTS
    assert body["behavioral_model"]["initial"]["status"] == "Created"
    assert body["verification_result"]["status"] == "PROPERTY_VIOLATED"
    assert [state["values"]["status"] for state in body["counterexample"]] == [
        "Created", "Approved", "Cancelled", "Executed"
    ]
    assert [state["transition"] for state in body["counterexample"]] == [
        None, "Approve", "Cancel", "Execute"
    ]
    assert "approved остаётся true" in body["explanation"]
    assert "отменённая заявка" in body["explanation"]


@pytest.mark.integration
def test_analyze_fixed_model_with_real_tlc(configured_tlc):
    response = TestClient(app).post("/api/analyze", json={"requirements": FIXED_REQUIREMENTS})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requirements"] == FIXED_REQUIREMENTS
    assert body["verification_result"]["status"] == "PROPERTY_HOLDS"
    assert body["counterexample"] is None
    assert "не нашёл" in body["explanation"]
