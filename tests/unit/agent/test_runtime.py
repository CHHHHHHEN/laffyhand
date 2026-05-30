from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from laffyhand.agent.agent import AgentInfo
from laffyhand.agent.runtime import AgentRuntime, MAX_SUBAGENT_DEPTH
from laffyhand.agent.schemas import (
    AgentState, CompactionConfig, SessionUsage, SystemMessage, UserMessage,
)
from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.tools.registry import ToolRegistry


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def session_manager(db_path):
    return SessionManager(db_path)


@pytest.fixture
def runtime(session_manager):
    rt = AgentRuntime(
        llm=MagicMock(),
        session_manager=session_manager,
        mcp_service=MagicMock(),
        compaction_config=CompactionConfig(),
        title_config=TitleConfig(mode="off"),
        max_steps=50,
        max_subagents=2,
        db_path=":memory:",
        context_size=128000,
    )
    return rt


class TestAgentRuntimeInit:
    def test_creates_tool_registry(self, runtime):
        assert isinstance(runtime.tool_registry, ToolRegistry)

    def test_creates_agent_registry(self, runtime):
        assert runtime.agent_registry.get("build") is not None

    def test_creates_subagent_manager(self, runtime):
        assert runtime.subagent_manager.active_count() == 0

    def test_initial_state_is_none(self, runtime):
        assert runtime.state is None

    def test_current_session_id_is_none_when_no_state(self, runtime):
        assert runtime.current_session_id is None


class TestStateProperty:
    def test_setter_and_getter(self, runtime):
        state = AgentState(
            messages=[SystemMessage(content="test")],
            session_id="s1",
            usage=SessionUsage(context_size=1000),
        )
        runtime.state = state
        assert runtime.state is state
        assert runtime.current_session_id == "s1"

    def test_current_session_id_none_when_state_has_no_id(self, runtime):
        runtime._state = AgentState(
            messages=[], session_id="", usage=SessionUsage(context_size=0),
        )
        assert runtime.current_session_id == ""


class TestLoadAgents:
    def test_load_agents_calls_discover(self, runtime):
        with patch.object(runtime.agent_registry, "discover") as mock:
            runtime.load_agents(["/tmp/agents"])
            mock.assert_called_once_with(["/tmp/agents"])


class TestLoadSkills:
    def test_load_skills_calls_discover(self, runtime):
        with patch.object(runtime.skill_registry, "discover") as mock:
            runtime.load_skills(["/tmp/skills"])
            mock.assert_called_once_with(["/tmp/skills"])


class TestBuildSystemPrompt:
    def test_returns_base_prompt_plus_tools(self, runtime):
        runtime.tool_registry.register_tool(MagicMock(name="read"))
        prompt = runtime.build_system_prompt("Base prompt.\n")
        assert prompt.startswith("Base prompt.\n")
        assert "Available tools" in prompt

    def test_includes_skills_when_available(self, runtime):
        with patch.object(runtime.skill_registry, "all") as mock_all, \
             patch.object(runtime.skill_registry, "build_skills_summary") as mock_summary:
            mock_all.return_value = {"skill1": MagicMock()}
            mock_summary.return_value = "Skills summary"
            prompt = runtime.build_system_prompt("Base.\n")
            assert "Skills summary" in prompt


class TestCreateInitialState:
    @pytest.mark.anyio
    async def test_creates_new_session(self, runtime):
        sys_msg = SystemMessage(content="You are a bot.")
        state = runtime.create_initial_state(sys_msg)
        assert state.session_id is not None
        assert len(state.messages) == 1
        assert state.messages[0].content == "You are a bot."
        assert runtime.state is state

    @pytest.mark.anyio
    async def test_usage_context_size(self, runtime):
        state = runtime.create_initial_state(SystemMessage(content="hi"))
        assert state.usage.context_size == 128000


