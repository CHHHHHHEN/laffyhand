from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from laffyhand.agent.llm.specs.models import AssistantMessage, SystemMessage, UserMessage
from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.schemas import (
    AgentState,
    CompactionConfig,
    StreamText,
    StreamFinish,
    StreamError,
    SessionUsage,
)


# ── generate_title ───────────────────────────────────────────


class TestGenerateTitle:
    @pytest.mark.anyio
    async def test_mode_off_returns_none(self, session_manager: SessionManager) -> None:
        from laffyhand.agent.title import generate_title

        config = TitleConfig(mode="off")
        result = await generate_title(session_manager, "sid", MagicMock(), config)
        assert result is None

    @pytest.mark.anyio
    async def test_no_user_messages_returns_none(
        self, session_manager: SessionManager
    ) -> None:
        from laffyhand.agent.title import generate_title

        session = session_manager.create(messages=[SystemMessage(content="sys")])
        config = TitleConfig(mode="auto")
        result = await generate_title(session_manager, session.id, MagicMock(), config)
        assert result is None

    @pytest.mark.anyio
    async def test_generates_title(self, session_manager: SessionManager) -> None:
        from laffyhand.agent.title import generate_title

        async def mock_stream(messages, **kwargs):
            yield StreamText(delta="My Title")
            yield StreamFinish(finish_reason="stop")

        llm = MagicMock()
        llm.stream = mock_stream
        msgs = [UserMessage(content="Hello world")]
        session = session_manager.create(messages=msgs)
        config = TitleConfig(mode="auto")
        result = await generate_title(session_manager, session.id, llm, config)
        assert result == "My Title"
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.title == "My Title"

    @pytest.mark.anyio
    async def test_stream_error_returns_none(
        self, session_manager: SessionManager
    ) -> None:
        from laffyhand.agent.title import generate_title

        async def mock_stream(messages, **kwargs):
            yield StreamError(error="API error")

        llm = MagicMock()
        llm.stream = mock_stream
        msgs = [UserMessage(content="Hello")]
        session = session_manager.create(messages=msgs)
        config = TitleConfig(mode="auto")
        result = await generate_title(session_manager, session.id, llm, config)
        assert result is None

    @pytest.mark.anyio
    async def test_empty_title_returns_none(
        self, session_manager: SessionManager
    ) -> None:
        from laffyhand.agent.title import generate_title

        async def mock_stream(messages, **kwargs):
            yield StreamText(delta="")
            yield StreamFinish(finish_reason="stop")

        llm = MagicMock()
        llm.stream = mock_stream
        msgs = [UserMessage(content="Hello")]
        session = session_manager.create(messages=msgs)
        config = TitleConfig(mode="auto")
        result = await generate_title(session_manager, session.id, llm, config)
        assert result is None


# ── _compact_on_overflow ─────────────────────────────────────


