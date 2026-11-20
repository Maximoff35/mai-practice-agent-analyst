import json
from pathlib import Path

import pytest


@pytest.fixture
def buggy_model():
    path = Path(__file__).parent / "fixtures" / "buggy_model.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def fixed_model():
    path = Path(__file__).parent / "fixtures" / "fixed_model.json"
    return json.loads(path.read_text(encoding="utf-8"))


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
