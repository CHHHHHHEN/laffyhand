from __future__ import annotations

import json
import sqlite3
from typing import Optional, cast

from pydantic import BaseModel

from laffyhand.core.db.models import (
    AgentSwitchedData,
    AssistantData,
    CompactionData,
    ModelSwitchedData,
    SessionMessage,
    ShellData,
    SyntheticData,
    UserData,
)


class MessageRepo:
    """Pure DB CRUD for the session_message table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> SessionMessage:
        raw = json.loads(row["data"])
        type_map: dict[str, type] = {
            "user": UserData,
            "assistant": AssistantData,
            "synthetic": SyntheticData,
            "shell": ShellData,
            "agent-switched": AgentSwitchedData,
            "model-switched": ModelSwitchedData,
            "compaction": CompactionData,
        }
        model_cls = type_map.get(row["type"])
        if model_cls is None:
            raise ValueError(f"Unknown message type: {row['type']}")
        data_cls = cast(type[BaseModel], model_cls)
        data = cast(
            "UserData | AssistantData | SyntheticData | ShellData | AgentSwitchedData | ModelSwitchedData | CompactionData",
            data_cls.model_validate(raw),
        )
        return SessionMessage(
            id=row["id"],
            session_id=row["session_id"],
            type=row["type"],
            time_created=row["time_created"],
            time_updated=row["time_updated"],
            data=data,
        )

    def insert(self, sm: SessionMessage) -> None:
        self._conn.execute(
            "INSERT INTO session_message (id, session_id, type, time_created, time_updated, data) VALUES (?,?,?,?,?,?)",
            (
                sm.id,
                sm.session_id,
                sm.type,
                sm.time_created,
                sm.time_updated,
                sm.data.model_dump_json(),
            ),
        )

    def get_by_session(
        self, session_id: str, offset: int = 0, limit: Optional[int] = None
    ) -> list[SessionMessage]:
        if limit is not None:
            rows = self._conn.execute(
                "SELECT * FROM session_message WHERE session_id=? ORDER BY time_created LIMIT ? OFFSET ?",
                (session_id, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM session_message WHERE session_id=? ORDER BY time_created",
                (session_id,),
            ).fetchall()
        return [self._decode_row(r) for r in rows]

    def count_by_session(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM session_message WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0
