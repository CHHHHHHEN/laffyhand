from __future__ import annotations

import argparse
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from laffyhand.agent.runtime import AgentRuntime
from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.schemas import (
    AgentState, AssistantMessage, CompactionConfig, StreamText, StreamFinish,
    StreamError, SystemMessage, SessionUsage, UserMessage,
)


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def manager(db_path: str) -> SessionManager:
    return SessionManager(db_path)


@pytest.fixture
def runtime(manager: SessionManager) -> AgentRuntime:
    rt = AgentRuntime(
        llm=MagicMock(),
        session_manager=manager,
        mcp_service=MagicMock(),
        compaction_config=CompactionConfig(),
        title_config=TitleConfig(mode="off"),
        max_steps=50,
        max_subagents=2,
        db_path=":memory:",
    )
    rt._state = AgentState(
        messages=[SystemMessage(content="system")],
        session_id="",
        usage=SessionUsage(context_size=128000),
    )
    return rt


def make_messages():
    return [
        SystemMessage(content="system"),
        UserMessage(content="Hello!"),
        AssistantMessage(content="Hi there!"),
    ]


# ── resolve_session ──────────────────────────────────────────

class TestResolveSession:
    @pytest.mark.anyio
    async def test_creates_new_session(self, manager: SessionManager) -> None:
        from laffyhand.main import resolve_session
        args = argparse.Namespace(session=None, resume=False, list=False)
        sys_msg = SystemMessage(content="system")
        state = await resolve_session(args, manager, sys_msg)
        assert state.session_id is not None
        assert len(state.messages) == 1
        assert state.messages[0].content == "system"

    @pytest.mark.anyio
    async def test_resume_found(self, manager: SessionManager) -> None:
        from laffyhand.main import resolve_session
        session = manager.create()
        args = argparse.Namespace(session=None, resume=True, list=False)
        sys_msg = SystemMessage(content="system")
        state = await resolve_session(args, manager, sys_msg)
        assert state.session_id == session.id

    @pytest.mark.anyio
    async def test_resume_not_found_creates_new(self, manager: SessionManager) -> None:
        from laffyhand.main import resolve_session
        args = argparse.Namespace(session=None, resume=True, list=False)
        sys_msg = SystemMessage(content="system")
        state = await resolve_session(args, manager, sys_msg)
        assert state.session_id is not None

    @pytest.mark.anyio
    async def test_session_specified_found(self, manager: SessionManager) -> None:
        from laffyhand.main import resolve_session
        session = manager.create()
        args = argparse.Namespace(session=session.id, resume=False, list=False)
        sys_msg = SystemMessage(content="system")
        state = await resolve_session(args, manager, sys_msg)
        assert state.session_id == session.id

    @pytest.mark.anyio
    async def test_session_specified_not_found_exits(self, manager: SessionManager) -> None:
        from laffyhand.main import resolve_session
        args = argparse.Namespace(session="nonexistent", resume=False, list=False)
        sys_msg = SystemMessage(content="system")
        with pytest.raises(SystemExit):
            await resolve_session(args, manager, sys_msg)


# ── handle_repl_command ──────────────────────────────────────