class TestSaveCurrentState:
    def test_saves_when_state_and_session_exist(self, runtime, session_manager):
        session = session_manager.create()
        runtime._state = AgentState(
            messages=[], session_id=session.id, usage=SessionUsage(context_size=0),
        )
        with patch.object(session_manager, "save_state") as mock_save:
            runtime.save_current_state()
            mock_save.assert_called_once_with(session.id, runtime._state)

    def test_noop_when_no_state(self, runtime):
        runtime._state = None
        with patch.object(runtime.session_manager, "save_state") as mock_save:
            runtime.save_current_state()
            mock_save.assert_not_called()

    def test_noop_when_session_not_in_manager(self, runtime, session_manager):
        runtime._state = AgentState(
            messages=[], session_id="nonexistent", usage=SessionUsage(context_size=0),
        )
        with patch.object(session_manager, "get", return_value=None):
            with patch.object(session_manager, "save_state") as mock_save:
                runtime.save_current_state()
                mock_save.assert_not_called()


class TestCompleteCurrentSession:
    def test_saves_and_completes(self, runtime, session_manager):
        session = session_manager.create()
        runtime._state = AgentState(
            messages=[], session_id=session.id, usage=SessionUsage(context_size=0),
        )
        runtime.complete_current_session()
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "completed"

    def test_noop_when_no_state(self, runtime):
        runtime._state = None
        runtime.complete_current_session()


class TestSwitchSession:
    def test_switches_to_existing_session(self, runtime, session_manager):
        session = session_manager.create(messages=[UserMessage(content="hi")])
        runtime._state = AgentState(
            messages=[], session_id="old", usage=SessionUsage(context_size=0),
        )
        result = runtime.switch_session(session.id)
        assert result is True
        assert runtime.state is not None
        assert runtime.state.session_id == session.id

    def test_returns_false_for_nonexistent(self, runtime):
        runtime._state = AgentState(
            messages=[], session_id="old", usage=SessionUsage(context_size=0),
        )
        result = runtime.switch_session("nonexistent")
        assert result is False


class TestNewSession:
    def test_creates_new_session(self, runtime, session_manager):
        old_session = session_manager.create()
        runtime._state = AgentState(
            messages=[SystemMessage(content="old")],
            session_id=old_session.id,
            usage=SessionUsage(context_size=100),
            turn_count=5,
        )
        sys_msg = SystemMessage(content="new system")
        runtime.new_session(sys_msg)
        assert runtime.state is not None
        assert runtime.state.session_id != old_session.id
        assert runtime.state.turn_count == 0
        assert runtime.state.step == 0
        assert len(runtime.state.messages) == 1
        assert runtime.state.messages[0].content == "new system"

    def test_previous_session_completed(self, runtime, session_manager):
        old_session = session_manager.create()
        runtime._state = AgentState(
            messages=[SystemMessage(content="old")],
            session_id=old_session.id,
            usage=SessionUsage(context_size=100),
        )
        runtime.new_session(SystemMessage(content="new"))
        fetched = session_manager.get(old_session.id)
        assert fetched is not None
        assert fetched.status == "completed"


