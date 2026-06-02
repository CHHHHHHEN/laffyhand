from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Optional, cast

from loguru import logger

from laffyhand.agent.llm.specs.models import AssistantMessage, Message, SystemMessage, ToolMessage, UserMessage
from laffyhand.agent.session.models import (
    MessageRecord,
    Session,
    _utcnow,
    _ts,
    _from_ts,
)
from laffyhand.agent.session.schema import create_tables, has_fts5
from laffyhand.agent.llm.specs.models import ToolCallContent
from laffyhand.agent.schemas import (
    AgentState,
    SessionUsage,
)


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


def _message_to_record(
    session_id: str,
    msg: Message,
    turn_index: int,
) -> MessageRecord:
    if isinstance(msg, SystemMessage):
        return MessageRecord(
            session_id=session_id,
            role="system",
            content=msg.content,
            turn_index=turn_index,
        )
    if isinstance(msg, UserMessage):
        return MessageRecord(
            session_id=session_id,
            role="user",
            content=msg.content,
            turn_index=turn_index,
        )
    if isinstance(msg, AssistantMessage):
        tool_args = None
        if msg.tool_calls:
            tool_args = json.dumps(
                [t.model_dump() for t in msg.tool_calls],
                default=str,
            )
        return MessageRecord(
            session_id=session_id,
            role="assistant",
            content=msg.content,
            reasoning=msg.reasoning,
            tool_args=tool_args,
            token_count=(
                (msg.tokens.input_tokens or 0) + (msg.tokens.output_tokens or 0)
            )
            if msg.tokens
            else None,
            turn_index=turn_index,
        )
    if isinstance(msg, ToolMessage):
        return MessageRecord(
            session_id=session_id,
            role="tool",
            content=msg.content,
            tool_call_id=msg.tool_call_id,
            turn_index=turn_index,
        )
    raise TypeError(f"Unknown message type: {type(msg).__name__}")


def _record_to_message(rec: MessageRecord) -> Message:
    if rec.role == "system":
        return SystemMessage(content=rec.content or "")
    if rec.role == "user":
        return UserMessage(content=rec.content or "")
    if rec.role == "assistant":
        tool_calls = None
        if rec.tool_args:
            try:
                raw = json.loads(rec.tool_args)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse tool_args JSON for message {rec.id}")
                raw = []
            tool_calls = [ToolCallContent(**t) for t in raw]
        return AssistantMessage(
            content=rec.content,
            reasoning=rec.reasoning,
            tool_calls=tool_calls,
        )
    if rec.role == "tool":
        return ToolMessage(
            tool_call_id=rec.tool_call_id or "",
            content=rec.content or "",
        )
    raise ValueError(f"Unknown role: {rec.role}")


