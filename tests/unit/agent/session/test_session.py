from __future__ import annotations

import pytest

from laffyhand.agent.llm.specs.models import AssistantMessage, SystemMessage, ToolMessage, UserMessage
from laffyhand.agent.session import SessionManager
from laffyhand.agent.llm.specs.models import ToolCallContent
from laffyhand.agent.schemas import (
    AgentState,
    SessionUsage,
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

    def test_delete_with_child_sessions(self, session_manager: SessionManager) -> None:
        parent = session_manager.create()
        child1 = session_manager.create(parent_id=parent.id)
        child2 = session_manager.create(parent_id=parent.id)
        session_manager.delete(parent.id)
        assert session_manager.get(parent.id) is None
        c1 = session_manager.get(child1.id)
        assert c1 is not None
        assert c1.parent_id is None
        c2 = session_manager.get(child2.id)
        assert c2 is not None
        assert c2.parent_id is None

    def test_delete_with_forked_sessions(self, session_manager: SessionManager) -> None:
        orig = session_manager.create()
        fork = session_manager.create(fork_id=orig.id)
        session_manager.delete(orig.id)
        assert session_manager.get(orig.id) is None
        f = session_manager.get(fork.id)
        assert f is not None
        assert f.fork_id is None

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

    def test_store_messages(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        msgs = make_messages()
        count = session_manager.store_messages(session.id, msgs)
        assert count == len(msgs)

    def test_store_messages_incremental(self, session_manager: SessionManager) -> None:
        session = session_manager.create()
        first = [
            SystemMessage(content="system"),
            UserMessage(content="hi"),
        ]
        session_manager.store_messages(session.id, first)
        second = [AssistantMessage(content="hello")]
        session_manager.store_messages(session.id, second)
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

    def test_assistant_message_with_tool_calls(
        self, session_manager: SessionManager
    ) -> None:
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

    def test_save_state_does_not_duplicate_last_message(self, session_manager: SessionManager) -> None:
        """save_state() must not re-store messages already in DB.

        Regression test: when state.messages contains a SystemMessage at [0]
        that was stored via store_messages(), save_state() should correctly
        compare counts and avoid inserting the last message a second time.
        """
        # Simulate the flow:
        # 1. _prepare_chat stores [SystemMessage, UserMessage] (first persist)
        session = session_manager.create()
        sys_msg = SystemMessage(content="You are a helpful assistant.")
        user_msg1 = UserMessage(content="Hello!")
        session_manager.store_messages(session.id, [sys_msg, user_msg1])

        # 2. Agent loop stores AssistantMessage
        assist_msg = AssistantMessage(content="Hi there!")
        session_manager.store_messages(session.id, [assist_msg])

        # 3. Now simulate shutdown: state.messages has the same 3 messages
        state = AgentState(
            messages=[sys_msg, user_msg1, assist_msg],
            turn_count=1,
            step=1,
            session_id=session.id,
        )
        # Before the fix, save_state would insert AssistantMessage again here
        session_manager.save_state(session.id, state)

        # 4. Verify: DB should still have exactly 3 messages (no duplicates)
        loaded = session_manager.get_messages(session.id)
        assert len(loaded) == 3, f"Expected 3 messages, got {len(loaded)}"
        assert isinstance(loaded[0], SystemMessage)
        assert loaded[0].content == "You are a helpful assistant."
        assert isinstance(loaded[1], UserMessage)
        assert loaded[1].content == "Hello!"
        assert isinstance(loaded[2], AssistantMessage)
        assert loaded[2].content == "Hi there!"

    def test_save_state_shutdown_does_not_duplicate(self, session_manager: SessionManager) -> None:
        """Simulate the full shutdown scenario that caused the duplication bug.

        After a session's messages are all stored via store_messages(),
        calling save_state() during shutdown must NOT insert any duplicates
        even if state.messages has the same content.
        """
        session = session_manager.create()
        msgs = [
            SystemMessage(content="system"),
            UserMessage(content="first"),
            AssistantMessage(content="response"),
        ]
        # Store all messages via store_messages (as the agent loop does)
        session_manager.store_messages(session.id, msgs)

        # Verify initial state
        assert session_manager.get_message_count(session.id) == 3

        # Shutdown: save the exact same state
        state = AgentState(
            messages=list(msgs),
            turn_count=1,
            step=1,
            session_id=session.id,
            usage=SessionUsage(
                total_input=100,
                total_output=50,
            ),
        )
        session_manager.save_state(session.id, state)

        # Verify no duplicates
        loaded = session_manager.get_messages(session.id)
        assert len(loaded) == 3, f"Expected 3 messages, got {len(loaded)}"
        contents = [m.content for m in loaded]
        assert contents == ["system", "first", "response"]

    def test_save_state_with_partial_new_messages(self, session_manager: SessionManager) -> None:
        """save_state() should persist messages that were added in memory
        but not yet in DB (e.g., mid-turn shutdown)."""
        session = session_manager.create()
        # Only store first two messages in DB
        session_manager.store_messages(session.id, [
            SystemMessage(content="system"),
            UserMessage(content="Hello!"),
        ])
        # State has an additional AssistantMessage not yet in DB
        state = AgentState(
            messages=[
                SystemMessage(content="system"),
                UserMessage(content="Hello!"),
                AssistantMessage(content="Hi there!"),
            ],
            turn_count=1,
            step=1,
            session_id=session.id,
        )
        session_manager.save_state(session.id, state)
        loaded = session_manager.get_messages(session.id)
        assert len(loaded) == 3, f"Expected 3 messages, got {len(loaded)}"
        assert loaded[2].content == "Hi there!"


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

    def test_compression_tip_skips_completed(
        self, session_manager: SessionManager
    ) -> None:
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


class TestLoadCompressedState:
    def test_load_compressed_state_returns_state(self, session_manager: SessionManager) -> None:
        session = session_manager.create(model="gpt-4")
        sys_msg = SystemMessage(content="system")
        state = session_manager.load_compressed_state(session.id, sys_msg, context_size=128000)
        assert state is not None
        assert state.session_id == session.id
        assert state.usage.context_size == 128000
        assert any(isinstance(m, SystemMessage) for m in state.messages)

    def test_load_compressed_state_inserts_system_message(
        self, session_manager: SessionManager
    ) -> None:
        msgs = [UserMessage(content="hi")]
        session = session_manager.create(messages=msgs)
        sys_msg = SystemMessage(content="You are a helpful assistant.")
        state = session_manager.load_compressed_state(session.id, sys_msg)
        assert state is not None
        assert state.messages[0].content == "You are a helpful assistant."
        assert state.messages[1].content == "hi"

    def test_load_compressed_state_follows_compression_chain(
        self, session_manager: SessionManager
    ) -> None:
        parent = session_manager.create()
        child = session_manager.create_compacted_child(
            parent_id=parent.id,
            system_messages=[SystemMessage(content="sys")],
            summary_content="summary",
            tail_messages=[UserMessage(content="tail")],
        )
        sys_msg = SystemMessage(content="system")
        state = session_manager.load_compressed_state(parent.id, sys_msg)
        assert state is not None
        assert state.session_id == child.id

    def test_load_compressed_state_nonexistent(self, session_manager: SessionManager) -> None:
        sys_msg = SystemMessage(content="system")
        result = session_manager.load_compressed_state("nonexistent", sys_msg)
        assert result is None


class TestHelpers:
    def test_ts_roundtrip(self) -> None:
        from laffyhand.agent.db.repository.common import _ts, _from_ts
        from datetime import datetime, timezone

        dt = datetime(2026, 5, 29, 12, 30, 0, tzinfo=timezone.utc)
        ts = _ts(dt)
        assert isinstance(ts, str)
        recovered = _from_ts(ts)
        assert recovered == dt

    def test_ts_none(self) -> None:
        from laffyhand.agent.db.repository.common import _ts, _from_ts

        assert _ts(None) is None
        assert _from_ts(None) is None

    def test_serialize_metadata_roundtrip(self) -> None:
        from laffyhand.agent.db.repository.common import (
            _serialize_metadata,
            _deserialize_metadata,
        )

        meta = {"key": "value", "nested": {"a": 1}}
        raw = _serialize_metadata(meta)
        assert isinstance(raw, str)
        recovered = _deserialize_metadata(raw)
        assert recovered == meta

    def test_deserialize_metadata_empty(self) -> None:
        from laffyhand.agent.db.repository.common import _deserialize_metadata

        assert _deserialize_metadata("") == {}

    def test_deserialize_metadata_invalid_json(self) -> None:
        from laffyhand.agent.db.repository.common import _deserialize_metadata

        result = _deserialize_metadata("{invalid")
        assert result == {}

    def test_message_to_session_message_unknown_type(self) -> None:
        from laffyhand.agent.session.converters import message_to_session_message

        class FakeMsg:
            pass

        with pytest.raises(TypeError, match="Unknown message type"):
            message_to_session_message(FakeMsg(), "sid")

    def test_message_to_session_message_assistant_with_tokens(self) -> None:
        from laffyhand.agent.session.converters import message_to_session_message
        from laffyhand.agent.llm.specs.models import Usage

        msg = AssistantMessage(
            content="Hello", tokens=Usage(input_tokens=10, output_tokens=5, reasoning_tokens=3)
        )
        sm = message_to_session_message(msg, "sid")
        assert sm.type == "assistant"
        d = sm.data
        assert d.tokens is not None
        assert d.tokens.input == 10
        assert d.tokens.output == 5
        assert d.tokens.reasoning == 3

    def test_session_message_to_message_roundtrip(self) -> None:
        from laffyhand.agent.session.converters import (
            message_to_session_message, session_message_to_message,
        )
        from laffyhand.agent.llm.specs.models import Usage

        msg = AssistantMessage(
            content="Hello", reasoning="thinking",
            tokens=Usage(input_tokens=10, output_tokens=5, reasoning_tokens=3, cache_read_tokens=2, cache_write_tokens=1),
        )
        sm = message_to_session_message(msg, "sid")
        restored = session_message_to_message(sm)
        assert isinstance(restored, AssistantMessage)
        assert restored.content == "Hello"
        assert restored.reasoning == "thinking"
        assert restored.tokens is not None
        assert restored.tokens.input_tokens == 10
        assert restored.tokens.cache_write_tokens == 1

    def test_shell_message_preserves_is_error(self) -> None:
        from laffyhand.agent.session.converters import (
            message_to_session_message, session_message_to_message,
        )

        msg = ToolMessage(tool_call_id="c1", content="error", is_error=True)
        sm = message_to_session_message(msg, "sid")
        restored = session_message_to_message(sm)
        assert isinstance(restored, ToolMessage)
        assert restored.is_error is True


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

    def test_store_messages_creates_session_if_not_exists(
        self, session_manager: SessionManager
    ) -> None:
        count = session_manager.store_messages("nonexistent", [UserMessage(content="hi")])
        assert count == 1
        session = session_manager.get("nonexistent")
        assert session is not None
        assert session.message_count == 1

    def test_sync_messages_creates_session_if_not_exists(
        self, session_manager: SessionManager
    ) -> None:
        session_manager.sync_messages("nonexistent", [UserMessage(content="hi")])
        session = session_manager.get("nonexistent")
        assert session is not None
        messages = session_manager.get_messages("nonexistent")
        assert len(messages) == 1

    def test_fork_with_custom_title(self, session_manager: SessionManager) -> None:
        msgs = [UserMessage(content="hi")]
        parent = session_manager.create(title="Original", messages=msgs)
        child = session_manager.fork(parent.id, title="Forked")
        assert child.title == "Forked"
        assert child.fork_id == parent.id


class TestSchema:
    def test_create_tables_idempotent(self, session_manager: SessionManager) -> None:
        from laffyhand.agent.db.schema import create_tables

        create_tables(session_manager._conn)  # should not raise

    def test_migrate_fresh_db(self, db_path: str) -> None:
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        from laffyhand.agent.db.schema import create_tables

        create_tables(conn)
        row = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()
        assert row[0] >= 4
        conn.close()
