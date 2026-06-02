from __future__ import annotations

import sqlite3
from typing import Optional

from laffyhand.agent.session.models import SessionMessage
from laffyhand.agent.db.repository.common import decode_session_message


class MessageRepo:
    """Pure DB CRUD for the session_message table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, sm: SessionMessage) -> None:
        self._conn.execute(
            "INSERT INTO session_message (id, session_id, type, time_created, time_updated, data) VALUES (?,?,?,?,?,?)",
            (sm.id, sm.session_id, sm.type, sm.time_created, sm.time_updated, sm.data.model_dump_json()),
        )

    def get_by_session(self, session_id: str, offset: int = 0, limit: Optional[int] = None) -> list[SessionMessage]:
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
        return [decode_session_message(r) for r in rows]

    def count_by_session(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM session_message WHERE session_id=?", (session_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def delete_by_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM session_message WHERE session_id=?", (session_id,))