class SessionManager:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        create_tables(self._conn)
        self._fts5_available = has_fts5(self._conn)
        if not self._fts5_available:
            logger.warning("FTS5 unavailable; session search falls back to LIKE")

    # ── Connection ────────────────────────────────────────────

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SessionManager:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ── Session CRUD ──────────────────────────────────────────

    def create(
        self,
        title: str = "",
        cwd: str = "",
        provider: str = "",
        model: str = "",
        agent_version: str = "",
        parent_id: Optional[str] = None,
        fork_id: Optional[str] = None,
        messages: Optional[list[Message]] = None,
    ) -> Session:
        session = Session(
            title=title,
            cwd=cwd,
            provider=provider,
            model=model,
            agent_version=agent_version,
            parent_id=parent_id,
            fork_id=fork_id,
        )
        self._insert(session)
        if messages:
            self._insert_messages(session.id, messages)
            session.message_count = len(messages)
            self._update_counters(session.id, session.message_count)
        logger.debug(f"Session created: {session.id}")
        return session

    def get(self, session_id: str) -> Optional[Session]:
        row = self._conn.execute(
            "SELECT * FROM session WHERE id = ?",
            (session_id,),
        ).fetchone()
        return self._row_to_session(row) if row else None

    def get_active(self) -> Optional[Session]:
        row = self._conn.execute(
            "SELECT * FROM session WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1",
        ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Session]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM session WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM session ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def update(self, session: Session) -> None:
        session.updated_at = _utcnow()
        self._conn.execute(
            """UPDATE session SET
                status=?, title=?, cwd=?, model=?, agent_version=?,
                turn_count=?, step_count=?,
                input_tokens=?, output_tokens=?, reasoning_tokens=?,
                cache_read_tokens=?,
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
                session.message_count,
                session.summary,
                _serialize_metadata(session.metadata),
                _ts(session.updated_at),
                _ts(session.ended_at),
                session.id,
            ),
        )
        self._conn.commit()
        logger.debug(f"Session updated: {session.id}")

    def complete(self, session_id: str, summary: Optional[str] = None) -> None:
        now = _utcnow()
        self._conn.execute(
            "UPDATE session SET status='completed', summary=?, ended_at=?, updated_at=? WHERE id=?",
            (summary, _ts(now), _ts(now), session_id),
        )
        self._conn.commit()
        logger.info(f"Session completed: {session_id}")

    def archive(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE session SET status='archived', updated_at=? WHERE id=?",
            (_ts(_utcnow()), session_id),
        )
        self._conn.commit()
        logger.info(f"Session archived: {session_id}")

    def delete(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM session WHERE id=?", (session_id,))
        self._conn.commit()
        logger.info(f"Session deleted: {session_id}")

    def search(self, query: str, limit: int = 20) -> list[Session]:
        if self._fts5_available:
            rows = self._conn.execute(
                """SELECT DISTINCT s.* FROM session s
                   JOIN message m ON m.session_id = s.id
                   JOIN message_fts fts ON fts.rowid = m.id
                   WHERE message_fts MATCH ?
                   ORDER BY s.updated_at DESC LIMIT ?""",
                (query, limit),
            ).fetchall()
        else:
            like = f"%{query}%"
            rows = self._conn.execute(
                """SELECT DISTINCT s.* FROM session s
                   JOIN message m ON m.session_id = s.id
                   WHERE m.content LIKE ? OR m.reasoning LIKE ?
                   ORDER BY s.updated_at DESC LIMIT ?""",
                (like, like, limit),
            ).fetchall()
        return [self._row_to_session(r) for r in rows]

    # ── Messages ──────────────────────────────────────────────

    def append_messages(
        self,
        session_id: str,
        messages: list[Message],
    ) -> int:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            session = self.get(session_id)
            if session is None:
                raise ValueError(f"Session not found: {session_id}")
            existing = session.message_count
            if existing > len(messages):
                logger.warning(
                    f"append_messages: session.message_count ({existing}) > "
                    f"len(messages) ({len(messages)}). Check caller logic."
                )
                return existing
            new_messages = messages[existing:]
            if not new_messages:
                return existing
            turn_index = session.turn_count
            for msg in new_messages:
                rec = _message_to_record(session_id, msg, turn_index)
                self._insert_record(rec)
            count = session.message_count + len(new_messages)
            self._conn.execute(
                "UPDATE session SET message_count=?, updated_at=? WHERE id=?",
                (count, _ts(_utcnow()), session_id),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return count

    def sync_messages(
        self,
        session_id: str,
        messages: list[Message],
    ) -> int:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            session = self.get(session_id)
            if session is None:
                raise ValueError(f"Session not found: {session_id}")
            self._conn.execute("DELETE FROM message WHERE session_id=?", (session_id,))
            turn_index = 0
            for msg in messages:
                rec = _message_to_record(session_id, msg, turn_index)
                self._insert_record(rec)
                if isinstance(msg, UserMessage):
                    turn_index += 1
            self._conn.execute(
                "UPDATE session SET message_count=?, updated_at=? WHERE id=?",
                (len(messages), _ts(_utcnow()), session_id),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return len(messages)

    def get_messages(
        self,
        session_id: str,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> list[Message]:
        if limit is not None:
            rows = self._conn.execute(
                "SELECT * FROM message WHERE session_id=? ORDER BY id LIMIT ? OFFSET ?",
                (session_id, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM message WHERE session_id=? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [_record_to_message(self._row_to_record(r)) for r in rows]

    # ── State persistence ─────────────────────────────────────

    def save_state(self, session_id: str, state: AgentState) -> None:
        if self.get(session_id) is None:
            logger.warning(f"save_state: session {session_id} not found, skipping")
            return
        self.sync_messages(session_id, state.messages)
        self._conn.execute(
            """UPDATE session SET
                turn_count=?, step_count=?,
                input_tokens=?, output_tokens=?,
                reasoning_tokens=?, cache_read_tokens=?,
                updated_at=?
            WHERE id=?""",
            (
                state.turn_count,
                state.step,
                state.usage.total_input,
                state.usage.total_output,
                state.usage.total_reasoning,
                state.usage.total_cache_read,
                _ts(_utcnow()),
                session_id,
            ),
        )
        self._conn.commit()

    def load_state(self, session_id: str) -> Optional[AgentState]:
        session = self.get(session_id)
        if session is None:
            return None
        messages = self.get_messages(session_id)
        return AgentState(
            messages=messages,
            turn_count=session.turn_count,
            step=session.step_count,
            session_id=session.id,
            usage=SessionUsage(
                total_input=session.input_tokens,
                total_output=session.output_tokens,
                total_reasoning=session.reasoning_tokens,
                total_cache_read=session.cache_read_tokens,
            ),
        )

    # ── Session resolution (compression chain aware) ─────────

    def resolve(
        self,
        session_id: str,
        system_message: SystemMessage,
        context_size: int = 0,
    ) -> Optional[AgentState]:
        tip = self.get_compression_tip(session_id)
        loaded = self.load_state(tip)
        if loaded is None:
            return None
        loaded.usage.context_size = context_size
        if not any(isinstance(m, SystemMessage) for m in loaded.messages):
            loaded.messages.insert(0, system_message)
        return loaded

    # ── Compaction chain ──────────────────────────────────────

    def get_compression_tip(self, session_id: str) -> str:
        current = session_id
        max_depth = 1000
        depth = 0
        while True:
            row = self._conn.execute(
                "SELECT id FROM session WHERE parent_id=? AND status='active' LIMIT 1",
                (current,),
            ).fetchone()
            if row is None:
                return current
            current = cast(str, row["id"])
            depth += 1
            if depth > max_depth:
                logger.warning(
                    f"Compression chain too deep (>{max_depth}) for {session_id}, stopping"
                )
                return current

    def chain(self, session_id: str) -> list[str]:
        ids: list[str] = []
        current: Optional[str] = session_id
        while current:
            ids.append(current)
            row = self._conn.execute(
                "SELECT parent_id FROM session WHERE id=?",
                (current,),
            ).fetchone()
            current = row["parent_id"] if row else None
        return ids

    def create_compacted_child(
        self,
        parent_id: str,
        system_messages: Sequence[Message],
        summary_content: str,
        tail_messages: Sequence[Message],
    ) -> Session:
        parent = self.get(parent_id)
        tail_all = (
            list(system_messages)
            + [
                UserMessage(content=summary_content.strip()),
            ]
            + list(tail_messages)
        )
        child = self.create(
            title=parent.title if parent else "",
            cwd=parent.cwd if parent else "",
            provider=parent.provider if parent else "",
            model=parent.model if parent else "",
            agent_version=parent.agent_version if parent else "",
            parent_id=parent_id,
            messages=tail_all,
        )
        self.complete(parent_id, summary=summary_content)
        logger.info(f"Compacted {parent_id} -> {child.id}")
        return child

    # ── Fork ──────────────────────────────────────────────────

    def fork(
        self,
        session_id: str,
        title: str = "",
    ) -> Session:
        parent = self.get(session_id)
        if parent is None:
            raise ValueError(f"Source session not found: {session_id}")
        messages = self.get_messages(session_id)
        fork_title = title or parent.title or ""
        child = self.create(
            title=fork_title,
            cwd=parent.cwd,
            provider=parent.provider,
            model=parent.model,
            agent_version=parent.agent_version,
            fork_id=session_id,
            messages=messages,
        )
        logger.info(f"Forked {session_id} -> {child.id}")
        return child

    # ── Subagent session ──────────────────────────────────────

    def create_child(
        self,
        parent_id: str,
        model: str = "",
        messages: Optional[list[Message]] = None,
    ) -> Session:
        parent = self.get(parent_id)
        child = self.create(
            title="",
            cwd=parent.cwd if parent else "",
            provider=parent.provider if parent else "",
            model=model or (parent.model if parent else ""),
            agent_version=parent.agent_version if parent else "",
            parent_id=parent_id,
            messages=messages,
        )
        logger.debug(f"Child session created: {child.id} (parent={parent_id})")
        return child

    def get_parent(self, session_id: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT parent_id FROM session WHERE id=?",
            (session_id,),
        ).fetchone()
        return row["parent_id"] if row else None

    def get_depth(self, session_id: str) -> int:
        depth = 0
        current: Optional[str] = session_id
        max_depth = 1000
        while current and depth <= max_depth:
            current = self.get_parent(current)
            depth += 1
        if depth > max_depth:
            logger.warning(f"Session chain too deep (>{max_depth}) for {session_id}")
        return depth

    def get_children(self, session_id: str) -> list[Session]:
        rows = self._conn.execute(
            "SELECT * FROM session WHERE parent_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    # ── Title ─────────────────────────────────────────────────

    def set_title(self, session_id: str, title: str) -> None:
        self._conn.execute(
            "UPDATE session SET title=? WHERE id=?",
            (title, session_id),
        )
        self._conn.commit()

    # ── Internal helpers ─────────────────────────────────────

    def _insert(self, session: Session) -> None:
        self._conn.execute(
            """INSERT INTO session (
                id, status, title, cwd, provider, model, agent_version,
                turn_count, step_count,
                input_tokens, output_tokens, reasoning_tokens,
                cache_read_tokens,
                parent_id, fork_id,
                message_count, summary, metadata,
                created_at, updated_at, ended_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
        self._conn.commit()

    def _insert_messages(
        self,
        session_id: str,
        messages: list[Message],
    ) -> None:
        turn_index = 0
        for msg in messages:
            rec = _message_to_record(session_id, msg, turn_index)
            self._insert_record(rec)
            if isinstance(msg, UserMessage):
                turn_index += 1

    def _insert_record(self, rec: MessageRecord) -> None:
        self._conn.execute(
            """INSERT INTO message (
                session_id, role, content, tool_call_id,
                tool_name, tool_args, reasoning,
                token_count, timestamp, turn_index
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                rec.session_id,
                rec.role,
                rec.content,
                rec.tool_call_id,
                rec.tool_name,
                rec.tool_args,
                rec.reasoning,
                rec.token_count,
                _ts(rec.timestamp),
                rec.turn_index,
            ),
        )

    def _update_counters(self, session_id: str, message_count: int) -> None:
        self._conn.execute(
            "UPDATE session SET message_count=?, updated_at=? WHERE id=?",
            (message_count, _ts(_utcnow()), session_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            status=row["status"],
            title=row["title"],
            cwd=row["cwd"],
            provider=row["provider"] if "provider" in row.keys() else "",
            model=row["model"],
            agent_version=row["agent_version"],
            turn_count=row["turn_count"],
            step_count=row["step_count"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            reasoning_tokens=row["reasoning_tokens"],
            cache_read_tokens=row["cache_read_tokens"],
            parent_id=row["parent_id"],
            fork_id=row["fork_id"],
            message_count=row["message_count"],
            summary=row["summary"],
            metadata=_deserialize_metadata(row["metadata"] or "{}"),
            created_at=_from_ts(row["created_at"]) or _utcnow(),
            updated_at=_from_ts(row["updated_at"]) or _utcnow(),
            ended_at=_from_ts(row["ended_at"]) if row["ended_at"] else None,
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            tool_call_id=row["tool_call_id"],
            tool_name=row["tool_name"],
            tool_args=row["tool_args"],
            reasoning=row["reasoning"],
            token_count=row["token_count"],
            timestamp=_from_ts(row["timestamp"]) or _utcnow(),
            turn_index=row["turn_index"],
        )
