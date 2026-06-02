from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from laffyhand.agent.agent import AgentInfo
from laffyhand.agent.llm.specs.models import SystemMessage, UserMessage
from laffyhand.agent.runtime import AgentRuntime, MAX_SUBAGENT_DEPTH
from laffyhand.agent.schemas import (
    AgentState,
    SessionID,
    SessionUsage,
)
from laffyhand.agent.tools.registry import ToolRegistry


@pytest.fixture
def runtime(session_manager, runtime_config):
    rt = AgentRuntime(
        config=runtime_config,
        llm=MagicMock(),
        session_manager=session_manager,
        mcp_service=MagicMock(),
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
            session_id=SessionID("s1"),
            usage=SessionUsage(context_size=1000),
        )
        runtime.state = state
        assert runtime.state is state
        assert runtime.current_session_id == "s1"

    def test_current_session_id_none_when_state_has_no_id(self, runtime):
        state = AgentState(
            messages=[],
            session_id=SessionID(""),
            usage=SessionUsage(context_size=0),
        )
        runtime._states[""] = state
        runtime._session_id = ""
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
    @pytest.mark.anyio
    async def test_returns_base_prompt_plus_tools(self, runtime):
        runtime.tool_registry.register_tool(MagicMock(name="read"))
        with patch.object(runtime, "_load_preferences", AsyncMock(return_value="")):
            prompt = await runtime.build_system_prompt("Base prompt.\n")
        assert prompt.startswith("<soul>\nBase prompt.")
        assert "<tools>" in prompt
        assert "<env>" in prompt

    @pytest.mark.anyio
    async def test_includes_skills_when_available(self, runtime):
        with (
            patch.object(runtime.skill_registry, "all") as mock_all,
            patch.object(
                runtime.skill_registry, "build_skills_summary"
            ) as mock_summary,
            patch.object(runtime, "_load_preferences", AsyncMock(return_value="")),
        ):
            mock_all.return_value = {"skill1": MagicMock()}
            mock_summary.return_value = "<skills>\n- **skill1**: desc\n</skills>"
            prompt = await runtime.build_system_prompt("Base.\n")
            assert "<skills>" in prompt


