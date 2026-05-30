from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.schemas import (
    AgentState,
    AssistantMessage,
    CompactionConfig,
    StreamText,
    StreamFinish,
    StreamError,
    SystemMessage,
    SessionUsage,
    UserMessage,
)


# ── handle_repl_command ──────────────────────────────────────


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock()
    client.list_sessions.return_value = [
        {"id": "sess-1", "status": "active", "title": "Test", "message_count": 5,
         "turn_count": 3, "input_tokens": 100, "output_tokens": 200,
         "created_at": "2024-01-01T00:00:00", "updated_at": "2024-01-01T00:00:00"},
        {"id": "sess-2", "status": "active", "title": "", "message_count": 2,
         "turn_count": 1, "input_tokens": 50, "output_tokens": 75,
         "created_at": "2024-01-02T00:00:00", "updated_at": "2024-01-02T00:00:00"},
    ]
    client.load_session.return_value = {"session_id": "sess-1", "messages_count": 5, "turn_count": 3}
    client.create_session.return_value = "new-sess-id"
    client.fork_session.return_value = "forked-sess-id"
    client.generate_session_title.return_value = "Generated Title"
    client.search_sessions.return_value = [
        {"id": "sess-1", "status": "active", "title": "Found", "message_count": 3,
         "turn_count": 2, "input_tokens": 60, "output_tokens": 120,
         "created_at": "2024-01-01T00:00:00", "updated_at": "2024-01-01T00:00:00"},
    ]
    return client