class TestHandleReplCommand:
    @pytest.mark.anyio
    async def test_sessions(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        runtime.session_manager.create()
        runtime.session_manager.create()
        result = await handle_repl_command("/sessions", runtime)
        assert result is True
        captured = capsys.readouterr()
        assert "No sessions." not in captured.out

    @pytest.mark.anyio
    async def test_sessions_empty(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        result = await handle_repl_command("/sessions", runtime)
        assert result is True
        captured = capsys.readouterr()
        assert "No sessions." in captured.out

    @pytest.mark.anyio
    async def test_session_switch(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        msgs = [UserMessage(content="test")]
        session = runtime.session_manager.create(messages=msgs)
        result = await handle_repl_command(f"/session {session.id}", runtime)
        assert result is True
        assert runtime.state.session_id == session.id

    @pytest.mark.anyio
    async def test_session_no_arg(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        result = await handle_repl_command("/session", runtime)
        assert result is True
        captured = capsys.readouterr()
        assert "Usage:" in captured.out

    @pytest.mark.anyio
    async def test_session_not_found(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        result = await handle_repl_command("/session nonexistent", runtime)
        assert result is True
        captured = capsys.readouterr()
        assert "not found" in captured.out

    @pytest.mark.anyio
    async def test_new(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        runtime.state.session_id = "some-old-session"
        result = await handle_repl_command("/new", runtime)
        assert result is True
        assert runtime.state.session_id != "some-old-session"
        assert runtime.state.turn_count == 0

    @pytest.mark.anyio
    async def test_title_set(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        session = runtime.session_manager.create()
        runtime.state.session_id = session.id
        result = await handle_repl_command("/title My Title", runtime)
        assert result is True
        fetched = runtime.session_manager.get(session.id)
        assert fetched is not None
        assert fetched.title == "My Title"

    @pytest.mark.anyio
    async def test_title_no_active(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        runtime.state.session_id = ""
        result = await handle_repl_command("/title MyTitle", runtime)
        assert result is True
        captured = capsys.readouterr()
        assert "No active session" in captured.out

    @pytest.mark.anyio
    async def test_fork(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        session = runtime.session_manager.create(messages=[UserMessage(content="hi")])
        runtime.state.session_id = session.id
        result = await handle_repl_command("/fork", runtime)
        assert result is True
        assert runtime.state.session_id != session.id

    @pytest.mark.anyio
    async def test_fork_no_active(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        runtime.state.session_id = ""
        result = await handle_repl_command("/fork", runtime)
        assert result is True
        captured = capsys.readouterr()
        assert "No active" in captured.out

    @pytest.mark.anyio
    async def test_archive(self, runtime: AgentRuntime, capsys) -> None:
        from laffyhand.main import handle_repl_command
        session = runtime.session_manager.create()
        runtime.state.session_id = session.id
        result = await handle_repl_command("/archive", runtime)
        assert result is True
        fetched = runtime.session_manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "archived"

    @pytest.mark.anyio
    async def test_unknown_command(self, runtime: AgentRuntime) -> None:
        from laffyhand.main import handle_repl_command
        result = await handle_repl_command("/unknown", runtime)
        assert result is False


# ── generate_title ───────────────────────────────────────────

class TestGenerateTitle:
    @pytest.mark.anyio
    async def test_mode_off_returns_none(self, manager: SessionManager) -> None:
        from laffyhand.agent.title import generate_title
        config = TitleConfig(mode="off")
        result = await generate_title(manager, "sid", MagicMock(), config)
        assert result is None

    @pytest.mark.anyio
    async def test_no_user_messages_returns_none(self, manager: SessionManager) -> None:
        from laffyhand.agent.title import generate_title
        session = manager.create(messages=[SystemMessage(content="sys")])
        config = TitleConfig(mode="auto")
        result = await generate_title(manager, session.id, MagicMock(), config)
        assert result is None

    @pytest.mark.anyio
    async def test_generates_title(self, manager: SessionManager) -> None:
        from laffyhand.agent.title import generate_title

        async def mock_stream(messages, **kwargs):
            yield StreamText(delta="My Title")
            yield StreamFinish(finish_reason="stop")

        llm = MagicMock()
        llm.stream = mock_stream
        msgs = [UserMessage(content="Hello world")]
        session = manager.create(messages=msgs)
        config = TitleConfig(mode="auto")
        result = await generate_title(manager, session.id, llm, config)
        assert result == "My Title"
        fetched = manager.get(session.id)
        assert fetched is not None
        assert fetched.title == "My Title"

    @pytest.mark.anyio
    async def test_stream_error_returns_none(self, manager: SessionManager) -> None:
        from laffyhand.agent.title import generate_title

        async def mock_stream(messages, **kwargs):
            yield StreamError(error="API error")

        llm = MagicMock()
        llm.stream = mock_stream
        msgs = [UserMessage(content="Hello")]
        session = manager.create(messages=msgs)
        config = TitleConfig(mode="auto")
        result = await generate_title(manager, session.id, llm, config)
        assert result is None

    @pytest.mark.anyio
    async def test_empty_title_returns_none(self, manager: SessionManager) -> None:
        from laffyhand.agent.title import generate_title

        async def mock_stream(messages, **kwargs):
            yield StreamText(delta="")
            yield StreamFinish(finish_reason="stop")

        llm = MagicMock()
        llm.stream = mock_stream
        msgs = [UserMessage(content="Hello")]
        session = manager.create(messages=msgs)
        config = TitleConfig(mode="auto")
        result = await generate_title(manager, session.id, llm, config)
        assert result is None


# ── _compact_on_overflow ─────────────────────────────────────

class TestCompactOnOverflow:
    @pytest.mark.anyio
    async def test_no_overflow_returns_false(self, manager: SessionManager) -> None:
        from laffyhand.agent.loop import _compact_on_overflow
        state = AgentState(
            messages=[UserMessage(content="hi")],
            usage=SessionUsage(context_size=128000),
        )
        config = CompactionConfig()
        result = await _compact_on_overflow(state, MagicMock(), config, manager)
        assert result is False

    @pytest.mark.anyio
    async def test_overflow_with_session_manager(self, manager: SessionManager) -> None:
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
        session = manager.create(messages=msgs)
        state = AgentState(
            messages=msgs,
            turn_count=2,
            step=0,
            session_id=session.id,
            usage=SessionUsage(context_size=2000),
        )
        config = CompactionConfig(tail_turns=1)
        result = await _compact_on_overflow(state, llm, config, manager)
        assert result is True
        assert state.session_id != session.id
        assert state.step == 0

    @pytest.mark.anyio
    async def test_overflow_without_session_manager(self, manager: SessionManager) -> None:
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
    async def test_overflow_with_session_compact_fails(self, manager: SessionManager) -> None:
        from laffyhand.agent.loop import _compact_on_overflow

        async def mock_stream(messages, **kwargs):
            yield StreamError(error="LLM failed")

        llm = MagicMock()
        llm.stream = mock_stream

        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="Hello! " * 5000),
        ]
        session = manager.create(messages=msgs)
        state = AgentState(
            messages=msgs,
            session_id=session.id,
            usage=SessionUsage(context_size=2000),
        )
        config = CompactionConfig()
        result = await _compact_on_overflow(state, llm, config, manager)
        assert result is False


# ── create_runtime ─────────────────────────────────────────────

class TestCreateRuntime:
    @pytest.mark.anyio
    async def test_creates_runtime(self):
        from laffyhand.main import create_runtime

        args = argparse.Namespace(session=None, resume=False, list=False)

        with patch("laffyhand.main.OPENCODE_BASE_URL", "http://test"), \
             patch("laffyhand.main.OPENCODE_API_KEY", "test-key"), \
             patch("laffyhand.main.OPENCODE_MODEL_NAME", "test-model"), \
             patch("laffyhand.main.MODEL_CONTEXT_SIZE", 128000), \
             patch("laffyhand.main.deepseek_route") as mock_route, \
             patch("laffyhand.main.LLM") as mock_llm, \
             patch("laffyhand.main.MCPService") as mock_mcp, \
             patch("laffyhand.main.SessionManager") as mock_sm:
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

            runtime = await create_runtime(args)

        assert runtime is not None
        assert runtime.llm is not None
        assert runtime.session_manager is not None
        assert runtime.mcp_service is not None

    @pytest.mark.anyio
    async def test_runtime_has_registries(self):
        from laffyhand.main import create_runtime

        args = argparse.Namespace(session=None, resume=False, list=False)

        with patch("laffyhand.main.OPENCODE_BASE_URL", "http://test"), \
             patch("laffyhand.main.OPENCODE_API_KEY", "test-key"), \
             patch("laffyhand.main.OPENCODE_MODEL_NAME", "test-model"), \
             patch("laffyhand.main.MODEL_CONTEXT_SIZE", 128000), \
             patch("laffyhand.main.deepseek_route") as mock_route, \
             patch("laffyhand.main.LLM") as mock_llm, \
             patch("laffyhand.main.MCPService") as mock_mcp, \
             patch("laffyhand.main.SessionManager") as mock_sm:
            mock_route.return_value = "route"
            mock_llm.return_value = MagicMock()
            async def mock_get_wrapped():
                return []
            mock_mcp_instance = MagicMock()
            mock_mcp_instance.get_wrapped_tools = mock_get_wrapped
            mock_mcp.return_value = mock_mcp_instance
            mock_sm_instance = MagicMock()
            mock_sm.return_value = mock_sm_instance

            runtime = await create_runtime(args)

        assert runtime.agent_registry is not None
        assert runtime.tool_registry is not None
        assert runtime.skill_registry is not None
        assert runtime.subagent_manager is not None
