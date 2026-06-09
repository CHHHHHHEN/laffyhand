from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from laffyhand.core.context import ContextManager, PreparedContext
from laffyhand.core.llm.specs.models import (
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from laffyhand.core.models import AgentState, CompactionConfig, SessionID, SessionUsage


def _make_state(
    messages: list[Message] | None = None,
    context_size: int = 128_000,
    curr_usage: int = 0,
) -> AgentState:
    return AgentState(
        messages=messages or [],
        session_id=SessionID("sess-1"),
        usage=SessionUsage(
            context_size=context_size,
            curr_context_usage=curr_usage,
        ),
    )


class TestPreparedContext:
    def test_default_values(self) -> None:
        ctx = PreparedContext(messages=[])
        assert ctx.messages == []
        assert ctx.compacted is False
        assert ctx.session_id is None

    def test_custom_values(self) -> None:
        msgs = [UserMessage(content="hi")]
        ctx = PreparedContext(messages=msgs, compacted=True, session_id="sess-2")
        assert ctx.messages == msgs
        assert ctx.compacted is True
        assert ctx.session_id == "sess-2"


class TestContextManagerPrepare:
    @pytest.mark.anyio
    async def test_no_context_size_returns_messages_as_is(self) -> None:
        llm = MagicMock()
        cm = ContextManager(llm=llm, config=CompactionConfig())
        state = _make_state(context_size=0, messages=[UserMessage(content="hi")])

        ctx = await cm.prepare(state)
        assert ctx.compacted is False
        assert len(ctx.messages) == 1

    @pytest.mark.anyio
    async def test_no_overflow_passes_through(self) -> None:
        llm = MagicMock()
        cm = ContextManager(llm=llm, config=CompactionConfig())
        state = _make_state(curr_usage=10_000, messages=[UserMessage(content="hi")])

        ctx = await cm.prepare(state)
        assert ctx.compacted is False
        assert len(ctx.messages) == 1

    @pytest.mark.anyio
    async def test_prune_applied_when_enabled(self) -> None:
        llm = MagicMock()
        config = CompactionConfig(prune=True)
        cm = ContextManager(llm=llm, config=config)

        big = "x" * (config.prune_protect * 4 + 5)
        msgs = [
            SystemMessage(content="sys"),
            ToolMessage(tool_call_id="c1", content=big),
        ]
        state = _make_state(
            curr_usage=128_000,
            messages=list(msgs),
        )

        ctx = await cm.prepare(state)
        assert ctx.messages[1].content.startswith("[Old tool result content cleared:")

    @pytest.mark.anyio
    async def test_no_prune_when_disabled(self) -> None:
        llm = MagicMock()
        cm = ContextManager(llm=llm, config=CompactionConfig(prune=False))

        msgs = [
            ToolMessage(tool_call_id="c1", content="original"),
        ]
        state = _make_state(messages=list(msgs))

        ctx = await cm.prepare(state)
        assert ctx.messages[0].content == "original"

    @pytest.mark.anyio
    async def test_compaction_without_session_manager_returns_uncompacted(
        self,
    ) -> None:
        llm = AsyncMock()
        cm = ContextManager(
            llm=llm,
            config=CompactionConfig(),
            session_manager=None,
        )
        state = _make_state(
            curr_usage=120_000,
            messages=[
                UserMessage(content="a" * 1000),
                UserMessage(content="b" * 1000),
                UserMessage(content="c" * 1000),
            ],
        )
        # With high usage and no session_manager, compact should be skipped
        ctx = await cm.prepare(state)
        assert ctx.compacted is False

    @pytest.mark.anyio
    async def test_prepare_respects_step_flag(self) -> None:
        llm = AsyncMock()
        session_manager = MagicMock()
        session_manager.create_compacted_child = MagicMock()

        cm = ContextManager(
            llm=llm,
            config=CompactionConfig(),
            session_manager=session_manager,
        )
        # Simulate that we already compacted this step
        cm._compacted_this_step = True

        state = _make_state(
            curr_usage=120_000,
            messages=[
                UserMessage(content="x" * 1000),
                UserMessage(content="y" * 1000),
                UserMessage(content="z" * 1000),
            ],
        )
        ctx = await cm.prepare(state)
        # Should not try to compact again this step
        assert ctx.compacted is False


class TestContextManagerPostTurn:
    @pytest.mark.anyio
    async def test_no_overflow_returns_false(self) -> None:
        llm = MagicMock()
        cm = ContextManager(llm=llm, config=CompactionConfig())
        state = _make_state(curr_usage=10_000)

        result = await cm.post_turn(state)
        assert result is False

    @pytest.mark.anyio
    async def test_compacted_this_step_skips(self) -> None:
        llm = MagicMock()
        cm = ContextManager(llm=llm, config=CompactionConfig())
        cm._compacted_this_step = True

        state = _make_state(curr_usage=120_000)
        result = await cm.post_turn(state)
        assert result is False

    @pytest.mark.anyio
    async def test_compact_with_session_manager_and_auto_continue(
        self,
    ) -> None:
        llm = AsyncMock()
        session_manager = MagicMock()
        child = MagicMock()
        child.id = "sess-2"
        session_manager.create_compacted_child = MagicMock(return_value=child)

        cm = ContextManager(
            llm=llm,
            config=CompactionConfig(auto_continue=True),
            session_manager=session_manager,
        )

        # Mock compact_with_chain via the llm's _summarize path
        # We need enough messages to trigger overflow + compact
        state = _make_state(
            curr_usage=120_000,
            messages=[
                UserMessage(content="x" * 1000),
                UserMessage(content="y" * 1000),
                UserMessage(content="z" * 1000),
            ],
        )

        result = await cm.post_turn(state)
        # Without a proper compact mock, this should fail and return False
        # since compact_with_chain will fail without an LLM returning a summary
        assert result is False


class TestContextManagerFullFlow:
    @pytest.mark.anyio
    async def test_prepare_then_post_turn(self) -> None:
        llm = AsyncMock()
        cm = ContextManager(
            llm=llm,
            config=CompactionConfig(auto_continue=False),
            session_manager=None,
        )
        state = _make_state(
            curr_usage=10_000,
            messages=[UserMessage(content="hello")],
        )

        ctx = await cm.prepare(state)
        assert ctx.compacted is False
        assert len(ctx.messages) == 1

        result = await cm.post_turn(state)
        assert result is False

    def test_reset_step_flag(self) -> None:
        llm = MagicMock()
        cm = ContextManager(llm=llm, config=CompactionConfig())
        cm._compacted_this_step = True
        cm.reset_step_flag()
        assert cm._compacted_this_step is False
