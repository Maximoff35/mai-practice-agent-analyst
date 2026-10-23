import pytest
from fastapi.testclient import TestClient

from analyst import AnalystAgent, FakeLLMProvider
from api.main import app, get_agent
from model_checker import TraceState, VerificationResult, VerificationStatus


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
    assert result.related_requirements == []
    assert result.verification_result.related_requirements == []
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


def test_agent_returns_verified_related_requirements(buggy_model):
    requirements = "[REQ-1] approve заявку. [REQ-2] cancel заявку."
    buggy_model["transitions"][0]["source_reference"] = {
        "id": "REQ-1",
        "fragment": "approve заявку.",
    }
    buggy_model["transitions"][1]["source_reference"] = {
        "id": "REQ-2",
        "fragment": "cancel заявку.",
    }
    buggy_model["properties"][0]["source_reference"] = {
        "id": "REQ-2",
        "fragment": "cancel заявку.",
    }

    class ReferencingProvider:
        def build_model(self, requirements):
            from model_checker import BehavioralModel

            return BehavioralModel.model_validate(buggy_model)

        def explain_result(self, requirements, model, result):
            return "Связанный результат"

    result = AnalystAgent(
        ReferencingProvider(),
        checker=lambda model: VerificationResult(
            status=VerificationStatus.PROPERTY_VIOLATED,
            violated_property="NoExecutedAfterCancel",
            counterexample=[
                TraceState(number=1, values={}, transition=None),
                TraceState(number=2, values={}, transition="Approve"),
                TraceState(number=3, values={}, transition="Cancel"),
            ],
        ),
    ).analyze(requirements)

    assert [reference.id for reference in result.related_requirements] == ["REQ-2", "REQ-1"]
    assert [reference.id for reference in result.counterexample[2].related_requirements] == ["REQ-2"]


@pytest.mark.parametrize("status", list(VerificationStatus))
def test_api_preserves_checked_result_when_explanation_fails(status):
    calls = []
    verification = VerificationResult(
        status=status,
        counterexample=[TraceState(number=1, values={"status": "Created"})]
        if status == VerificationStatus.PROPERTY_VIOLATED else [],
        statistics={"distinct_states": 4},
    )

    class FailingExplanationProvider(FakeLLMProvider):
        def explain_result(self, requirements, model, result):
            raise RuntimeError("secret-provider-response")

    def checker(model):
        calls.append(model)
        return verification

    app.dependency_overrides[get_agent] = lambda: AnalystAgent(FailingExplanationProvider(), checker)
    try:
        response = TestClient(app).post("/api/analyze", json={"requirements": DEMO_REQUIREMENTS})
    finally:
        app.dependency_overrides.pop(get_agent, None)

    assert response.status_code == 200
    body = response.json()
    assert len(calls) == 1
    assert body["behavioral_model"] == calls[0].model_dump(mode="json")
    assert body["verification_result"] == verification.model_dump(mode="json")
    assert body["counterexample"] == (verification.model_dump(mode="json")["counterexample"] or None)
    assert "Шаблонное сообщение" in body["explanation"]
    assert status.value in body["explanation"]
    assert "secret-provider-response" not in response.text


@pytest.mark.parametrize("explanation", ["", "  ", None])
def test_empty_explanation_uses_fallback(explanation):
    class EmptyExplanationProvider(FakeLLMProvider):
        def explain_result(self, requirements, model, result):
            return explanation

    result = AnalystAgent(
        EmptyExplanationProvider(),
        checker=lambda model: VerificationResult(status=VerificationStatus.TIMEOUT),
    ).analyze(DEMO_REQUIREMENTS)
    assert result.verification_result.status == VerificationStatus.TIMEOUT
    assert "Шаблонное сообщение" in result.explanation


def test_model_construction_failure_still_returns_api_error():
    from analyst import OpenRouterAPIError

    class FailingModelProvider(FakeLLMProvider):
        def build_model(self, requirements):
            raise OpenRouterAPIError("OpenRouter API вернул HTTP 503")

    def unexpected_checker(model):
        pytest.fail("Checker не должен запускаться без модели")

    app.dependency_overrides[get_agent] = lambda: AnalystAgent(FailingModelProvider(), unexpected_checker)
    try:
        response = TestClient(app).post("/api/analyze", json={"requirements": DEMO_REQUIREMENTS})
    finally:
        app.dependency_overrides.pop(get_agent, None)
    assert response.status_code == 502
    assert "behavioral_model" not in response.json()


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