class TestPreferences:
    @pytest.mark.anyio
    async def test_load_initial_preferences_from_cwd(self, runtime, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("Rule 1\nRule 2")
        runtime._preferences = None  # force fresh load
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            result = await runtime._load_preferences()
        assert "<preference>" in result
        assert "Rule 1" in result
        assert "Rule 2" in result
        assert runtime._preferences is not None
        # cached on second call
        cached = await runtime._load_preferences()
        assert cached is result

    @pytest.mark.anyio
    async def test_load_initial_no_agents_md(self, runtime):
        runtime._preferences = None
        with (
            patch("os.getcwd", return_value="/nonexistent"),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            result = await runtime._load_preferences()
        assert result == ""

    @pytest.mark.anyio
    async def test_poll_new_preferences_detects_new_file(self, runtime, tmp_path):
        runtime._preferences = ""
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            result = await runtime.poll_new_preferences()
        assert result == ""
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("New rule")
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            result = await runtime.poll_new_preferences()
        assert "<preference>" in result
        assert "New rule" in result

    @pytest.mark.anyio
    async def test_poll_new_preferences_detects_changed_file(self, runtime, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("Original rule")
        runtime._preferences = None
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            await runtime._load_preferences()
        agents_md.write_text("Changed rule")
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            result = await runtime.poll_new_preferences()
        assert "Changed rule" in result

    @pytest.mark.anyio
    async def test_poll_new_preferences_returns_empty_when_unchanged(
        self, runtime, tmp_path
    ):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("Stable rule")
        runtime._preferences = None
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            await runtime._load_preferences()
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            result = await runtime.poll_new_preferences()
        assert result == ""

    @pytest.mark.anyio
    async def test_poll_new_preferences_cleared_cache_rescans(self, runtime, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("Persistent rule")
        runtime._preferences = ""
        runtime._preference_files = {}
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            result = await runtime.poll_new_preferences()
        assert "Persistent rule" in result

    @pytest.mark.anyio
    async def test_preference_includes_in_system_prompt(self, runtime, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("Be concise.")
        runtime._preferences = None
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            prompt = await runtime.build_system_prompt("Base.")
        assert "<preference>" in prompt
        assert "Be concise." in prompt


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
        state = AgentState(
            messages=[],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        with patch.object(session_manager, "save_state") as mock_save:
            runtime.save_current_state()
            mock_save.assert_called_once_with(session.id, state)

    def test_noop_when_no_state(self, runtime):
        runtime._session_id = None
        with patch.object(runtime.session_manager, "save_state") as mock_save:
            runtime.save_current_state()
            mock_save.assert_not_called()

    def test_noop_when_session_not_in_manager(self, runtime, session_manager):
        state = AgentState(
            messages=[],
            session_id=SessionID("nonexistent"),
            usage=SessionUsage(context_size=0),
        )
        runtime._states["nonexistent"] = state
        runtime._session_id = "nonexistent"
        with patch.object(session_manager, "get", return_value=None):
            with patch.object(session_manager, "save_state") as mock_save:
                runtime.save_current_state()
                mock_save.assert_not_called()


class TestCompleteCurrentSession:
    def test_saves_and_completes(self, runtime, session_manager):
        session = session_manager.create()
        state = AgentState(
            messages=[],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        runtime.complete_current_session()
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "completed"

    def test_noop_when_no_state(self, runtime):
        runtime._session_id = None
        runtime.complete_current_session()


class TestSwitchSession:
    def test_switches_to_existing_session(self, runtime, session_manager):
        session = session_manager.create(messages=[UserMessage(content="hi")])
        old_state = AgentState(
            messages=[],
            session_id=SessionID("old"),
            usage=SessionUsage(context_size=0),
        )
        runtime._states["old"] = old_state
        runtime._session_id = "old"
        result = runtime.switch_session(session.id)
        assert result is True
        assert runtime.state is not None
        assert runtime.state.session_id == session.id

    def test_returns_false_for_nonexistent(self, runtime):
        state = AgentState(
            messages=[],
            session_id=SessionID("old"),
            usage=SessionUsage(context_size=0),
        )
        runtime._states["old"] = state
        runtime._session_id = "old"
        result = runtime.switch_session("nonexistent")
        assert result is False


class TestNewSession:
    def test_creates_new_session(self, runtime, session_manager):
        old_session = session_manager.create()
        state = AgentState(
            messages=[SystemMessage(content="old")],
            session_id=old_session.id,
            usage=SessionUsage(context_size=100),
            turn_count=5,
        )
        runtime._states[old_session.id] = state
        runtime._session_id = old_session.id
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
        state = AgentState(
            messages=[SystemMessage(content="old")],
            session_id=old_session.id,
            usage=SessionUsage(context_size=100),
        )
        runtime._states[old_session.id] = state
        runtime._session_id = old_session.id
        runtime.new_session(SystemMessage(content="new"))
        fetched = session_manager.get(old_session.id)
        assert fetched is not None
        assert fetched.status == "completed"


class TestForkSession:
    def test_forks_current_session(self, runtime, session_manager):
        session = session_manager.create(messages=[UserMessage(content="hi")])
        state = AgentState(
            messages=[SystemMessage(content="test")],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        child_id = runtime.fork_session()
        assert child_id is not None
        assert child_id != session.id
        assert runtime.state.session_id == child_id

    def test_returns_none_when_no_state(self, runtime):
        runtime._session_id = None
        result = runtime.fork_session()
        assert result is None

    def test_returns_none_without_session_id(self, runtime):
        state = AgentState(
            messages=[],
            session_id=SessionID(""),
            usage=SessionUsage(context_size=0),
        )
        runtime._states[""] = state
        runtime._session_id = ""
        result = runtime.fork_session()
        assert result is None


class TestCreateSubagent:
    @pytest.mark.anyio
    async def test_depth_exceeded_returns_error(self, runtime, session_manager):
        session = session_manager.create()
        state = AgentState(
            messages=[],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        agent_info = AgentInfo(name="test")
        with patch.object(
            session_manager, "get_depth", return_value=MAX_SUBAGENT_DEPTH + 1
        ):
            result = await runtime.create_subagent(agent_info, "Do it")
        assert "maximum sub-agent depth" in result

    @pytest.mark.anyio
    async def test_foreground_runs_agent_loop(self, runtime, session_manager):
        session = session_manager.create()
        state = AgentState(
            messages=[],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        agent_info = AgentInfo(name="test", prompt="You are test.")

        with patch("laffyhand.agent.runtime.agent_loop") as mock_loop:

            async def mock_agent_loop(*args, **kwargs):
                child_state = args[0]
                child_state.messages.append(UserMessage(content="final answer"))
                from laffyhand.agent.schemas import StepFinish

                yield StepFinish(index=1, reason="stop")

            mock_loop.side_effect = mock_agent_loop

            result = await runtime.create_subagent(agent_info, "Do the task")

        assert "<task>" in result
        assert "final answer" in result

    @pytest.mark.anyio
    async def test_foreground_no_output_returns_placeholder(
        self, runtime, session_manager
    ):
        session = session_manager.create()
        state = AgentState(
            messages=[],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        agent_info = AgentInfo(name="test", prompt="You are test.")

        with patch("laffyhand.agent.runtime.agent_loop") as mock_loop:

            async def mock_agent_loop(*args, **kwargs):
                from laffyhand.agent.schemas import StepFinish

                yield StepFinish(index=1, reason="stop")

            mock_loop.side_effect = mock_agent_loop

            result = await runtime.create_subagent(agent_info, "Do it")
        assert "<task>" in result

    @pytest.mark.anyio
    async def test_background_spawns_subagent(self, runtime, session_manager):
        session = session_manager.create()
        state = AgentState(
            messages=[],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        agent_info = AgentInfo(name="test", prompt="You are test.")

        with patch.object(
            runtime.subagent_manager, "spawn", new_callable=AsyncMock
        ) as mock_spawn:
            mock_spawn.return_value = "abc123def456"
            result = await runtime.create_subagent(
                agent_info,
                "Do it",
                background=True,
            )
        assert "started" in result
        assert "test" in result
        mock_spawn.assert_awaited_once()

    @pytest.mark.anyio
    async def test_background_spawn_receives_compaction_config(
        self, runtime, session_manager
    ):
        session = session_manager.create()
        state = AgentState(
            messages=[],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        agent_info = AgentInfo(name="test", prompt="You are test.")

        with patch.object(
            runtime.subagent_manager, "spawn", new_callable=AsyncMock
        ) as mock_spawn:
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
        runtime._session_id = None
        result = await runtime.generate_title_for_current()
        assert result is None

    @pytest.mark.anyio
    async def test_no_session_id_returns_none(self, runtime):
        runtime.title_config.mode = "auto"
        state = AgentState(
            messages=[],
            session_id=SessionID(""),
            usage=SessionUsage(context_size=0),
        )
        runtime._states[""] = state
        runtime._session_id = ""
        result = await runtime.generate_title_for_current()
        assert result is None

    @pytest.mark.anyio
    async def test_generates_title(self, runtime, session_manager):
        runtime.title_config.mode = "auto"
        session = session_manager.create(messages=[UserMessage(content="Hello")])
        state = AgentState(
            messages=[UserMessage(content="Hello")],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        runtime.llm.stream = MagicMock()

        with patch(
            "laffyhand.agent.title.generate_title", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = "My Title"
            result = await runtime.generate_title_for_current()
            assert result == "My Title"


class TestScheduleTitleGeneration:
    @pytest.mark.anyio
    async def test_mode_off_skips(self, runtime):
        runtime.title_config.mode = "off"
        runtime._do_generate_title = AsyncMock()
        runtime._schedule_title_generation("sid", "auto")
        runtime._do_generate_title.assert_not_called()

    @pytest.mark.anyio
    async def test_trigger_mismatch_skips(self, runtime):
        runtime.title_config.mode = "auto"
        runtime._do_generate_title = AsyncMock()
        session = runtime.session_manager.create()
        runtime._schedule_title_generation(session.id, "on_create")
        runtime._do_generate_title.assert_not_called()

    @pytest.mark.anyio
    async def test_existing_title_skips(self, runtime):
        runtime.title_config.mode = "auto"
        runtime._do_generate_title = AsyncMock()
        session = runtime.session_manager.create(title="Existing")
        runtime._schedule_title_generation(session.id, "auto")
        runtime._do_generate_title.assert_not_called()

    @pytest.mark.anyio
    async def test_fires_background_task(self, runtime):
        runtime.title_config.mode = "auto"
        runtime._do_generate_title = AsyncMock()
        session = runtime.session_manager.create()
        runtime._schedule_title_generation(session.id, "auto")
        await asyncio.sleep(0)
        runtime._do_generate_title.assert_awaited_once_with(session.id)


class TestDoGenerateTitle:
    @pytest.mark.anyio
    async def test_generates_title(self, runtime, session_manager):
        from laffyhand.agent.llm.specs.models import StreamText, StreamFinish

        async def mock_stream(messages, **kwargs):
            yield StreamText(delta="My Title")
            yield StreamFinish(finish_reason="stop")

        runtime.llm.stream = mock_stream
        runtime._llm_for_session = MagicMock(return_value=runtime.llm)
        msgs = [UserMessage(content="Hello world")]
        session = session_manager.create(messages=msgs)
        await runtime._do_generate_title(session.id)
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.title == "My Title"

    @pytest.mark.anyio
    async def test_exception_logged(self, runtime, session_manager):
        runtime._llm_for_session = MagicMock(side_effect=Exception("mock error"))
        session = session_manager.create()
        with patch("laffyhand.agent.runtime.logger.exception") as mock_log:
            await runtime._do_generate_title(session.id)
            mock_log.assert_called_once()


class TestShutdown:
    @pytest.mark.anyio
    async def test_saves_state_and_disconnects(self, runtime, session_manager):
        session = session_manager.create()
        state = AgentState(
            messages=[],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        runtime._session_id = session.id
        runtime.mcp_service.disconnect_all = AsyncMock()
        await runtime.shutdown()
        runtime.mcp_service.disconnect_all.assert_awaited_once()
        assert runtime.session_manager is not None
