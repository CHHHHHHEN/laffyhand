from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, cast
from pydantic import BaseModel

from loguru import logger

from laffyhand.agent.llm.specs.models import ModelID, ProviderID
from laffyhand.agent.session.models import (
    AgentSwitchedData,
    AssistantData,
    CompactionData,
    ModelSwitchedData,
    Session,
    SessionMessage,
    ShellData,
    SyntheticData,
    UserData,
    _utcnow,
)


def _ts(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _from_ts(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts is not None else None


def _serialize_metadata(meta: dict[str, Any]) -> str:
    return json.dumps(meta, default=str)


def _deserialize_metadata(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return cast(dict[str, Any], json.loads(raw))
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse session metadata JSON: {raw[:200]}")
        return {}


def row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        status=row["status"],
        title=row["title"],
        cwd=row["cwd"],
        provider=ProviderID(row["provider"]) if "provider" in row.keys() else ProviderID(""),
        model=ModelID(row["model"]),
        agent_version=row["agent_version"],
        turn_count=row["turn_count"],
        step_count=row["step_count"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        reasoning_tokens=row["reasoning_tokens"],
        cache_read_tokens=row["cache_read_tokens"],
        cache_write_tokens=row["cache_write_tokens"] if "cache_write_tokens" in row.keys() else 0,
        parent_id=row["parent_id"],
        fork_id=row["fork_id"],
        message_count=row["message_count"],
        summary=row["summary"],
        metadata=_deserialize_metadata(row["metadata"] or "{}"),
        created_at=_from_ts(row["created_at"]) or _utcnow(),
        updated_at=_from_ts(row["updated_at"]) or _utcnow(),
        ended_at=_from_ts(row["ended_at"]) if row["ended_at"] else None,
    )


def decode_session_message(row: sqlite3.Row) -> SessionMessage:
    raw = json.loads(row["data"])
    type_map: dict[str, type] = {
        "user": UserData, "assistant": AssistantData,
        "synthetic": SyntheticData, "shell": ShellData,
        "agent-switched": AgentSwitchedData,
        "model-switched": ModelSwitchedData,
        "compaction": CompactionData,
    }
    model_cls = type_map.get(row["type"])
    if model_cls is None:
        raise ValueError(f"Unknown message type: {row['type']}")
    data_cls = cast(type[BaseModel], model_cls)
    data = cast("UserData | AssistantData | SyntheticData | ShellData | AgentSwitchedData | ModelSwitchedData | CompactionData", data_cls.model_validate(raw))
    return SessionMessage(
        id=row["id"], session_id=row["session_id"], type=row["type"],
        time_created=row["time_created"], time_updated=row["time_updated"],
        data=data,
    )
