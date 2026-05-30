from __future__ import annotations

import pytest

from laffyhand.agent.session import SessionManager
from laffyhand.agent.schemas import (
    AgentState, AssistantMessage, SystemMessage, ToolCallContent,
    ToolMessage, UserMessage, SessionUsage,
)


def make_messages() -> list:
    return [
        SystemMessage(content="You are a helpful assistant."),
        UserMessage(content="Hello!"),
        AssistantMessage(content="Hi there!", tokens=None),
        UserMessage(content="What is Python?"),
        AssistantMessage(content="Python is a programming language."),
    ]


class TestSessionCRUD:
    def test_create(self, session_manager: SessionManager) -> None:
        session = session_manager.create(cwd="/test", model="gpt-4")
        assert session.id != ""
        assert session.status == "active"
        assert session.cwd == "/test"
        assert session.model == "gpt-4"
        assert session.turn_count == 0

    def test_get(self, session_manager: SessionManager) -> None:
        created = session_manager.create()
        fetched = session_manager.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_not_found(self, session_manager: SessionManager) -> None:
        assert session_manager.get("nonexistent") is None

    def test_get_active(self, session_manager: SessionManager) -> None:
        session_manager.create(model="gpt-4")
        s2 = session_manager.create(model="gpt-5")
        active = session_manager.get_active()
        assert active is not None
        assert active.id == s2.id

    def test_list_sessions(self, session_manager: SessionManager) -> None:
        session_manager.create()
        session_manager.create()
        all_sessions = session_manager.list_sessions()
        assert len(all_sessions) == 2

    def test_list_with_status_filter(self, session_manager: SessionManager) -> None:
        s1 = session_manager.create()
        s2 = session_manager.create()
        session_manager.complete(s2.id)
        active = session_manager.list_sessions(status="active")
        assert len(active) == 1
        assert active[0].id == s1.id

    def test_complete(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        session_manager.complete(session.id, summary="Done!")
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "completed"
        assert fetched.summary == "Done!"
        assert fetched.ended_at is not None

    def test_archive(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        session_manager.archive(session.id)
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "archived"

    def test_delete(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        session_manager.delete(session.id)
        assert session_manager.get(session.id) is None

    def test_update(self, session_manager: SessionManager) -> None:
        session = session_manager.create(title="old")
        session.title = "new"
        session_manager.update(session)
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.title == "new"


class TestMessages:
    def test_create_with_messages(self, session_manager: SessionManager) -> None:
        msgs = make_messages()
        session = session_manager.create(messages=msgs)
        assert session.message_count == len(msgs)

    def test_append_messages(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        msgs = make_messages()
        count = session_manager.append_messages(session.id, msgs)
        assert count == len(msgs)

    def test_append_messages_incremental(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        first = [
            SystemMessage(content="system"),
            UserMessage(content="hi"),
        ]
        session_manager.append_messages(session.id, first)
        second = [AssistantMessage(content="hello")]
        session_manager.append_messages(session.id, first + second)
        loaded = session_manager.get_messages(session.id)
        assert len(loaded) == 3

    def test_get_messages(self, session_manager: SessionManager) -> None:
        msgs = make_messages()
        session = session_manager.create(messages=msgs)
        loaded = session_manager.get_messages(session.id)
        assert len(loaded) == len(msgs)
        assert isinstance(loaded[0], SystemMessage)
        assert isinstance(loaded[1], UserMessage)
        assert loaded[1].content == "Hello!"

    def test_get_messages_with_limit(self, session_manager: SessionManager) -> None:
        msgs = make_messages()
        session = session_manager.create(messages=msgs)
        loaded = session_manager.get_messages(session.id, limit=2)
        assert len(loaded) == 2

    def test_sync_messages(self, session_manager: SessionManager) -> None:
        msgs = make_messages()
        session = session_manager.create(messages=msgs)
        new_msgs = [SystemMessage(content="New system.")]
        session_manager.sync_messages(session.id, new_msgs)
        loaded = session_manager.get_messages(session.id)
        assert len(loaded) == 1
        assert loaded[0].content == "New system."

    def test_assistant_message_with_tool_calls(self, session_manager: SessionManager) -> None:
        tc = ToolCallContent(
            tool_call_id="call_1",
            tool_name="test_tool",
            args='{"key": "value"}',
        )
        msgs: list = [
            AssistantMessage(
                content="Calling tool...",
                tool_calls=[tc],
            ),
            ToolMessage(tool_call_id="call_1", content="Result!"),
        ]
        session = session_manager.create(messages=msgs)
        loaded = session_manager.get_messages(session.id)
        assert len(loaded) == 2
        assert isinstance(loaded[0], AssistantMessage)
        assert loaded[0].tool_calls is not None
        assert len(loaded[0].tool_calls) == 1
        assert loaded[0].tool_calls[0].tool_call_id == "call_1"
        assert isinstance(loaded[1], ToolMessage)
        assert loaded[1].content == "Result!"


class TestStatePersistence:
    def test_save_and_load_state(self, session_manager: SessionManager) -> None:
        msgs = make_messages()
        session = session_manager.create()
        state = AgentState(
            messages=msgs,
            turn_count=3,
            step=5,
            session_id=session.id,
            usage=SessionUsage(
                total_input=100,
                total_output=50,
                total_reasoning=10,
            ),
        )
        session_manager.save_state(session.id, state)
        loaded = session_manager.load_state(session.id)
        assert loaded is not None
        assert loaded.turn_count == 3
        assert loaded.step == 5
        assert loaded.session_id == session.id
        assert loaded.usage.total_input == 100
        assert loaded.usage.total_output == 50
        assert len(loaded.messages) == len(msgs)

    def test_load_nonexistent(self, session_manager: SessionManager) -> None:
        assert session_manager.load_state("nonexistent") is None


class TestCompactionChain:
    def test_chain_from_root(self, session_manager: SessionManager) -> None:
        root = session_manager.create()
        child = session_manager.create(parent_id=root.id)
        grandchild = session_manager.create(parent_id=child.id)
        ids = session_manager.chain(grandchild.id)
        assert ids == [grandchild.id, child.id, root.id]

    def test_compression_tip(self, session_manager: SessionManager) -> None:
        root = session_manager.create()
        child = session_manager.create(parent_id=root.id)
        grandchild = session_manager.create(parent_id=child.id)
        tip = session_manager.get_compression_tip(root.id)
        assert tip == grandchild.id

    def test_compression_tip_no_children(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        tip = session_manager.get_compression_tip(session.id)
        assert tip == session.id

    def test_compression_tip_skips_completed(self, session_manager: SessionManager) -> None:
        root = session_manager.create()
        child = session_manager.create(parent_id=root.id)
        session_manager.complete(child.id)
        tip = session_manager.get_compression_tip(root.id)
        assert tip == root.id

    def test_compact_creates_child(self, session_manager: SessionManager) -> None:
        msgs = make_messages()
        parent = session_manager.create(messages=msgs)
        system = [msgs[0]]
        tail = msgs[2:]
        child = session_manager.create_compacted_child(
            parent_id=parent.id,
            system_messages=system,
            summary_content="Summarized conversation.",
            tail_messages=tail,
        )
        assert child.parent_id == parent.id
        assert child.status == "active"
        parent_fetched = session_manager.get(parent.id)
        assert parent_fetched is not None
        assert parent_fetched.status == "completed"
        assert parent_fetched.summary == "Summarized conversation."
        child_msgs = session_manager.get_messages(child.id)
        assert len(child_msgs) == len(system) + 1 + len(tail)
        assert child_msgs[1].content == "Summarized conversation."


class TestFork:
    def test_fork_creates_child(self, session_manager: SessionManager) -> None:
        msgs = make_messages()
        parent = session_manager.create(title="Original", messages=msgs)
        child = session_manager.fork(parent.id)
        assert child.fork_id == parent.id
        assert child.status == "active"
        child_msgs = session_manager.get_messages(child.id)
        assert len(child_msgs) == len(msgs)
        assert child_msgs[0].content == msgs[0].content

    def test_fork_nonexistent(self, session_manager: SessionManager) -> None:
        with pytest.raises(ValueError, match="Source session not found"):
            session_manager.fork("nonexistent")


class TestSearch:
    def test_search_content(self, session_manager: SessionManager) -> None:
        msgs = [
            SystemMessage(content="system"),
            UserMessage(content="What is the meaning of life?"),
            AssistantMessage(content="42"),
        ]
        session = session_manager.create(messages=msgs)
        results = session_manager.search("meaning")
        assert len(results) >= 1
        assert results[0].id == session.id

    def test_search_no_match(self, session_manager: SessionManager) -> None:
        msgs = [UserMessage(content="Hello world.")]
        session_manager.create(messages=msgs)
        results = session_manager.search("nonexistenttermxyz")
        assert len(results) == 0


class TestMetadata:
    def test_metadata_roundtrip(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        session.metadata = {"key": "value", "nested": {"a": 1}}
        session_manager.update(session)
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.metadata == {"key": "value", "nested": {"a": 1}}


class TestTitle:
    def test_set_title(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        session_manager.set_title(session.id, "My Title")
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.title == "My Title"


class TestResolve:
    def test_resolve_returns_state(self, session_manager: SessionManager) -> None:
        session = session_manager.create(model="gpt-4")
        sys_msg = SystemMessage(content="system")
        state = session_manager.resolve(session.id, sys_msg, context_size=128000)
        assert state is not None
        assert state.session_id == session.id
        assert state.usage.context_size == 128000
        assert any(isinstance(m, SystemMessage) for m in state.messages)

    def test_resolve_inserts_system_message(self, session_manager: SessionManager) -> None:
        msgs = [UserMessage(content="hi")]
        session = session_manager.create(messages=msgs)
        sys_msg = SystemMessage(content="You are a helpful assistant.")
        state = session_manager.resolve(session.id, sys_msg)
        assert state is not None
        assert state.messages[0].content == "You are a helpful assistant."
        assert state.messages[1].content == "hi"

    def test_resolve_follows_compression_chain(self, session_manager: SessionManager) -> None:
        parent = session_manager.create()
        child = session_manager.create_compacted_child(
            parent_id=parent.id,
            system_messages=[SystemMessage(content="sys")],
            summary_content="summary",
            tail_messages=[UserMessage(content="tail")],
        )
        sys_msg = SystemMessage(content="system")
        state = session_manager.resolve(parent.id, sys_msg)
        assert state is not None
        assert state.session_id == child.id

    def test_resolve_nonexistent(self, session_manager: SessionManager) -> None:
        sys_msg = SystemMessage(content="system")
        result = session_manager.resolve("nonexistent", sys_msg)
        assert result is None


class TestHelpers:
    def test_ts_roundtrip(self) -> None:
        from laffyhand.agent.session.manager import _ts, _from_ts
        from datetime import datetime, timezone
        dt = datetime(2026, 5, 29, 12, 30, 0, tzinfo=timezone.utc)
        ts = _ts(dt)
        assert isinstance(ts, str)
        recovered = _from_ts(ts)
        assert recovered == dt

    def test_ts_none(self) -> None:
        from laffyhand.agent.session.manager import _ts, _from_ts
        assert _ts(None) is None
        assert _from_ts(None) is None

    def test_serialize_metadata_roundtrip(self) -> None:
        from laffyhand.agent.session.manager import _serialize_metadata, _deserialize_metadata
        meta = {"key": "value", "nested": {"a": 1}}
        raw = _serialize_metadata(meta)
        assert isinstance(raw, str)
        recovered = _deserialize_metadata(raw)
        assert recovered == meta

    def test_deserialize_metadata_empty(self) -> None:
        from laffyhand.agent.session.manager import _deserialize_metadata
        assert _deserialize_metadata("") == {}

    def test_deserialize_metadata_invalid_json(self) -> None:
        from laffyhand.agent.session.manager import _deserialize_metadata
        result = _deserialize_metadata("{invalid")
        assert result == {}

    def test_message_to_record_unknown_type(self) -> None:
        from laffyhand.agent.session.manager import _message_to_record

        class FakeMsg:
            pass

        with pytest.raises(TypeError, match="Unknown message type"):
            _message_to_record("sid", FakeMsg(), 0)

    def test_record_to_message_unknown_role(self) -> None:
        from laffyhand.agent.session.manager import _record_to_message
        from laffyhand.agent.session.models import MessageRecord
        rec = MessageRecord(session_id="sid", role="unknown", content="x")
        with pytest.raises(ValueError, match="Unknown role"):
            _record_to_message(rec)

    def test_message_to_record_assistant_with_tokens(self) -> None:
        from laffyhand.agent.session.manager import _message_to_record
        from laffyhand.agent.schemas import Usage
        msg = AssistantMessage(content="Hello", tokens=Usage(input_tokens=10, output_tokens=5))
        rec = _message_to_record("sid", msg, 1)
        assert rec.role == "assistant"
        assert rec.token_count == 15

    def test_record_to_message_assistant_with_tool_calls(self) -> None:
        from laffyhand.agent.session.manager import _record_to_message
        from laffyhand.agent.session.models import MessageRecord
        rec = MessageRecord(
            session_id="sid", role="assistant", content="calling...",
            tool_args='[{"tool_call_id": "c1", "tool_name": "t", "args": "{}", "type": "tool-call"}]',
        )
        msg = _record_to_message(rec)
        assert isinstance(msg, AssistantMessage)
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].tool_call_id == "c1"


class TestAdvancedCRUD:
    def test_complete_without_summary(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        session_manager.complete(session.id)
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "completed"
        assert fetched.summary is None

    def test_complete_already_completed(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        session_manager.complete(session.id)
        session_manager.complete(session.id)  # should not raise
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "completed"

    def test_delete_nonexistent(self, session_manager: SessionManager) -> None:
        session_manager.delete("nonexistent")  # should not raise

    def test_get_messages_with_offset(self, session_manager: SessionManager) -> None:
        msgs = [UserMessage(content=f"msg{i}") for i in range(5)]
        session = session_manager.create(messages=msgs)
        loaded = session_manager.get_messages(session.id, offset=2, limit=2)
        assert len(loaded) == 2
        assert loaded[0].content == "msg2"

    def test_list_sessions_pagination(self, session_manager: SessionManager) -> None:
        for i in range(5):
            session_manager.create(model=f"model-{i}")
        page1 = session_manager.list_sessions(limit=2)
        assert len(page1) == 2
        page2 = session_manager.list_sessions(limit=2, offset=2)
        assert len(page2) == 2
        assert page1[0].id != page2[0].id

    def test_append_messages_error_nonexistent(self, session_manager: SessionManager) -> None:
        with pytest.raises(ValueError, match="Session not found"):
            session_manager.append_messages("nonexistent", [UserMessage(content="hi")])

    def test_sync_messages_error_nonexistent(self, session_manager: SessionManager) -> None:
        with pytest.raises(ValueError, match="Session not found"):
            session_manager.sync_messages("nonexistent", [])

    def test_fork_with_custom_title(self, session_manager: SessionManager) -> None:
        msgs = [UserMessage(content="hi")]
        parent = session_manager.create(title="Original", messages=msgs)
        child = session_manager.fork(parent.id, title="Forked")
        assert child.title == "Forked"
        assert child.fork_id == parent.id


class TestSchema:
    def test_has_fts5_default(self, session_manager: SessionManager) -> None:
        from laffyhand.agent.session.schema import has_fts5
        assert has_fts5(session_manager._conn) is True

    def test_create_tables_idempotent(self, session_manager: SessionManager) -> None:
        from laffyhand.agent.session.schema import create_tables
        create_tables(session_manager._conn)  # should not raise

    def test_migrate_fresh_db(self, db_path: str) -> None:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        from laffyhand.agent.session.schema import create_tables
        create_tables(conn)
        row = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()
        assert row[0] == 2
        conn.close()