class TestCompactOnOverflow:
    @pytest.mark.anyio
    async def test_no_overflow_returns_false(
        self, session_manager: SessionManager
    ) -> None:
        from laffyhand.agent.loop import _compact_on_overflow

        state = AgentState(
            messages=[UserMessage(content="hi")],
            usage=SessionUsage(context_size=128000),
        )
        config = CompactionConfig()
        result = await _compact_on_overflow(state, MagicMock(), config, session_manager)
        assert result is False

    @pytest.mark.anyio
    async def test_overflow_with_session_manager(
        self, session_manager: SessionManager
    ) -> None:
        from laffyhand.agent.loop import _compact_on_overflow

        async def mock_stream(messages, **kwargs):
            yield StreamText(delta="Summary of conversation.")
            yield StreamFinish(finish_reason="stop")

        llm = MagicMock()
        llm.stream = mock_stream

        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="Hello! " * 5000),
            AssistantMessage(content="Hi! " * 5000),
            UserMessage(content="More text. " * 5000),
            AssistantMessage(content="Response. " * 5000),
        ]
        session = session_manager.create(messages=msgs)
        state = AgentState(
            messages=msgs,
            turn_count=2,
            step=0,
            session_id=session.id,
            usage=SessionUsage(context_size=2000),
        )
        config = CompactionConfig(tail_turns=1)
        result = await _compact_on_overflow(state, llm, config, session_manager)
        assert result is True
        assert state.session_id != session.id
        assert state.step == 0

    @pytest.mark.anyio
    async def test_overflow_without_session_manager(
        self, session_manager: SessionManager
    ) -> None:
        from laffyhand.agent.loop import _compact_on_overflow

        async def mock_stream(messages, **kwargs):
            yield StreamText(delta="Summary.")
            yield StreamFinish(finish_reason="stop")

        llm = MagicMock()
        llm.stream = mock_stream

        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="Hello! " * 5000),
            AssistantMessage(content="Hi! " * 5000),
            UserMessage(content="More. " * 5000),
            AssistantMessage(content="Response. " * 5000),
        ]
        state = AgentState(
            messages=msgs,
            turn_count=2,
            session_id="test-session",
            usage=SessionUsage(context_size=2000),
        )
        config = CompactionConfig(tail_turns=1)
        result = await _compact_on_overflow(state, llm, config, None)
        assert result is True
        assert len(state.messages) < len(msgs)

    @pytest.mark.anyio
    async def test_overflow_with_session_compact_fails(
        self, session_manager: SessionManager
    ) -> None:
        from laffyhand.agent.loop import _compact_on_overflow

        async def mock_stream(messages, **kwargs):
            yield StreamError(error="LLM failed")

        llm = MagicMock()
        llm.stream = mock_stream

        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="Hello! " * 5000),
        ]
        session = session_manager.create(messages=msgs)
        state = AgentState(
            messages=msgs,
            session_id=session.id,
            usage=SessionUsage(context_size=2000),
        )
        config = CompactionConfig()
        result = await _compact_on_overflow(state, llm, config, session_manager)
        assert result is False


# ── create_runtime ─────────────────────────────────────────────


SAMPLE_PROVIDERS = {
    "test": {
        "type": "openai",
        "base_url": "http://test",
        "api_key": "test-key",
        "models": [{"name": "test-model", "context_size": 128000}],
    },
}


class TestCreateRuntime:
    @pytest.mark.anyio
    async def test_creates_runtime(self):
        from laffyhand.main import create_runtime
        from laffyhand.config import LaffyConfig

        config = LaffyConfig.model_construct(
            llm={"default_provider": "test", "providers": SAMPLE_PROVIDERS},
        )

        with patch("laffyhand.main.AgentRuntime") as mock_rt_cls:
            mock_rt = MagicMock()
            mock_rt_cls.return_value = mock_rt

            async def mock_get_wrapped():
                return []

            mock_rt.mcp_service.get_wrapped_tools = mock_get_wrapped
            mock_rt.init_tools = AsyncMock()

            runtime = await create_runtime(config)

        assert runtime is not None
        mock_rt_cls.assert_called_once_with(config=config)
        mock_rt.load_skills.assert_called_once()
        mock_rt.load_agents.assert_called_once()
        mock_rt.init_tools.assert_called_once()

    @pytest.mark.anyio
    async def test_runtime_has_registries(self):
        from laffyhand.main import create_runtime
        from laffyhand.config import LaffyConfig

        config = LaffyConfig.model_construct(
            llm={"default_provider": "test", "providers": SAMPLE_PROVIDERS},
        )

        with patch("laffyhand.main.AgentRuntime") as mock_rt_cls:
            mock_rt = MagicMock()
            mock_rt_cls.return_value = mock_rt
            mock_rt.mcp_service = MagicMock()

            async def mock_get_wrapped():
                return []

            mock_rt.mcp_service.get_wrapped_tools = mock_get_wrapped
            mock_rt.init_tools = AsyncMock()

            runtime = await create_runtime(config)

        assert runtime is not None
        assert mock_rt.load_skills.called
        assert mock_rt.load_agents.called
