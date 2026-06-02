from __future__ import annotations

import sqlite3
from pathlib import Path
from collections.abc import Sequence
from typing import Optional

from loguru import logger

from laffyhand.agent.llm.specs.models import AssistantMessage, Message, SystemMessage, ToolMessage, UserMessage
from laffyhand.agent.llm.specs.models import ModelID, ProviderID, ToolCallContent, Usage
from laffyhand.agent.session.models import (
    AssistantContent,
    AssistantData,
    AssistantReasoningPart,
    AssistantTextPart,
    AssistantToolPart,
    MessageSnapshot,
    MessageTime,
    Model,
    Session,
    SessionMessage,
    ShellData,
    SyntheticData,
    TokenCache,
    TokenDetail,
    ToolStateCompleted,
    ToolStatePending,
    UserData,
    _utcnow,
)
from laffyhand.agent.db.repository import SessionRepo, MessageRepo
from laffyhand.agent.db.schema import create_tables
from laffyhand.agent.schemas import AgentState, SessionID, SessionUsage


def _generate_id() -> str:
    from uuid import uuid4
    return _utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]


def _message_to_session_message(msg: Message, session_id: str) -> SessionMessage:
    now = int(_utcnow().timestamp())
    if isinstance(msg, SystemMessage):
        return SessionMessage(
            id=_generate_id(), session_id=session_id, type="synthetic",
            time_created=now, time_updated=now,
            data=SyntheticData(sessionID=session_id, text=msg.content),
        )
    if isinstance(msg, UserMessage):
        return SessionMessage(
            id=_generate_id(), session_id=session_id, type="user",
            time_created=now, time_updated=now,
            data=UserData(text=msg.content),
        )
    if isinstance(msg, AssistantMessage):
        content: list[AssistantContent] = []
        if msg.reasoning:
            content.append(AssistantReasoningPart(id=f"reasoning-{now}", text=msg.reasoning))
        if msg.content:
            content.append(AssistantTextPart(text=msg.content))
        if msg.tool_calls:
            for tc in msg.tool_calls:
                content.append(AssistantToolPart(
                    id=tc.tool_call_id, name=tc.tool_name,
                    state=ToolStatePending(input=tc.args),
                    time=MessageTime(created=now),
                ))
        tokens = TokenDetail(
            input=msg.tokens.input_tokens or 0, output=msg.tokens.output_tokens or 0,
            reasoning=msg.tokens.reasoning_tokens or 0,
            cache=TokenCache(read=msg.tokens.cache_read_tokens or 0, write=msg.tokens.cache_write_tokens or 0),
        ) if msg.tokens else None
        return SessionMessage(
            id=_generate_id(), session_id=session_id, type="assistant",
            time_created=now, time_updated=now,
            data=AssistantData(
                agent="", model=Model(id=ModelID(""), provider=ProviderID("")),
                snapshot=MessageSnapshot(), finish="stop", cost=0, tokens=tokens,
                content=content,
            ),
        )
    if isinstance(msg, ToolMessage):
        return SessionMessage(
            id=_generate_id(), session_id=session_id, type="shell",
            time_created=now, time_updated=now,
            data=ShellData(
                callID=msg.tool_call_id, command="", output=msg.content,
                is_error=msg.is_error, time=MessageTime(created=now),
            ),
        )
    raise TypeError(f"Unknown message type: {type(msg).__name__}")


