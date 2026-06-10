from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from loguru import logger

from laffyhand.core._ports import MessageRepository, SessionRepository
from laffyhand.core.domain.messages import (
    AssistantMessage,
    CompactionMessage,
    Message,
    ModelID,
    ProviderID,
    SystemMessage,
    UserMessage,
)
from laffyhand.core.exceptions import SessionError
from laffyhand.core.models import AgentState, SessionID, SessionUsage
from laffyhand.core.session.models import Session


class SessionManager:
    def __init__(
        self,
        sessions: SessionRepository,
        messages: MessageRepository,
        conn: sqlite3.Connection,
    ) -> None:
        self._sessions = sessions
        self._messages = messages
        self._conn = conn
        self._pending_meta: dict[str, dict] = {}

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        self._conn.close()

    # ── Session CRUD ──────────────────────────────────────────

    def create(
        self,
        title: str = "",
        cwd: str = "",
        provider: str = "",
        model: str = "",
        agent_name: str = "",
        parent_id: str | None = None,
        messages: Sequence[Message] | None = None,
    ) -> Session:
        session = Session(
            title=title,
            cwd=cwd,
            provider=ProviderID(provider) if provider else ProviderID(""),
            model=ModelID(model) if model else ModelID(""),
            agent_name=agent_name,
            parent_id=parent_id,
        )
        self._sessions.insert(session)
        if messages:
            for msg in messages:
                self._messages.insert(msg, session.id)
            session.message_count = len(messages)
            self._sessions.update_counters(
                session.id, message_count=session.message_count
            )
        self._conn.commit()
        logger.debug(f"Session created: {session.id}")
        return session

    def set_pending_meta(self, session_id: str, **kwargs: str) -> None:
        self._pending_meta[session_id] = kwargs

    def ensure_exists(self, session_id: str) -> Session:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        meta = self._pending_meta.pop(session_id, {})
        session = Session(
            id=session_id,
            title=meta.get("title", ""),
            cwd=meta.get("cwd", ""),
            provider=ProviderID(meta.get("provider", ""))
            if meta.get("provider")
            else ProviderID(""),
            model=ModelID(meta.get("model", "")) if meta.get("model") else ModelID(""),
            agent_name=meta.get("agent_name", ""),
        )
        self._sessions.insert(session)
        self._conn.commit()
        logger.debug(f"Session lazily persisted: {session.id}")
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_active(self) -> Session | None:
        return self._sessions.get_active()

    def list_sessions(
        self, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> list[Session]:
        return self._sessions.list_sessions(status=status, limit=limit, offset=offset)

    def complete(self, session_id: str) -> None:
        self._sessions.complete(session_id)
        self._conn.commit()

    def archive(self, session_id: str) -> None:
        self._sessions.archive(session_id)
        self._conn.commit()

    def delete(self, session_id: str) -> None:
        self._sessions.delete(session_id)
        self._conn.commit()

    def search(self, query: str, limit: int = 20) -> list[Session]:
        return self._sessions.search(query, limit=limit)

    # ── Transaction helpers ────────────────────────────────────

    def _begin(self) -> bool:
        if not self._conn.in_transaction:
            self._conn.execute("BEGIN IMMEDIATE")
            return True
        return False

    def _end(self, began: bool) -> None:
        if began:
            self._conn.commit()

    def _rollback(self, began: bool) -> None:
        if began:
            self._conn.rollback()

    # ── Messages ──────────────────────────────────────────────

    def store_messages(self, session_id: str, messages: Sequence[Message]) -> int:
        session = self.ensure_exists(session_id)
        began = self._begin()
        try:
            existing = self._messages.count_by_session(session_id)
            if existing > session.message_count:
                logger.warning(
                    f"store_messages: session.message_count ({session.message_count}) "
                    f"< actual message count ({existing}). Resetting counter."
                )
                session.message_count = existing
            for msg in messages:
                self._messages.insert(msg, session_id)
            new_count = existing + len(messages)
            self._sessions.update_counters(session_id, message_count=new_count)
            self._end(began)
        except Exception:
            self._rollback(began)
            raise
        return new_count

    def get_messages(
        self, session_id: str, offset: int = 0, limit: int | None = None
    ) -> list[Message]:
        return self._messages.get_by_session(
            session_id, offset=offset, limit=limit
        )

    # ── State persistence ─────────────────────────────────────

    def save_state(self, session_id: str, state: AgentState) -> None:
        if self._sessions.get(session_id) is None:
            logger.warning(f"save_state: session {session_id} not found, skipping")
            return
        began = self._begin()
        try:
            existing = self._messages.count_by_session(session_id)
            state_count = len(state.messages)

            if state_count > existing:
                to_store = state.messages[existing:]
                for msg in to_store:
                    self._messages.insert(msg, session_id)
                logger.debug(
                    f"save_state: stored {len(to_store)} message(s) for {session_id} "
                    f"(state_count={state_count}, existing={existing})"
                )
            elif state_count < existing:
                logger.warning(
                    f"save_state: state has fewer messages ({state_count}) "
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
                message_count=max(state_count, existing),
            )
            self._end(began)
        except Exception:
            self._rollback(began)
            raise

    def _reconstruct_curr_context(self, messages: list[Message]) -> int:
        for msg in reversed(messages):
            if (
                isinstance(msg, AssistantMessage)
                and msg.tokens
                and msg.tokens.input_tokens
            ):
                return msg.tokens.input_tokens
        return 0

    def load_state(self, session_id: str) -> AgentState | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        messages = self.get_messages(session_id)
        return AgentState(
            messages=messages,
            turn_count=session.turn_count,
            step=session.step_count,
            session_id=SessionID(session.id),
            usage=SessionUsage(
                curr_context_usage=self._reconstruct_curr_context(messages),
                total_input=session.input_tokens,
                total_output=session.output_tokens,
                total_reasoning=session.reasoning_tokens,
                total_cache_read=session.cache_read_tokens,
                total_cache_write=session.cache_write_tokens,
                cost=0,
            ),
        )

    def load_compressed_state(
        self, session_id: str, system_message: SystemMessage, context_size: int = 0
    ) -> AgentState | None:
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
        tail_all = (
            list(system_messages)
            + [UserMessage(content=summary_content.strip())]
            + list(tail_messages)
        )

        began = self._begin()
        try:
            # Create child session inline (no auto-commit)
            child = Session(
                title=parent.title if parent else "",
                cwd=parent.cwd if parent else "",
                provider=ProviderID(parent.provider) if parent and parent.provider else ProviderID(""),
                model=ModelID(parent.model) if parent and parent.model else ModelID(""),
                agent_name=parent.agent_name if parent else "",
                parent_id=parent_id,
            )
            self._sessions.insert(child)
            for msg in tail_all:
                self._messages.insert(msg, child.id)
            child.message_count = len(tail_all)
            self._sessions.update_counters(
                child.id, message_count=child.message_count,
            )

            # Record compaction event in parent session
            compaction_msg = CompactionMessage(
                reason="overflow",
                summary=summary_content,
                child_session_id=child.id,
            )
            self._messages.insert(compaction_msg, parent_id)
            parent_msg_count = self._messages.count_by_session(parent_id)
            self._sessions.update_counters(parent_id, message_count=parent_msg_count)

            # Complete parent within the same transaction
            self._sessions.complete(parent_id)

            self._end(began)
        except Exception:
            self._rollback(began)
            raise

        logger.info(f"Compacted {parent_id} -> {child.id}")
        return child

    # ── Fork ──────────────────────────────────────────────────

    def fork(self, session_id: str, title: str = "") -> Session:
        parent = self._sessions.get(session_id)
        if parent is None:
            raise SessionError(f"Source session not found: {session_id}")
        messages = self.get_messages(session_id)
        child = self.create(
            title=title or parent.title or "",
            cwd=parent.cwd,
            provider=parent.provider,
            model=parent.model,
            agent_name=parent.agent_name,
            messages=messages,
        )
        logger.info(f"Forked {session_id} -> {child.id}")
        return child

    # ── Subagent session ──────────────────────────────────────

    def create_child(
        self, parent_id: str, model: str = "", messages: list[Message] | None = None
    ) -> Session:
        parent = self._sessions.get(parent_id)
        child = self.create(
            title="",
            cwd=parent.cwd if parent else "",
            provider=parent.provider if parent else "",
            model=model or (parent.model if parent else ""),
            agent_name=parent.agent_name if parent else "",
            parent_id=parent_id,
            messages=messages,
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
