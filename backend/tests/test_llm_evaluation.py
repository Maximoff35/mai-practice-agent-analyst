"""Replay recorded MAI responses without network; check their models with real TLC."""

import json
import shutil
from pathlib import Path

import httpx
import pytest

from analyst import AnalystAgent, MAIProvider
from model_checker import TLCConfig, VerificationResult, validate_model, verify


EVALUATION = Path(__file__).parents[1] / "evaluation"
SCENARIOS = {row["id"]: row for row in json.loads((EVALUATION / "scenarios.json").read_text(encoding="utf-8"))}
RUNS = json.loads((EVALUATION / "recorded-qwen36.json").read_text(encoding="utf-8"))["runs"]


@pytest.mark.parametrize("run", RUNS, ids=lambda run: run["id"])
def test_replay_recorded_mai_responses(run):
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        content = json.dumps(run["behavioral_model"]) if "response_format" in payload else run["explanation"]
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})

    def checker(model):
        calls.append(model)
        return VerificationResult.model_validate(run["verification_result"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = AnalystAgent(MAIProvider("offline-key", "qwen3.6-35b-a3b", client=client), checker).analyze(
            SCENARIOS[run["id"]]["requirements"]
        )
    assert len(calls) == 1
    assert result.behavioral_model.model_dump(mode="json") == run["behavioral_model"]
    assert result.explanation == run["explanation"]
    if run["id"].startswith("mutex"):
        assert {variable.name for variable in result.behavioral_model.variables} == {"inA", "inB"}


@pytest.mark.integration
@pytest.mark.parametrize("run", [run for run in RUNS if run["expected_status"]], ids=lambda run: run["id"])
def test_recorded_explicit_models_with_real_tlc(run):
    config = TLCConfig.from_env()
    if not shutil.which(config.java_executable) or not config.tla2tools_jar or not config.tla2tools_jar.is_file():
        pytest.skip("Настройте Java и TLC для проверки сохранённых моделей")
    result = verify(validate_model(run["behavioral_model"]), config)
    assert result.status.value == SCENARIOS[run["id"]]["expected_status"], result.stdout + result.stderr
    assert [state.transition for state in result.counterexample] == [
        state["transition"] for state in run["verification_result"]["counterexample"]
    ]
