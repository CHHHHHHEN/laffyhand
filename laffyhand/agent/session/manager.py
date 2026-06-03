from __future__ import annotations

import sqlite3
from pathlib import Path
from collections.abc import Sequence

from loguru import logger

from laffyhand.agent.llm.specs.models import Message, SystemMessage, UserMessage
from laffyhand.agent.llm.specs.models import ModelID, ProviderID
from laffyhand.agent.session.models import Session, _utcnow
from laffyhand.agent.session.converters import message_to_session_message, session_message_to_message
from laffyhand.agent.db.repository import SessionRepo, MessageRepo
from laffyhand.agent.db.schema import create_tables
from laffyhand.agent.schemas import AgentState, SessionID, SessionUsage


class SessionManager:
    """Orchestrates session operations using SessionRepo and MessageRepo."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        create_tables(self._conn)
        self._sessions = SessionRepo(self._conn)
        self._messages = MessageRepo(self._conn)

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
        parent_id: str | None = None,
        fork_id: str | None = None,
        messages: list[Message] | None = None,
    ) -> Session:
        session = Session(
            title=title, cwd=cwd,
            provider=ProviderID(provider) if provider else ProviderID(""),
            model=ModelID(model) if model else ModelID(""),
            agent_version=agent_version, parent_id=parent_id, fork_id=fork_id,
        )
        self._sessions.insert(session)
        if messages:
            for msg in messages:
                self._messages.insert(message_to_session_message(msg, session.id))
            session.message_count = len(messages)
            self._update_counters(session.id, session.message_count)
        self._conn.commit()
        logger.debug(f"Session created: {session.id}")
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_active(self) -> Session | None:
        return self._sessions.get_active()

    def list_sessions(self, status: str | None = None, limit: int = 20, offset: int = 0) -> list[Session]:
        return self._sessions.list_sessions(status=status, limit=limit, offset=offset)

    def update(self, session: Session) -> None:
        self._sessions.update(session)
        self._conn.commit()

    def complete(self, session_id: str, summary: str | None = None) -> None:
        self._sessions.complete(session_id, summary=summary)
        self._conn.commit()

    def archive(self, session_id: str) -> None:
        self._sessions.archive(session_id)
        self._conn.commit()

    def delete(self, session_id: str) -> None:
        self._sessions.delete(session_id)
        self._conn.commit()

    def search(self, query: str, limit: int = 20) -> list[Session]:
        return self._sessions.search(query, limit=limit)

    # ── Messages ──────────────────────────────────────────────

    def store_messages(self, session_id: str, messages: list[Message]) -> int:
        """Store new Message objects as V2 session messages and update counters."""
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self._messages.count_by_session(session_id)
            if existing > session.message_count:
                logger.warning(
                    f"store_messages: session.message_count ({session.message_count}) "
                    f"< actual message count ({existing}). Resetting counter."
                )
                session.message_count = existing
            for msg in messages:
                self._messages.insert(message_to_session_message(msg, session_id))
            new_count = existing + len(messages)
            self._update_counters(session_id, new_count)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return new_count

    def sync_messages(self, session_id: str, messages: list[Message]) -> int:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            session = self._sessions.get(session_id)
            if session is None:
                raise ValueError(f"Session not found: {session_id}")
            self._messages.delete_by_session(session_id)
            for msg in messages:
                self._messages.insert(message_to_session_message(msg, session_id))
            self._update_counters(session_id, len(messages))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return len(messages)

    def get_messages(self, session_id: str, offset: int = 0, limit: int | None = None) -> list[Message]:
        return [session_message_to_message(sm) for sm in self._messages.get_by_session(session_id, offset=offset, limit=limit)]

    # ── State persistence ─────────────────────────────────────

    def save_state(self, session_id: str, state: AgentState) -> None:
        if self._sessions.get(session_id) is None:
            logger.warning(f"save_state: session {session_id} not found, skipping")
            return
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self._messages.count_by_session(session_id)
            if len(state.messages) > existing:
                for msg in state.messages[existing:]:
                    self._messages.insert(message_to_session_message(msg, session_id))
            elif len(state.messages) < existing:
                logger.warning(
                    f"save_state: state has fewer messages ({len(state.messages)}) "
                    f"than DB ({existing}). Appending nothing — DB is source of truth."
                )

            self._sessions.update_counters(
                session_id,
                turn_count=state.turn_count,
                step_count=state.step,
                input_tokens=state.usage.total_input,
                output_tokens=state.usage.total_output,
                reasoning_tokens=state.usage.total_reasoning,
                cache_read_tokens=state.usage.total_cache_read,
                cache_write_tokens=state.usage.total_cache_write,
                cost=state.usage.cost,
                message_count=max(len(state.messages), existing),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def load_state(self, session_id: str) -> AgentState | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        messages = self.get_messages(session_id)
        return AgentState(
            messages=messages, turn_count=session.turn_count, step=session.step_count,
            session_id=SessionID(session.id),
            usage=SessionUsage(
                total_input=session.input_tokens, total_output=session.output_tokens,
                total_reasoning=session.reasoning_tokens,
                total_cache_read=session.cache_read_tokens,
                total_cache_write=session.cache_write_tokens,
                cost=session.cost,
            ),
        )

    def load_compressed_state(self, session_id: str, system_message: SystemMessage, context_size: int = 0) -> AgentState | None:
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
        return self._sessions.get_compression_tip(session_id)

    def chain(self, session_id: str) -> list[str]:
        return self._sessions.chain(session_id)

    def create_compacted_child(
        self,
        parent_id: str,
        system_messages: Sequence[Message],
        summary_content: str,
        tail_messages: Sequence[Message],
    ) -> Session:
        parent = self._sessions.get(parent_id)
        tail_all = list(system_messages) + [UserMessage(content=summary_content.strip())] + list(tail_messages)
        child = self.create(
            title=parent.title if parent else "", cwd=parent.cwd if parent else "",
            provider=parent.provider if parent else "", model=parent.model if parent else "",
            agent_version=parent.agent_version if parent else "",
            parent_id=parent_id, messages=tail_all,
        )
        self._sessions.complete(parent_id, summary=summary_content)
        self._conn.commit()
        logger.info(f"Compacted {parent_id} -> {child.id}")
        return child

    # ── Fork ──────────────────────────────────────────────────

    def fork(self, session_id: str, title: str = "") -> Session:
        parent = self._sessions.get(session_id)
        if parent is None:
            raise ValueError(f"Source session not found: {session_id}")
        messages = self.get_messages(session_id)
        child = self.create(
            title=title or parent.title or "", cwd=parent.cwd,
            provider=parent.provider, model=parent.model,
            agent_version=parent.agent_version, fork_id=session_id,
            messages=messages,
        )
        logger.info(f"Forked {session_id} -> {child.id}")
        return child

    # ── Subagent session ──────────────────────────────────────

    def create_child(self, parent_id: str, model: str = "", messages: list[Message] | None = None) -> Session:
        parent = self._sessions.get(parent_id)
        child = self.create(
            title="", cwd=parent.cwd if parent else "",
            provider=parent.provider if parent else "",
            model=model or (parent.model if parent else ""),
            agent_version=parent.agent_version if parent else "",
            parent_id=parent_id, messages=messages,
        )
        logger.debug(f"Child session created: {child.id} (parent={parent_id})")
        return child

    def get_parent(self, session_id: str) -> str | None:
        return self._sessions.get_parent(session_id)

    def get_depth(self, session_id: str) -> int:
        return self._sessions.get_depth(session_id)

    def get_children(self, session_id: str) -> list[Session]:
        return self._sessions.get_children(session_id)

    # ── Title ─────────────────────────────────────────────────

    def set_title(self, session_id: str, title: str) -> None:
        self._sessions.set_title(session_id, title)
        self._conn.commit()

    # ── Internal ──────────────────────────────────────────────

    def _update_counters(self, session_id: str, message_count: int) -> None:
        self._conn.execute(
            "UPDATE session SET message_count=?, updated_at=? WHERE id=?",
            (message_count, _utcnow().isoformat(), session_id),
        )
