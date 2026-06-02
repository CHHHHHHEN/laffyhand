from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Optional, cast
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


def _row_to_session(row: sqlite3.Row) -> Session:
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


def _decode_session_message(row: sqlite3.Row) -> SessionMessage:
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


class SessionRepo:
    """Pure DB CRUD for the session table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, session: Session) -> None:
        self._conn.execute(
            """INSERT INTO session (
                id, status, title, cwd, provider, model, agent_version,
                turn_count, step_count,
                input_tokens, output_tokens, reasoning_tokens,
                cache_read_tokens, cache_write_tokens,
                parent_id, fork_id,
                message_count, summary, metadata,
                created_at, updated_at, ended_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session.id, session.status, session.title, session.cwd,
                session.provider, session.model, session.agent_version,
                session.turn_count, session.step_count,
                session.input_tokens, session.output_tokens, session.reasoning_tokens,
                session.cache_read_tokens, session.cache_write_tokens,
                session.parent_id, session.fork_id,
                session.message_count, session.summary,
                _serialize_metadata(session.metadata),
                _ts(session.created_at), _ts(session.updated_at), _ts(session.ended_at),
            ),
        )
        self._conn.commit()

    def get(self, session_id: str) -> Optional[Session]:
        row = self._conn.execute("SELECT * FROM session WHERE id=?", (session_id,)).fetchone()
        return _row_to_session(row) if row else None

    def get_active(self) -> Optional[Session]:
        row = self._conn.execute(
            "SELECT * FROM session WHERE status='active' ORDER BY updated_at DESC LIMIT 1",
        ).fetchone()
        return _row_to_session(row) if row else None

    def list_sessions(self, status: Optional[str] = None, limit: int = 20, offset: int = 0) -> list[Session]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM session WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM session ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_session(r) for r in rows]

    def update(self, session: Session) -> None:
        session.updated_at = _utcnow()
        self._conn.execute(
            """UPDATE session SET status=?, title=?, cwd=?, model=?, agent_version=?,
                turn_count=?, step_count=?,
                input_tokens=?, output_tokens=?, reasoning_tokens=?,
                cache_read_tokens=?, cache_write_tokens=?,
                message_count=?, summary=?, metadata=?,
                updated_at=?, ended_at=?
            WHERE id=?""",
            (
                session.status, session.title, session.cwd, session.model, session.agent_version,
                session.turn_count, session.step_count,
                session.input_tokens, session.output_tokens, session.reasoning_tokens,
                session.cache_read_tokens, session.cache_write_tokens,
                session.message_count, session.summary,
                _serialize_metadata(session.metadata),
                _ts(session.updated_at), _ts(session.ended_at),
                session.id,
            ),
        )
        self._conn.commit()

    def complete(self, session_id: str, summary: Optional[str] = None) -> None:
        now = _utcnow()
        self._conn.execute(
            "UPDATE session SET status='completed', summary=?, ended_at=?, updated_at=? WHERE id=?",
            (summary, _ts(now), _ts(now), session_id),
        )
        self._conn.commit()

    def archive(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE session SET status='archived', updated_at=? WHERE id=?",
            (_ts(_utcnow()), session_id),
        )
        self._conn.commit()

    def delete(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM session WHERE id=?", (session_id,))
        self._conn.commit()

    def set_title(self, session_id: str, title: str) -> None:
        self._conn.execute("UPDATE session SET title=? WHERE id=?", (title, session_id))
        self._conn.commit()

    def search(self, query: str, limit: int = 20) -> list[Session]:
        like = f"%{query}%"
        rows = self._conn.execute(
            """SELECT DISTINCT s.* FROM session s
               JOIN session_message m ON m.session_id = s.id
               WHERE m.data LIKE ? ORDER BY s.updated_at DESC LIMIT ?""",
            (like, limit),
        ).fetchall()
        return [_row_to_session(r) for r in rows]

    def get_parent(self, session_id: str) -> Optional[str]:
        row = self._conn.execute("SELECT parent_id FROM session WHERE id=?", (session_id,)).fetchone()
        return row["parent_id"] if row else None

    def get_children(self, session_id: str) -> list[Session]:
        rows = self._conn.execute(
            "SELECT * FROM session WHERE parent_id=? ORDER BY created_at", (session_id,),
        ).fetchall()
        return [_row_to_session(r) for r in rows]

    def get_compression_tip(self, session_id: str) -> str:
        current = session_id
        max_depth = 1000
        for _ in range(max_depth):
            row = self._conn.execute(
                "SELECT id FROM session WHERE parent_id=? AND status='active' LIMIT 1",
                (current,),
            ).fetchone()
            if row is None:
                return current
            current = cast(str, row["id"])
        logger.warning(f"Compression chain too deep (>{max_depth}) for {session_id}, stopping")
        return current

    def chain(self, session_id: str) -> list[str]:
        ids: list[str] = []
        current: Optional[str] = session_id
        while current:
            ids.append(current)
            row = self._conn.execute("SELECT parent_id FROM session WHERE id=?", (current,)).fetchone()
            current = row["parent_id"] if row else None
        return ids


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
        return [_decode_session_message(r) for r in rows]

    def delete_by_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM session_message WHERE session_id=?", (session_id,))