class TestForkSession:
    def test_forks_current_session(self, runtime, session_manager):
        session = session_manager.create(messages=[UserMessage(content="hi")])
        runtime._state = AgentState(
            messages=[SystemMessage(content="test")],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        child_id = runtime.fork_session()
        assert child_id is not None
        assert child_id != session.id
        assert runtime.state.session_id == child_id

    def test_returns_none_when_no_state(self, runtime):
        runtime._state = None
        result = runtime.fork_session()
        assert result is None

    def test_returns_none_without_session_id(self, runtime):
        runtime._state = AgentState(
            messages=[], session_id="", usage=SessionUsage(context_size=0),
        )
        result = runtime.fork_session()
        assert result is None


class TestCreateSubagent:
    @pytest.mark.anyio
    async def test_depth_exceeded_returns_error(self, runtime, session_manager):
        session = session_manager.create()
        runtime._state = AgentState(
            messages=[], session_id=session.id, usage=SessionUsage(context_size=0),
        )
        agent_info = AgentInfo(name="test")
        with patch.object(session_manager, "get_depth", return_value=MAX_SUBAGENT_DEPTH + 1):
            result = await runtime.create_subagent(agent_info, "Do it")
        assert "maximum sub-agent depth" in result

    @pytest.mark.anyio
    async def test_foreground_runs_agent_loop(self, runtime, session_manager):
        session = session_manager.create()
        runtime._state = AgentState(
            messages=[], session_id=session.id, usage=SessionUsage(context_size=0),
        )
        agent_info = AgentInfo(name="test", prompt="You are test.")

        with patch("laffyhand.agent.runtime.agent_loop") as mock_loop:
            async def mock_agent_loop(*args, **kwargs):
                child_state = args[0]
                child_state.messages.append(UserMessage(content="final answer"))
                yield MagicMock(type="content", finish_reason="stop")

            mock_loop.side_effect = mock_agent_loop

            result = await runtime.create_subagent(agent_info, "Do the task")

        assert "<task>" in result
        assert "final answer" in result

    @pytest.mark.anyio
    async def test_foreground_no_output_returns_placeholder(self, runtime, session_manager):
        session = session_manager.create()
        runtime._state = AgentState(
            messages=[], session_id=session.id, usage=SessionUsage(context_size=0),
        )
        agent_info = AgentInfo(name="test", prompt="You are test.")

        with patch("laffyhand.agent.runtime.agent_loop") as mock_loop:
            async def mock_agent_loop(*args, **kwargs):
                yield MagicMock(type="tool_result", data="result")

            mock_loop.side_effect = mock_agent_loop

            result = await runtime.create_subagent(agent_info, "Do it")
        assert "[No output]" in result

    @pytest.mark.anyio
    async def test_background_spawns_subagent(self, runtime, session_manager):
        session = session_manager.create()
        runtime._state = AgentState(
            messages=[], session_id=session.id, usage=SessionUsage(context_size=0),
        )
        agent_info = AgentInfo(name="test", prompt="You are test.")

        with patch.object(runtime.subagent_manager, "spawn", new_callable=AsyncMock) as mock_spawn:
            mock_spawn.return_value = "abc123def456"
            result = await runtime.create_subagent(
                agent_info, "Do it", background=True,
            )
        assert "started" in result
        assert "test" in result
        mock_spawn.assert_awaited_once()

    @pytest.mark.anyio
    async def test_background_spawn_receives_compaction_config(self, runtime, session_manager):
        session = session_manager.create()
        runtime._state = AgentState(
            messages=[], session_id=session.id, usage=SessionUsage(context_size=0),
        )
        agent_info = AgentInfo(name="test", prompt="You are test.")

        with patch.object(runtime.subagent_manager, "spawn", new_callable=AsyncMock) as mock_spawn:
            await runtime.create_subagent(agent_info, "Do it", background=True)
            _call_session = mock_spawn.call_args[1]["session_manager"]
            _call_compaction = mock_spawn.call_args[1]["compaction_config"]
            assert _call_session is runtime.session_manager
            assert _call_compaction is runtime.compaction_config


class TestGenerateTitleForCurrent:
    @pytest.mark.anyio
    async def test_off_mode_returns_none(self, runtime):
        runtime.title_config.mode = "off"
        result = await runtime.generate_title_for_current()
        assert result is None

    @pytest.mark.anyio
    async def test_no_state_returns_none(self, runtime):
        runtime.title_config.mode = "auto"
        result = await runtime.generate_title_for_current()
        assert result is None

    @pytest.mark.anyio
    async def test_no_session_id_returns_none(self, runtime):
        runtime.title_config.mode = "auto"
        runtime._state = AgentState(
            messages=[], session_id="", usage=SessionUsage(context_size=0),
        )
        result = await runtime.generate_title_for_current()
        assert result is None

    @pytest.mark.anyio
    async def test_generates_title(self, runtime, session_manager):
        runtime.title_config.mode = "auto"
        session = session_manager.create(messages=[UserMessage(content="Hello")])
        runtime._state = AgentState(
            messages=[UserMessage(content="Hello")],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime.llm.stream = MagicMock()

        with patch("laffyhand.agent.title.generate_title", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "My Title"
            result = await runtime.generate_title_for_current()
            assert result == "My Title"


class TestShutdown:
    @pytest.mark.anyio
    async def test_saves_state_and_disconnects(self, runtime, session_manager):
        session = session_manager.create()
        runtime._state = AgentState(
            messages=[], session_id=session.id, usage=SessionUsage(context_size=0),
        )
        runtime.mcp_service.disconnect_all = AsyncMock()
        await runtime.shutdown()
        runtime.mcp_service.disconnect_all.assert_awaited_once()
        assert runtime.session_manager is not None
