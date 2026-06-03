from __future__ import annotations

import sqlite3
from typing import Optional

from laffyhand.agent.session.models import TodoItem, _utcnow
from laffyhand.agent.db.repository.common import (
    _from_ts,
    _serialize_json,
    _deserialize_str_list,
    _deserialize_metadata,
    _ts,
)


class TodoRepo:
    """Pure DB CRUD for the todo table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def get(self, task_id: str) -> Optional[TodoItem]:
        row = self._conn.execute(
            "SELECT * FROM todo WHERE id = ?",
            (task_id,),
        ).fetchone()
        return self._row_to_todo(row) if row else None

    def get_by_session(
        self, session_id: str, status: Optional[str] = None
    ) -> list[TodoItem]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM todo WHERE session_id = ? AND status = ? ORDER BY created_at",
                (session_id, status),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM todo WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return [self._row_to_todo(r) for r in rows]

    def insert(self, item: TodoItem) -> None:
        self._conn.execute(
            """INSERT INTO todo
               (id, session_id, content, status, priority, depends_on,
                created_at, updated_at, completed_at, task_tool_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id,
                item.session_id,
                item.content,
                item.status,
                item.priority,
                _serialize_json(item.depends_on),
                _ts(item.created_at),
                _ts(item.updated_at),
                _ts(item.completed_at) if item.completed_at else None,
                item.task_tool_id,
                _serialize_json(item.metadata),
            ),
        )

    def update(self, item: TodoItem) -> None:
        self._conn.execute(
            """UPDATE todo SET
                content=?, status=?, priority=?, depends_on=?,
                updated_at=?, completed_at=?, task_tool_id=?, metadata=?
               WHERE id=?""",
            (
                item.content,
                item.status,
                item.priority,
                _serialize_json(item.depends_on),
                _ts(item.updated_at),
                _ts(item.completed_at) if item.completed_at else None,
                item.task_tool_id,
                _serialize_json(item.metadata),
                item.id,
            ),
        )

    def delete(self, task_id: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM todo WHERE id=?", (task_id,)).fetchone()
        if row is None:
            return False
        self._conn.execute("DELETE FROM todo WHERE id=?", (task_id,))
        return True

    def delete_by_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM todo WHERE session_id=?", (session_id,))

    def get_dependents(self, task_id: str) -> list[tuple[str, list[str]]]:
        """Return (dependent_id, depends_on_list) for tasks that mention task_id."""
        rows = self._conn.execute(
            "SELECT id, depends_on FROM todo WHERE depends_on LIKE ?",
            (f"%{task_id}%",),
        ).fetchall()
        return [(r["id"], _deserialize_str_list(r["depends_on"])) for r in rows]

    def get_by_task_tool_id(self, tool_call_id: str) -> Optional[TodoItem]:
        row = self._conn.execute(
            "SELECT * FROM todo WHERE task_tool_id = ?",
            (tool_call_id,),
        ).fetchone()
        return self._row_to_todo(row) if row else None

    def count_by_session(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM todo WHERE session_id=?", (session_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _row_to_todo(row: sqlite3.Row) -> TodoItem:
        return TodoItem(
            id=row["id"],
            session_id=row["session_id"],
            content=row["content"],
            status=row["status"],
            priority=row["priority"],
            depends_on=_deserialize_str_list(row["depends_on"]),
            created_at=_from_ts(row["created_at"]) or _utcnow(),
            updated_at=_from_ts(row["updated_at"]) or _utcnow(),
            completed_at=_from_ts(row["completed_at"]) if row["completed_at"] else None,
            task_tool_id=row["task_tool_id"],
            metadata=_deserialize_metadata(row["metadata"]),
        )
