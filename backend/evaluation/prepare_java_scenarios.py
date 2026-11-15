"""Явные конечные модели приёмки; запускается до запросов LLM."""

import json
from pathlib import Path


def scenarios():
    fixtures = Path(__file__).resolve().parents[1] / "tests/fixtures"
    result = [{"id": name, "requirements": text, "expected": expected,
               "model": json.loads((fixtures / filename).read_text(encoding="utf-8"))}
              for name, text, expected, filename in [
                  ("application_buggy", "Заявка: Cancel сохраняет approved; Execute проверяет approved. Исполнение отменённой заявки запрещено.", "BLOCKED", "buggy_model.json"),
                  ("application_fixed", "Заявка: Cancel сбрасывает approved=false; Execute требует approved. Исполнение отменённой заявки запрещено.", "READY", "fixed_model.json")]]
    result.append({"id": "cycle_terminal", "requirements": "Изначально Ready. Stay сохраняет Ready, Finish переводит Ready в Done. Done — явно допустимое завершение. Проверь достижимость Done и отсутствие остальных блокировок.",
                   "expected": "READY", "model": {
        "variables": [{"name": "status", "type": "enum", "values": ["Ready", "Done"]}],
        "initial": {"status": "Ready"},
        "transitions": [{"name": name, "guard": {"eq": [{"var": "status"}, "Ready"]},
                         "effects": [{"set": ["status", target]}]} for name, target in [("Stay", "Ready"), ("Finish", "Done")]],
        "properties": [{"name": "ReachDone", "type": "reachable", "expression": {"eq": [{"var": "status"}, "Done"]}},
                       {"name": "NoDeadlock", "type": "deadlock_free", "terminal_states": {"eq": [{"var": "status"}, "Done"]}}],
    }})
    result.append({"id": "integer_swap", "requirements": "Integer x,y в 0..1, initial x=0,y=1; flag=false сохраняется. Swap при x=0 и not flag одновременно x:=y,y:=x. Reset при x=1 возвращает x=0,y=1. Проверь достижимость x=1.",
                   "expected": "READY", "model": {
        "variables": [{"name": name, "type": "integer", "min": 0, "max": 1} for name in ["x", "y"]] + [{"name": "flag", "type": "boolean"}],
        "initial": {"x": 0, "y": 1, "flag": False},
        "transitions": [{"name": "Swap", "guard": {"and": [{"eq": [{"var": "x"}, 0]}, {"not": {"var": "flag"}}]},
                         "effects": [{"set": ["x", {"var": "y"}]}, {"set": ["y", {"var": "x"}]}]},
                        {"name": "Reset", "guard": {"eq": [{"var": "x"}, 1]}, "effects": [{"set": ["x", 0]}, {"set": ["y", 1]}]}],
        "properties": [{"name": "ReachOne", "type": "reachable", "expression": {"eq": [{"var": "x"}, 1]}}],
    }})
    return result


if __name__ == "__main__":
    Path(__file__).with_name("java-scenarios.json").write_text(json.dumps(scenarios(), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