class TestHandleReplCommand:
    @pytest.mark.anyio
    async def test_sessions(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/sessions", mock_client)
        assert result is True
        mock_client.list_sessions.assert_called_once_with(limit=20)
        captured = capsys.readouterr()
        assert "sess-1" in captured.out
        assert "sess-2" in captured.out

    @pytest.mark.anyio
    async def test_sessions_empty(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        mock_client.list_sessions.return_value = []
        result = await handle_repl_command("/sessions", mock_client)
        assert result is True
        captured = capsys.readouterr()
        assert "No sessions." in captured.out

    @pytest.mark.anyio
    async def test_session_switch(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/session sess-1", mock_client)
        assert result is True
        mock_client.load_session.assert_called_once_with("sess-1")
        captured = capsys.readouterr()
        assert "Switched to session: sess-1" in captured.out

    @pytest.mark.anyio
    async def test_session_no_arg(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/session", mock_client)
        assert result is True
        captured = capsys.readouterr()
        assert "Usage:" in captured.out

    @pytest.mark.anyio
    async def test_session_not_found(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        mock_client.load_session.side_effect = Exception("not found")
        result = await handle_repl_command("/session nonexistent", mock_client)
        assert result is True
        captured = capsys.readouterr()
        assert "not found" in captured.out

    @pytest.mark.anyio
    async def test_new(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/new", mock_client)
        assert result is True
        mock_client.create_session.assert_called_once()
        captured = capsys.readouterr()
        assert "new-sess-id" in captured.out

    @pytest.mark.anyio
    async def test_title_set(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/title My Title", mock_client)
        assert result is True
        mock_client.set_session_title.assert_called_once_with(title="My Title")
        captured = capsys.readouterr()
        assert "My Title" in captured.out

    @pytest.mark.anyio
    async def test_title_generate(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/title", mock_client)
        assert result is True
        mock_client.generate_session_title.assert_called_once()
        captured = capsys.readouterr()
        assert "Generated Title" in captured.out

    @pytest.mark.anyio
    async def test_title_generate_fails(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        mock_client.generate_session_title.return_value = None
        result = await handle_repl_command("/title", mock_client)
        assert result is True
        captured = capsys.readouterr()
        assert "Could not generate" in captured.out

    @pytest.mark.anyio
    async def test_fork(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/fork", mock_client)
        assert result is True
        mock_client.fork_session.assert_called_once()
        captured = capsys.readouterr()
        assert "forked-sess-id" in captured.out

    @pytest.mark.anyio
    async def test_fork_no_active(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        mock_client.fork_session.side_effect = Exception("No active session")
        result = await handle_repl_command("/fork", mock_client)
        assert result is True
        captured = capsys.readouterr()
        assert "No active" in captured.out

    @pytest.mark.anyio
    async def test_archive(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/archive", mock_client)
        assert result is True
        mock_client.archive_session.assert_called_once_with(session_id="")

    @pytest.mark.anyio
    async def test_archive_with_id(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/archive some-id", mock_client)
        assert result is True
        mock_client.archive_session.assert_called_once_with(session_id="some-id")

    @pytest.mark.anyio
    async def test_search(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/search test", mock_client)
        assert result is True
        mock_client.search_sessions.assert_called_once_with("test", limit=20)
        captured = capsys.readouterr()
        assert "Found 1" in captured.out
        assert "Found" in captured.out

    @pytest.mark.anyio
    async def test_search_no_query(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/search", mock_client)
        assert result is True
        captured = capsys.readouterr()
        assert "Usage:" in captured.out

    @pytest.mark.anyio
    async def test_search_no_results(self, mock_client: AsyncMock, capsys) -> None:
        from laffyhand.main import handle_repl_command

        mock_client.search_sessions.return_value = []
        result = await handle_repl_command("/search nonexistent", mock_client)
        assert result is True
        captured = capsys.readouterr()
        assert "No sessions found" in captured.out

    @pytest.mark.anyio
    async def test_unknown_command(self, mock_client: AsyncMock) -> None:
        from laffyhand.main import handle_repl_command

        result = await handle_repl_command("/unknown", mock_client)
        assert result is False


# ── generate_title ───────────────────────────────────────────


class TestGenerateTitle:
    @pytest.mark.anyio
    async def test_mode_off_returns_none(self, session_manager: SessionManager) -> None:
        from laffyhand.agent.title import generate_title

        config = TitleConfig(mode="off")
        result = await generate_title(session_manager, "sid", MagicMock(), config)
        assert result is None

    @pytest.mark.anyio
    async def test_no_user_messages_returns_none(self, session_manager: SessionManager) -> None:
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
    async def test_stream_error_returns_none(self, session_manager: SessionManager) -> None:
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
    async def test_empty_title_returns_none(self, session_manager: SessionManager) -> None:
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
    async def test_no_overflow_returns_false(self, session_manager: SessionManager) -> None:
        from laffyhand.agent.loop import _compact_on_overflow

        state = AgentState(
            messages=[UserMessage(content="hi")],
            usage=SessionUsage(context_size=128000),
        )
        config = CompactionConfig()
        result = await _compact_on_overflow(state, MagicMock(), config, session_manager)
        assert result is False

    @pytest.mark.anyio
    async def test_overflow_with_session_manager(self, session_manager: SessionManager) -> None:
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


class TestCreateRuntime:
    @pytest.mark.anyio
    async def test_creates_runtime(self):
        from laffyhand.main import create_runtime
        from laffyhand.config import LaffyConfig, LLMConfig

        config = LaffyConfig.model_construct(
            llm=LLMConfig(
                base_url="http://test",
                api_key="test-key",
                model_name="test-model",
                context_size=128000,
            ),
        )

        with (
            patch("laffyhand.main.deepseek_route") as mock_route,
            patch("laffyhand.main.LLM") as mock_llm,
            patch("laffyhand.main.MCPService") as mock_mcp,
            patch("laffyhand.main.SessionManager") as mock_sm,
        ):
            mock_route.return_value = "route"
            mock_llm.return_value = MagicMock()
            mock_mcp_instance = MagicMock()

            async def mock_get_wrapped():
                return []

            mock_mcp_instance = MagicMock()
            mock_mcp_instance.get_wrapped_tools = mock_get_wrapped
            mock_mcp.return_value = mock_mcp_instance
            mock_sm_instance = MagicMock()
            mock_sm.return_value = mock_sm_instance

            runtime = await create_runtime(config)

        assert runtime is not None
        assert runtime.llm is not None
        assert runtime.session_manager is not None
        assert runtime.mcp_service is not None

    @pytest.mark.anyio
    async def test_runtime_has_registries(self):
        from laffyhand.main import create_runtime
        from laffyhand.config import LaffyConfig, LLMConfig

        config = LaffyConfig.model_construct(
            llm=LLMConfig(
                base_url="http://test",
                api_key="test-key",
                model_name="test-model",
                context_size=128000,
            ),
        )

        with (
            patch("laffyhand.main.deepseek_route") as mock_route,
            patch("laffyhand.main.LLM") as mock_llm,
            patch("laffyhand.main.MCPService") as mock_mcp,
            patch("laffyhand.main.SessionManager") as mock_sm,
        ):
            mock_route.return_value = "route"
            mock_llm.return_value = MagicMock()

            async def mock_get_wrapped():
                return []

            mock_mcp_instance = MagicMock()
            mock_mcp_instance.get_wrapped_tools = mock_get_wrapped
            mock_mcp.return_value = mock_mcp_instance
            mock_sm_instance = MagicMock()
            mock_sm.return_value = mock_sm_instance

            runtime = await create_runtime(config)

        assert runtime.agent_registry is not None
        assert runtime.tool_registry is not None
        assert runtime.skill_registry is not None
        assert runtime.subagent_manager is not None
