from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast


def _ts(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _from_ts(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts is not None else None


def _serialize_json(val: list[Any] | dict[str, Any]) -> str:
    return json.dumps(val, default=str)


def _serialize_metadata(meta: dict[str, Any]) -> str:
    return _serialize_json(meta)


def _deserialize_str_list(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        return cast(list[str], json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return []


def _deserialize_metadata(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return cast(dict[str, Any], json.loads(raw))
    except json.JSONDecodeError:
        return {}
