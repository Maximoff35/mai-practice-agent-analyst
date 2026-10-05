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
