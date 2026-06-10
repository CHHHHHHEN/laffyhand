from __future__ import annotations

import os
import tempfile

import pytest

from laffyhand.core.llm.specs.models import AssistantMessage, SystemMessage, UserMessage
from laffyhand.core.session import SessionManager
from laffyhand.core.models import (
    AgentState,
    SessionUsage,
)


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.mark.anyio
async def test_session_save_and_load(db_path):
    sm = SessionManager(db_path)
    session = sm.create(title="test-session", cwd="/tmp", model="gpt-4")
    assert session.id is not None

    messages = [
        SystemMessage(content="You are helpful."),
        UserMessage(content="Hello"),
        AssistantMessage(content="Hi there!"),
    ]
    sm.store_messages(session.id, messages)

    loaded = sm.get(session.id)
    assert loaded is not None
    assert loaded.title == "test-session"
    assert loaded.cwd == "/tmp"
    assert loaded.model == "gpt-4"
    assert loaded.message_count == 3

    loaded_messages = sm.get_messages(session.id)
    assert len(loaded_messages) == 3
    assert loaded_messages[0].content == "You are helpful."
    assert loaded_messages[1].content == "Hello"
    assert loaded_messages[2].content == "Hi there!"

    sm.close()


@pytest.mark.anyio
async def test_session_state_persistence(db_path):
    sm = SessionManager(db_path)
    session = sm.create(title="state-test")

    state = AgentState(
        messages=[
            SystemMessage(content="sys"),
            UserMessage(content="user1"),
            AssistantMessage(content="asst1"),
        ],
        turn_count=1,
        step=3,
        session_id=session.id,
        usage=SessionUsage(
            total_input=100,
            total_output=50,
            total_reasoning=10,
            total_cache_read=5,
        ),
    )
    sm.save_state(session.id, state)

    loaded = sm.load_state(session.id)
    assert loaded is not None
    assert loaded.turn_count == 1
    assert loaded.step == 3
    assert loaded.usage.total_input == 100
    assert loaded.usage.total_output == 50
    assert loaded.usage.total_reasoning == 10
    assert loaded.usage.total_cache_read == 5
    assert len(loaded.messages) == 3

    sm.close()


@pytest.mark.anyio
async def test_session_compaction_chain_persistence(db_path):
    sm = SessionManager(db_path)
    parent = sm.create(title="parent-session")

    messages = [
        SystemMessage(content="sys"),
        UserMessage(content="Hello"),
        AssistantMessage(content="World"),
    ]
    sm.store_messages(parent.id, messages)

    child = sm.create_compacted_child(
        parent_id=parent.id,
        system_messages=[SystemMessage(content="sys")],
        summary_content="User said hello",
        tail_messages=[UserMessage(content="Hello"), AssistantMessage(content="World")],
    )
    assert child.id != parent.id
    assert child.parent_id == parent.id

    parent_after = sm.get(parent.id)
    assert parent_after is not None
    assert parent_after.status == "archived"

    child_loaded = sm.get(child.id)
    assert child_loaded is not None
    assert child_loaded.status == "active"

    # Compression chain: resolve should walk to child
    tip = sm.get_compression_tip(parent.id)
    assert tip == child.id

    # Chain should include both
    chain = sm.chain(child.id)
    assert parent.id in chain
    assert child.id in chain

    sm.close()


@pytest.mark.anyio
async def test_session_persistence_after_crash(db_path):
    """Simulate saving state and verify it survives a 'restart' (new SessionManager)."""
    sm1 = SessionManager(db_path)
    session = sm1.create(title="crash-test")

    state = AgentState(
        messages=[
            SystemMessage(content="sys"),
            UserMessage(content="persist me"),
        ],
        turn_count=1,
        step=5,
        session_id=session.id,
    )
    sm1.save_state(session.id, state)
    sm1.close()

    sm2 = SessionManager(db_path)
    loaded_state = sm2.load_state(session.id)
    assert loaded_state is not None
    assert loaded_state.turn_count == 1
    assert loaded_state.step == 5
    assert len(loaded_state.messages) == 2
    assert loaded_state.messages[1].content == "persist me"

    loaded_session = sm2.get(session.id)
    assert loaded_session is not None
    assert loaded_session.title == "crash-test"
    sm2.close()
