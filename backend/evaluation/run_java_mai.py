"""Ручная приёмка двух реальных LLM и изолированного javac/java, вне pytest."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyst import AnalystAgent, MAIProvider, JavaGenerator
from analyst.config import get_setting
from analyst.java_reviewer import JavaReviewer
from java_runner import JavaArtifact, JavaCheckStatus, run_java_module
from java_runner.identity import fingerprint_model
from model_checker import validate_model
from orchestration import CaseAcceptance, CasePipeline


class RecordedModelProvider:
    """Фиксированная модель приёмки: не выдаётся за новый вызов аналитика."""
    def __init__(self, model):
        self.model = validate_model(model)
    def build_model(self, requirements):
        return self.model.model_copy(deep=True)
    def explain_result(self, requirements, model, result):
        return "Контрольная модель приёмки; интерпретация текста здесь зафиксирована заранее."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", default="qwen3.6-35b-a3b")
    parser.add_argument("--reviewer", default="deepseek-v4.1-flash")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = get_setting("MAI_API_KEY") or ""
    def provider(name):
        return MAIProvider(key, name, base_url=get_setting("MAI_BASE_URL") or "https://api-ai.mai.ru")
    generator = JavaGenerator(provider(args.generator))
    reviewer = JavaReviewer(provider(args.reviewer))
    scenarios = json.loads(Path(__file__).with_name("java-scenarios.json").read_text(encoding="utf-8"))
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "generator_requested": args.generator,
              "reviewer_requested": args.reviewer, "runs": [], "negative_fixtures": []}
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for scenario in scenarios:
        started = time.monotonic()
        pipeline = CasePipeline(AnalystAgent(RecordedModelProvider(scenario["model"])), generator=generator, reviewer=reviewer)
        analysis = pipeline.analyze(scenario["requirements"])
        row = {"id": scenario["id"], "expected": scenario["expected"],
               "analysis": analysis.model_dump(mode="json", exclude={"analysis": {"verification_result": {"stdout", "stderr"}}})}
        try:
            pipeline.accept(CaseAcceptance(case_id=analysis.case_id, model_fingerprint=analysis.model_fingerprint))
            result = pipeline.generate(analysis.case_id)
            row["report"] = result.model_dump(mode="json")
        except ValueError:
            row["blocked"] = True
        row["elapsed_seconds"] = round(time.monotonic()-started, 2)
        report["runs"].append(row)
        save()
        print(scenario["id"], row.get("report", {}).get("status", "BLOCKED"), row["elapsed_seconds"], flush=True)

    # Намеренно ошибочный код известен до запроса reviewer, без автоматического ремонта.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_java_runner import JAVA_MACHINE_FIXED
    model = validate_model(scenarios[1]["model"])
    defects = {
        "syntax": "public class Machine { syntax error }",
        "removed_guard": JAVA_MACHINE_FIXED.replace('event.equals("Execute") && approved', 'event.equals("Execute")'),
        "wrong_effect": JAVA_MACHINE_FIXED.replace('approved = false;\n          System.out.println("APPLIED");', 'approved = true;\n          System.out.println("APPLIED");'),
    }
    for name, code in defects.items():
        started = time.monotonic()
        artifact = JavaArtifact(files=[{"path": "Machine.java", "content": code}], main_class="Machine",
                                model_fingerprint=fingerprint_model(model), generator_model="deterministic-negative-fixture")
        row = {"id": name, "artifact": artifact.model_dump(mode="json")}
        try:
            row["review"] = reviewer.review(scenarios[1]["requirements"], model, artifact,
                                            artifact.model_fingerprint).model_dump(mode="json")
        except Exception as error:
            row["review_error"] = type(error).__name__
        row["check"] = run_java_module(artifact, model).model_dump(mode="json")
        row["elapsed_seconds"] = round(time.monotonic()-started, 2)
        report["negative_fixtures"].append(row)
        save()
        print(name, row["check"]["status"], "review:", row.get("review", {}).get("approved", row.get("review_error")), flush=True)


if __name__ == "__main__":
    main()