def _session_message_to_message(sm: SessionMessage) -> Message:
    if sm.type == "synthetic":
        d = sm.data
        assert isinstance(d, SyntheticData)
        return SystemMessage(content=d.text)
    if sm.type == "user":
        d = sm.data
        assert isinstance(d, UserData)
        return UserMessage(content=d.text)
    if sm.type == "assistant":
        d = sm.data
        assert isinstance(d, AssistantData)
        content_parts: list[str] = []
        reasoning: str | None = None
        tool_calls: list[ToolCallContent] | None = None
        for part in d.content:
            if isinstance(part, AssistantTextPart):
                content_parts.append(part.text)
            elif isinstance(part, AssistantReasoningPart):
                reasoning = (reasoning or "") + part.text
            elif isinstance(part, AssistantToolPart):
                if tool_calls is None:
                    tool_calls = []
                if isinstance(part.state, ToolStateCompleted):
                    args = part.state.input.get("input", "") if isinstance(part.state.input, dict) else str(part.state.input)
                    tool_calls.append(ToolCallContent(tool_call_id=part.id, tool_name=part.name, args=args))
                elif isinstance(part.state, ToolStatePending):
                    tool_calls.append(ToolCallContent(tool_call_id=part.id, tool_name=part.name, args=part.state.input))
        combined = "".join(content_parts) if content_parts else None
        usage = Usage(
            input_tokens=d.tokens.input, output_tokens=d.tokens.output,
            reasoning_tokens=d.tokens.reasoning,
            cache_read_tokens=d.tokens.cache.read, cache_write_tokens=d.tokens.cache.write,
        ) if d.tokens else None
        return AssistantMessage(content=combined, reasoning=reasoning, tool_calls=tool_calls, tokens=usage)
    if sm.type == "shell":
        d = sm.data
        assert isinstance(d, ShellData)
        return ToolMessage(tool_call_id=d.callID, content=d.output, is_error=d.is_error)
    raise ValueError(f"Unknown session message type: {sm.type}")


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
        parent_id: Optional[str] = None,
        fork_id: Optional[str] = None,
        messages: Optional[list[Message]] = None,
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
                self._messages.insert(_message_to_session_message(msg, session.id))
            session.message_count = len(messages)
            self._update_counters(session.id, session.message_count)
        logger.debug(f"Session created: {session.id}")
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def get_active(self) -> Optional[Session]:
        return self._sessions.get_active()

    def list_sessions(self, status: Optional[str] = None, limit: int = 20, offset: int = 0) -> list[Session]:
        return self._sessions.list_sessions(status=status, limit=limit, offset=offset)

    def update(self, session: Session) -> None:
        self._sessions.update(session)

    def complete(self, session_id: str, summary: Optional[str] = None) -> None:
        self._sessions.complete(session_id, summary=summary)

    def archive(self, session_id: str) -> None:
        self._sessions.archive(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.delete(session_id)

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
                self._messages.insert(_message_to_session_message(msg, session_id))
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
                self._messages.insert(_message_to_session_message(msg, session_id))
            self._update_counters(session_id, len(messages))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return len(messages)

    def get_messages(self, session_id: str, offset: int = 0, limit: Optional[int] = None) -> list[Message]:
        return [_session_message_to_message(sm) for sm in self._messages.get_by_session(session_id, offset=offset, limit=limit)]

    # ── State persistence ─────────────────────────────────────

    def save_state(self, session_id: str, state: AgentState) -> None:
        if self._sessions.get(session_id) is None:
            logger.warning(f"save_state: session {session_id} not found, skipping")
            return
        self.sync_messages(session_id, state.messages)
        self._conn.execute(
            """UPDATE session SET turn_count=?, step_count=?,
                input_tokens=?, output_tokens=?, reasoning_tokens=?,
                cache_read_tokens=?, cache_write_tokens=?, updated_at=?
            WHERE id=?""",
            (state.turn_count, state.step, state.usage.total_input, state.usage.total_output,
             state.usage.total_reasoning, state.usage.total_cache_read, state.usage.total_cache_write,
             _utcnow().isoformat(), session_id),
        )
        self._conn.commit()

    def load_state(self, session_id: str) -> Optional[AgentState]:
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
            ),
        )

    def resolve(self, session_id: str, system_message: SystemMessage, context_size: int = 0) -> Optional[AgentState]:
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

    def create_child(self, parent_id: str, model: str = "", messages: Optional[list[Message]] = None) -> Session:
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

    def get_parent(self, session_id: str) -> Optional[str]:
        return self._sessions.get_parent(session_id)

    def get_depth(self, session_id: str) -> int:
        depth = 0
        current: Optional[str] = session_id
        max_depth = 1000
        while current and depth <= max_depth:
            current = self._sessions.get_parent(current)
            depth += 1
        if depth > max_depth:
            logger.warning(f"Session chain too deep (>{max_depth}) for {session_id}")
        return depth

    def get_children(self, session_id: str) -> list[Session]:
        return self._sessions.get_children(session_id)

    # ── Title ─────────────────────────────────────────────────

    def set_title(self, session_id: str, title: str) -> None:
        self._sessions.set_title(session_id, title)

    # ── Internal ──────────────────────────────────────────────

    def _update_counters(self, session_id: str, message_count: int) -> None:
        self._conn.execute(
            "UPDATE session SET message_count=?, updated_at=? WHERE id=?",
            (message_count, _utcnow().isoformat(), session_id),
        )
        self._conn.commit()
