"""Small local settings reader; environment variables override backend/.env."""

from __future__ import annotations

import os
from pathlib import Path


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def get_setting(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is not None:
        return value
    if not ENV_FILE.is_file():
        return default
    for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        if key.strip() != name:
            continue
        raw_value = raw_value.strip()
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {'"', "'"}:
            raw_value = raw_value[1:-1]
        return raw_value
    return default
