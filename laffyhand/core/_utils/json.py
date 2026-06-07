from __future__ import annotations

import json
from typing import Any


def _unwrap_json_string(value: str) -> Any | None:
    try:
        parsed = json.loads(value)
        if isinstance(parsed, str):
            return json.loads(parsed)
        return parsed
    except json.JSONDecodeError, TypeError:
        return None


def coerce_json_dict(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: str(v) for k, v in value.items()}
    if isinstance(value, str):
        parsed = _unwrap_json_string(value)
        if isinstance(parsed, dict):
            return {k: str(v) for k, v in parsed.items()}
    return {}


def coerce_json_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parsed = _unwrap_json_string(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []
