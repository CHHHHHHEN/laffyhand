from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from laffyhand.agent.session import SessionManager
from laffyhand.agent.schemas import (
    AgentState, AssistantMessage, SystemMessage, ToolCallContent,
    ToolMessage, UserMessage, SessionUsage,
)


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def manager(db_path: str) -> SessionManager:
    return SessionManager(db_path)


def make_messages() -> list:
    return [
        SystemMessage(content="You are a helpful assistant."),
        UserMessage(content="Hello!"),
        AssistantMessage(content="Hi there!", tokens=None),
        UserMessage(content="What is Python?"),
        AssistantMessage(content="Python is a programming language."),
    ]


class TestSessionCRUD:
    def test_create(self, manager: SessionManager) -> None:
        session = manager.create(cwd="/test", model="gpt-4")
        assert session.id != ""
        assert session.status == "active"
        assert session.cwd == "/test"
        assert session.model == "gpt-4"
        assert session.turn_count == 0

    def test_get(self, manager: SessionManager) -> None:
        created = manager.create()
        fetched = manager.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_not_found(self, manager: SessionManager) -> None:
        assert manager.get("nonexistent") is None

    def test_get_active(self, manager: SessionManager) -> None:
        s1 = manager.create(model="gpt-4")
        s2 = manager.create(model="gpt-5")
        active = manager.get_active()
        assert active is not None
        assert active.id == s2.id

    def test_list_sessions(self, manager: SessionManager) -> None:
        manager.create()
        manager.create()
        all_sessions = manager.list_sessions()
        assert len(all_sessions) == 2

    def test_list_with_status_filter(self, manager: SessionManager) -> None:
        s1 = manager.create()
        s2 = manager.create()
        manager.complete(s2.id)
        active = manager.list_sessions(status="active")
        assert len(active) == 1
        assert active[0].id == s1.id

    def test_complete(self, manager: SessionManager) -> None:
        session = manager.create()
        manager.complete(session.id, summary="Done!")
        fetched = manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "completed"
        assert fetched.summary == "Done!"
        assert fetched.ended_at is not None

    def test_archive(self, manager: SessionManager) -> None:
        session = manager.create()
        manager.archive(session.id)
        fetched = manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "archived"

    def test_delete(self, manager: SessionManager) -> None:
        session = manager.create()
        manager.delete(session.id)
        assert manager.get(session.id) is None

    def test_update(self, manager: SessionManager) -> None:
        session = manager.create(title="old")
        session.title = "new"
        manager.update(session)
        fetched = manager.get(session.id)
        assert fetched is not None
        assert fetched.title == "new"


class TestMessages:
    def test_create_with_messages(self, manager: SessionManager) -> None:
        msgs = make_messages()
        session = manager.create(messages=msgs)
        assert session.message_count == len(msgs)

    def test_append_messages(self, manager: SessionManager) -> None:
        session = manager.create()
        msgs = make_messages()
        count = manager.append_messages(session.id, msgs)
        assert count == len(msgs)

    def test_append_messages_incremental(self, manager: SessionManager) -> None:
        session = manager.create()
        first = [
            SystemMessage(content="system"),
            UserMessage(content="hi"),
        ]
        manager.append_messages(session.id, first)
        second = [AssistantMessage(content="hello")]
        manager.append_messages(session.id, first + second)
        loaded = manager.get_messages(session.id)
        assert len(loaded) == 3

    def test_get_messages(self, manager: SessionManager) -> None:
        msgs = make_messages()
        session = manager.create(messages=msgs)
        loaded = manager.get_messages(session.id)
        assert len(loaded) == len(msgs)
        assert isinstance(loaded[0], SystemMessage)
        assert isinstance(loaded[1], UserMessage)
        assert loaded[1].content == "Hello!"

    def test_get_messages_with_limit(self, manager: SessionManager) -> None:
        msgs = make_messages()
        session = manager.create(messages=msgs)
        loaded = manager.get_messages(session.id, limit=2)
        assert len(loaded) == 2

    def test_sync_messages(self, manager: SessionManager) -> None:
        msgs = make_messages()
        session = manager.create(messages=msgs)
        new_msgs = [SystemMessage(content="New system.")]
        manager.sync_messages(session.id, new_msgs)
        loaded = manager.get_messages(session.id)
        assert len(loaded) == 1
        assert loaded[0].content == "New system."

    def test_assistant_message_with_tool_calls(self, manager: SessionManager) -> None:
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
        session = manager.create(messages=msgs)
        loaded = manager.get_messages(session.id)
        assert len(loaded) == 2
        assert isinstance(loaded[0], AssistantMessage)
        assert loaded[0].tool_calls is not None
        assert len(loaded[0].tool_calls) == 1
        assert loaded[0].tool_calls[0].tool_call_id == "call_1"
        assert isinstance(loaded[1], ToolMessage)
        assert loaded[1].content == "Result!"


