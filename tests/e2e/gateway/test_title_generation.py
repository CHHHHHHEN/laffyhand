from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from laffyhand.core.domain.messages import UserMessage
from laffyhand.core.runtime import AgentRuntime
from laffyhand.llm.specs.models import (
    StreamText,
    StreamFinish,
)
from laffyhand.core.models import (
    AgentState,
    SessionUsage,
)


class FakeLLM:
    def __init__(self, title: str = "Auto Title") -> None:
        self.title = title

    async def stream(self, messages, tools=None):
        yield StreamText(delta=self.title)
        yield StreamFinish(finish_reason="stop")


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def runtime(runtime_config, fake_llm) -> AgentRuntime:
    rt = AgentRuntime(
        config=runtime_config,
        llm=fake_llm,
        mcp_service=MagicMock(),
    )
    rt.title_config.mode = "auto"
    rt._llm_for_session = MagicMock(return_value=fake_llm)
    rt.title_service._llm_provider = MagicMock(return_value=fake_llm)
    yield rt
    # Close the internal SessionManager so db_path can unlink the temp file
    # on Windows (open SQLite files cannot be deleted).
    rt.session_manager.close()


@pytest.mark.anyio
async def test_do_generate_title_persists_to_db(
    runtime: AgentRuntime,
    fake_llm,
) -> None:
    """_do_generate_title generates and persists a title via real generate_title()."""
    sm = runtime.session_manager
    session = sm.create(messages=[UserMessage(content="Hello world")])
    runtime.state = AgentState(
        messages=[UserMessage(content="Hello world")],
        session_id=session.id,
        usage=SessionUsage(context_size=128000),
    )

    await runtime._do_generate_title(session.id)

    fetched = sm.get(session.id)
    assert fetched is not None
    assert fetched.title == "Auto Title"


@pytest.mark.anyio
async def test_auto_mode_creates_title_after_background_task(
    runtime: AgentRuntime,
) -> None:
    """_schedule_title_generation fires a background task that sets the title."""
    sm = runtime.session_manager
    session = sm.create(messages=[UserMessage(content="Hello world")])
    runtime.state = AgentState(
        messages=[UserMessage(content="Hello world")],
        session_id=session.id,
        usage=SessionUsage(context_size=128000),
    )

    runtime._schedule_title_generation(session.id, "auto")
    # Give the background task time to complete
    import asyncio

    await asyncio.sleep(0.1)

    fetched = sm.get(session.id)
    assert fetched is not None
    assert fetched.title != ""


@pytest.mark.anyio
async def test_existing_title_not_overwritten(
    runtime: AgentRuntime,
) -> None:
    """Sessions with an existing title are skipped by _schedule_title_generation."""
    sm = runtime.session_manager
    session = sm.create(
        title="Manual Title",
        messages=[UserMessage(content="Hello world")],
    )
    runtime.state = AgentState(
        messages=[UserMessage(content="Hello world")],
        session_id=session.id,
        usage=SessionUsage(context_size=128000),
    )

    runtime._schedule_title_generation(session.id, "auto")
    import asyncio

    await asyncio.sleep(0.1)

    fetched = sm.get(session.id)
    assert fetched is not None
    assert fetched.title == "Manual Title"


@pytest.mark.anyio
async def test_no_user_messages_no_title(
    runtime: AgentRuntime,
) -> None:
    """_do_generate_title does nothing when there are no user messages."""
    sm = runtime.session_manager
    session = sm.create()
    runtime.state = AgentState(
        messages=[],
        session_id=session.id,
        usage=SessionUsage(context_size=128000),
    )

    await runtime._do_generate_title(session.id)

    fetched = sm.get(session.id)
    assert fetched is not None
    assert fetched.title == ""
