"""Честно маркированный резерв: записи LLM + настоящий TLC и Docker/JDK."""

import json
from pathlib import Path

from analyst import AnalystAgent
from api.main import app, get_pipeline
from evaluation.run_java_mai import RecordedModelProvider
from java_runner import JavaArtifact
from orchestration import CasePipeline
from orchestration.schemas import JavaReview


directory = Path(__file__).resolve().parent
scenarios = json.loads((directory / "java-scenarios.json").read_text(encoding="utf-8"))
record = json.loads((directory / "recorded-java-mai.json").read_text(encoding="utf-8"))


class ReplayAnalyst:
    def build_model(self, requirements):
        fixed = "approved=false" in "".join(requirements.casefold().split())
        if "заявк" not in requirements.casefold():
            from analyst import UnsupportedRequirementsError
            raise UnsupportedRequirementsError("Режим записи поддерживает только контрольную заявку")
        return RecordedModelProvider(scenarios[1 if fixed else 0]["model"]).build_model(requirements)
    def explain_result(self, requirements, model, result):
        return "РЕЖИМ ЗАПИСИ: модель сценария зафиксирована заранее. TLC запущен заново; новые запросы к LLM не выполняются."


class ReplayGenerator:
    def generate(self, requirements, model, model_fingerprint):
        artifact = JavaArtifact.model_validate(record["runs"][1]["report"]["artifact"])
        if artifact.model_fingerprint != model_fingerprint:
            raise ValueError("Запись относится к другой модели")
        return artifact


class ReplayReviewer:
    def review(self, requirements, model, artifact, model_fingerprint):
        return JavaReview.model_validate_json(json.dumps(record["runs"][1]["report"]["review"]))


pipeline = CasePipeline(AnalystAgent(ReplayAnalyst()), generator=ReplayGenerator(), reviewer=ReplayReviewer(), source_mode="recorded")
app.dependency_overrides[get_pipeline] = lambda: pipeline
