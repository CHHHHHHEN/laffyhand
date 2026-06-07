from __future__ import annotations

import sqlite3
from typing import Optional, cast

from loguru import logger

from laffyhand.core.llm.specs.models import ModelID, ProviderID
from laffyhand.core.session.models import Session, utcnow
from laffyhand.core.db.repository.common import (
    _from_ts,
    _serialize_metadata,
    _deserialize_metadata,
    _ts,
)


class SessionRepo:
    """Pure DB CRUD for the session table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            status=row["status"],
            title=row["title"],
            cwd=row["cwd"],
            provider=ProviderID(row["provider"])
            if "provider" in row.keys()
            else ProviderID(""),
            model=ModelID(row["model"]),
            agent_version=row["agent_version"],
            turn_count=row["turn_count"],
            step_count=row["step_count"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            reasoning_tokens=row["reasoning_tokens"],
            cache_read_tokens=row["cache_read_tokens"],
            cache_write_tokens=row["cache_write_tokens"]
            if "cache_write_tokens" in row.keys()
            else 0,
            parent_id=row["parent_id"],
            fork_id=row["fork_id"],
            message_count=row["message_count"],
            summary=row["summary"],
            metadata=_deserialize_metadata(row["metadata"] or "{}"),
            created_at=_from_ts(row["created_at"]) or utcnow(),
            updated_at=_from_ts(row["updated_at"]) or utcnow(),
            ended_at=_from_ts(row["ended_at"]) if row["ended_at"] else None,
        )

    def insert(self, session: Session) -> None:
        self._conn.execute(
            """INSERT INTO session (
                id, status, title, cwd, provider, model, agent_version,
                turn_count, step_count,
                input_tokens, output_tokens, reasoning_tokens,
                cache_read_tokens, cache_write_tokens, cost,
                parent_id, fork_id,
                message_count, summary, metadata,
                created_at, updated_at, ended_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session.id,
                session.status,
                session.title,
                session.cwd,
                session.provider,
                session.model,
                session.agent_version,
                session.turn_count,
                session.step_count,
                session.input_tokens,
                session.output_tokens,
                session.reasoning_tokens,
                session.cache_read_tokens,
                session.cache_write_tokens,
                session.cost,
                session.parent_id,
                session.fork_id,
                session.message_count,
                session.summary,
                _serialize_metadata(session.metadata),
                _ts(session.created_at),
                _ts(session.updated_at),
                _ts(session.ended_at),
            ),
        )

    def get(self, session_id: str) -> Optional[Session]:
        row = self._conn.execute(
            "SELECT * FROM session WHERE id=?", (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def get_active(self) -> Optional[Session]:
        row = self._conn.execute(
            "SELECT * FROM session WHERE status='active' ORDER BY updated_at DESC LIMIT 1",
        ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(
        self, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> list[Session]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM session WHERE status=? AND parent_id IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM session WHERE parent_id IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def update(self, session: Session) -> None:
        session.updated_at = utcnow()
        self._conn.execute(
            """UPDATE session SET status=?, title=?, cwd=?, model=?, agent_version=?,
                turn_count=?, step_count=?,
                input_tokens=?, output_tokens=?, reasoning_tokens=?,
                cache_read_tokens=?, cache_write_tokens=?, cost=?,
                message_count=?, summary=?, metadata=?,
                updated_at=?, ended_at=?
            WHERE id=?""",
            (
                session.status,
                session.title,
                session.cwd,
                session.model,
                session.agent_version,
                session.turn_count,
                session.step_count,
                session.input_tokens,
                session.output_tokens,
                session.reasoning_tokens,
                session.cache_read_tokens,
                session.cache_write_tokens,
                session.cost,
                session.message_count,
                session.summary,
                _serialize_metadata(session.metadata),
                _ts(session.updated_at),
                _ts(session.ended_at),
                session.id,
            ),
        )

    def complete(self, session_id: str, summary: Optional[str] = None) -> None:
        now = utcnow()
        self._conn.execute(
            "UPDATE session SET status='completed', summary=?, ended_at=?, updated_at=? WHERE id=?",
            (summary, _ts(now), _ts(now), session_id),
        )

    def archive(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE session SET status='archived', updated_at=? WHERE id=?",
            (_ts(utcnow()), session_id),
        )

    def delete(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE session SET parent_id=NULL WHERE parent_id=?", (session_id,)
        )
        self._conn.execute(
            "UPDATE session SET fork_id=NULL WHERE fork_id=?", (session_id,)
        )
        self._conn.execute("DELETE FROM session WHERE id=?", (session_id,))

    def set_title(self, session_id: str, title: str) -> None:
        self._conn.execute("UPDATE session SET title=? WHERE id=?", (title, session_id))

    def update_counters(
        self,
        session_id: str,
        *,
        turn_count: int = 0,
        step_count: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        cost: int = 0,
        message_count: int = 0,
    ) -> None:
        self._conn.execute(
            """UPDATE session SET turn_count=?, step_count=?,
                input_tokens=?, output_tokens=?, reasoning_tokens=?,
                cache_read_tokens=?, cache_write_tokens=?, cost=?,
                message_count=?, updated_at=?
            WHERE id=?""",
            (
                turn_count,
                step_count,
                input_tokens,
                output_tokens,
                reasoning_tokens,
                cache_read_tokens,
                cache_write_tokens,
                cost,
                message_count,
                _ts(utcnow()),
                session_id,
            ),
        )

    def get_depth(self, session_id: str, max_depth: int = 1000) -> int:
        row = self._conn.execute(
            """WITH RECURSIVE ancestors(id, parent_id, depth) AS (
                SELECT id, parent_id, 0 FROM session WHERE id = ?
                UNION ALL
                SELECT s.id, s.parent_id, a.depth + 1
                FROM session s
                JOIN ancestors a ON s.id = a.parent_id
                WHERE a.depth < ?
            )
            SELECT COALESCE(MAX(depth), 0) FROM ancestors""",
            (session_id, max_depth),
        ).fetchone()
        depth: int = row[0] if row else 0
        if depth >= max_depth:
            logger.warning(f"Session chain too deep (>{max_depth}) for {session_id}")
        return depth

    def search(self, query: str, limit: int = 20) -> list[Session]:
        like = f"%{query}%"
        rows = self._conn.execute(
            """SELECT DISTINCT s.* FROM session s
               JOIN session_message m ON m.session_id = s.id
               WHERE m.data LIKE ? AND s.parent_id IS NULL ORDER BY s.updated_at DESC LIMIT ?""",
            (like, limit),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def get_parent(self, session_id: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT parent_id FROM session WHERE id=?", (session_id,)
        ).fetchone()
        return row["parent_id"] if row else None

    def get_children(self, session_id: str) -> list[Session]:
        rows = self._conn.execute(
            "SELECT * FROM session WHERE parent_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def get_compression_tip(self, session_id: str) -> str:
        max_depth = 1000
        row = self._conn.execute(
            """WITH RECURSIVE tip(id, depth) AS (
                SELECT id, 0 FROM session WHERE id = ?
                UNION ALL
                SELECT s.id, t.depth + 1
                FROM session s
                JOIN tip t ON s.parent_id = t.id
                WHERE s.status = 'active' AND t.depth < ?
            )
            SELECT id, depth FROM tip ORDER BY depth DESC LIMIT 1""",
            (session_id, max_depth),
        ).fetchone()
        if row is None:
            return session_id
        result = cast(str, row["id"])
        depth = cast(int, row["depth"])
        if depth >= max_depth:
            # Hit the recursion limit — check if there are deeper active children
            further = self._conn.execute(
                "SELECT 1 FROM session WHERE parent_id=? AND status='active' LIMIT 1",
                (result,),
            ).fetchone()
            if further is not None:
                logger.warning(
                    f"Compression chain too deep (>{max_depth}) for {session_id}, stopping"
                )
        return result

    def chain(self, session_id: str) -> list[str]:
        rows = self._conn.execute(
            """WITH RECURSIVE chain_cte(id, parent_id) AS (
                SELECT id, parent_id FROM session WHERE id = ?
                UNION ALL
                SELECT s.id, s.parent_id
                FROM session s
                JOIN chain_cte c ON s.id = c.parent_id
            )
            SELECT id FROM chain_cte""",
            (session_id,),
        ).fetchall()
        return [cast(str, r["id"]) for r in rows]