class TestStatePersistence:
    def test_save_and_load_state(self, manager: SessionManager) -> None:
        msgs = make_messages()
        session = manager.create()
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
        manager.save_state(session.id, state)
        loaded = manager.load_state(session.id)
        assert loaded is not None
        assert loaded.turn_count == 3
        assert loaded.step == 5
        assert loaded.session_id == session.id
        assert loaded.usage.total_input == 100
        assert loaded.usage.total_output == 50
        assert len(loaded.messages) == len(msgs)

    def test_load_nonexistent(self, manager: SessionManager) -> None:
        assert manager.load_state("nonexistent") is None


class TestCompactionChain:
    def test_chain_from_root(self, manager: SessionManager) -> None:
        root = manager.create()
        child = manager.create(parent_id=root.id)
        grandchild = manager.create(parent_id=child.id)
        ids = manager.chain(grandchild.id)
        assert ids == [grandchild.id, child.id, root.id]

    def test_compression_tip(self, manager: SessionManager) -> None:
        root = manager.create()
        child = manager.create(parent_id=root.id)
        grandchild = manager.create(parent_id=child.id)
        tip = manager.get_compression_tip(root.id)
        assert tip == grandchild.id

    def test_compression_tip_no_children(self, manager: SessionManager) -> None:
        session = manager.create()
        tip = manager.get_compression_tip(session.id)
        assert tip == session.id

    def test_compression_tip_skips_completed(self, manager: SessionManager) -> None:
        root = manager.create()
        child = manager.create(parent_id=root.id)
        manager.complete(child.id)
        tip = manager.get_compression_tip(root.id)
        assert tip == root.id

    def test_compact_creates_child(self, manager: SessionManager) -> None:
        msgs = make_messages()
        parent = manager.create(messages=msgs)
        system = [msgs[0]]
        tail = msgs[2:]
        child = manager.compact(
            session_id=parent.id,
            system_messages=system,
            summary_content="Summarized conversation.",
            tail_messages=tail,
        )
        assert child.parent_id == parent.id
        assert child.status == "active"
        parent_fetched = manager.get(parent.id)
        assert parent_fetched is not None
        assert parent_fetched.status == "completed"
        assert parent_fetched.summary == "Summarized conversation."
        child_msgs = manager.get_messages(child.id)
        assert len(child_msgs) == len(system) + 1 + len(tail)
        assert child_msgs[1].content == "Summarized conversation."


class TestFork:
    def test_fork_creates_child(self, manager: SessionManager) -> None:
        msgs = make_messages()
        parent = manager.create(title="Original", messages=msgs)
        child = manager.fork(parent.id)
        assert child.fork_id == parent.id
        assert child.status == "active"
        child_msgs = manager.get_messages(child.id)
        assert len(child_msgs) == len(msgs)
        assert child_msgs[0].content == msgs[0].content

    def test_fork_nonexistent(self, manager: SessionManager) -> None:
        with pytest.raises(ValueError, match="Source session not found"):
            manager.fork("nonexistent")


class TestSearch:
    def test_search_content(self, manager: SessionManager) -> None:
        msgs = [
            SystemMessage(content="system"),
            UserMessage(content="What is the meaning of life?"),
            AssistantMessage(content="42"),
        ]
        session = manager.create(messages=msgs)
        results = manager.search("meaning")
        assert len(results) >= 1
        assert results[0].id == session.id

    def test_search_no_match(self, manager: SessionManager) -> None:
        msgs = [UserMessage(content="Hello world.")]
        manager.create(messages=msgs)
        results = manager.search("nonexistenttermxyz")
        assert len(results) == 0


class TestMetadata:
    def test_metadata_roundtrip(self, manager: SessionManager) -> None:
        session = manager.create()
        session.metadata = {"key": "value", "nested": {"a": 1}}
        manager.update(session)
        fetched = manager.get(session.id)
        assert fetched is not None
        assert fetched.metadata == {"key": "value", "nested": {"a": 1}}


class TestTitle:
    def test_set_title(self, manager: SessionManager) -> None:
        session = manager.create()
        manager.set_title(session.id, "My Title")
        fetched = manager.get(session.id)
        assert fetched is not None
        assert fetched.title == "My Title"
