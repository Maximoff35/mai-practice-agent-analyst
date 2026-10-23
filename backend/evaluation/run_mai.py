"""Manual live evaluation; never runs as part of pytest. Run from backend/."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyst import MAIError, MAIProvider
from analyst.config import get_setting
from model_checker import verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Ручные контрольные прогоны API МАИ и настоящего TLC")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True, help="Локальный JSON-отчёт без ключей и технических логов")
    parser.add_argument("--scenario", help="Идентификатор одного сценария; по умолчанию все")
    args = parser.parse_args()
    provider = MAIProvider(
        get_setting("MAI_API_KEY") or "", args.model,
        base_url=get_setting("MAI_BASE_URL") or "https://api-ai.mai.ru",
        timeout_seconds=float(get_setting("MAI_TIMEOUT_SECONDS", "90") or "90"),
    )
    scenarios = json.loads(Path(__file__).with_name("scenarios.json").read_text(encoding="utf-8"))
    if args.scenario:
        scenarios = [scenario for scenario in scenarios if scenario["id"] == args.scenario]
        if not scenarios:
            parser.error("Неизвестный сценарий")
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "requested_model": args.model, "runs": []}
    for scenario in scenarios:
        run = {"id": scenario["id"], "expected_status": scenario["expected_status"]}
        started = time.monotonic()
        try:
            model = provider.build_model(scenario["requirements"])
            result = verify(model)
            run.update(
                behavioral_model=model.model_dump(mode="json"),
                verification_result=result.model_dump(mode="json", exclude={"stdout", "stderr"}),
            )
            try:
                run["explanation"] = provider.explain_result(scenario["requirements"], model, result)
            except MAIError as error:
                run["explanation_error"] = str(error)
        except MAIError as error:
            run["model_error"] = str(error)
        run["elapsed_seconds"] = round(time.monotonic() - started, 2)
        run["response_models"] = provider.response_models.copy()
        provider.response_models.clear()
        report["runs"].append(run)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        status = run.get("verification_result", {}).get("status", run.get("model_error"))
        print(f"{scenario['id']}: {status} ({run['elapsed_seconds']} s)", flush=True)


if __name__ == "__main__":
    main()
