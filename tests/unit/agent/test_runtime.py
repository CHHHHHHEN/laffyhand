from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from laffyhand.agent.agent import AgentInfo
from laffyhand.agent.llm.specs.models import AssistantMessage, SystemMessage, UserMessage
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
        assert runtime.get_state("nonexistent") is None


class TestStateProperty:
    def test_setter_and_getter(self, runtime):
        state = AgentState(
            messages=[SystemMessage(content="test")],
            session_id=SessionID("s1"),
            usage=SessionUsage(context_size=1000),
        )
        runtime._states["s1"] = state
        assert runtime.get_state("s1") is state

    def test_get_state_returns_none_for_missing(self, runtime):
        assert runtime.get_state("nonexistent") is None

    def test_state_with_empty_id(self, runtime):
        state = AgentState(
            messages=[],
            session_id=SessionID(""),
            usage=SessionUsage(context_size=0),
        )
        runtime._states[""] = state
        assert runtime.get_state("") is state


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
        assert "Current time:" in prompt

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
        runtime._prefs_initialized = True
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
        runtime._prefs_initialized = True
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


class TestPreferenceFileDiscovery:
    """Tests for _find_up / _find_up_all / first-match-wins in _read_preference_files."""

    def test_find_up_finds_closest_ancestor(self, runtime, tmp_path):
        """_find_up returns the first AGENTS.md when walking upward."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        md = outer / "AGENTS.md"
        md.write_text("outer rules")
        found = runtime._find_up("AGENTS.md", start=inner, stop=tmp_path)
        assert found is not None
        assert found == md

    def test_find_up_stops_at_stop_dir(self, runtime, tmp_path):
        """_find_up does not search past the stop directory."""
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)
        md = tmp_path / "AGENTS.md"  # above stop boundary
        md.write_text("should not be found")
        found = runtime._find_up("AGENTS.md", start=child, stop=parent)
        assert found is None

    def test_find_up_returns_none_when_missing(self, runtime, tmp_path):
        found = runtime._find_up("AGENTS.md", start=tmp_path, stop=tmp_path)
        assert found is None

    def test_find_up_uses_cwd_default(self, runtime):
        """_find_up with no args searches from CWD."""
        with patch("os.getcwd", return_value="/nonexistent"):
            found = runtime._find_up("AGENTS.md")
        assert found is None  # /nonexistent doesn't have AGENTS.md

    def test_find_up_all_collects_multiple_matches(self, runtime, tmp_path):
        """_find_up_all collects all AGENTS.md files walking upward."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        outer_md = outer / "AGENTS.md"
        outer_md.write_text("outer")
        inner_md = inner / "AGENTS.md"
        inner_md.write_text("inner")
        found = runtime._find_up_all("AGENTS.md", start=inner, stop=tmp_path)
        assert len(found) == 2
        assert inner_md in found
        assert outer_md in found

    def test_read_preference_files_first_match_wins_project(self, runtime, tmp_path):
        """_read_preference_files prefers project-level AGENTS.md over home."""
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("project rules")
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            result = runtime._read_preference_files()
        assert len(result) == 1
        assert str(agents_md) in result
        assert "project rules" in result[str(agents_md)]

    def test_read_preference_files_fallback_to_home(self, runtime, tmp_path):
        """When no project AGENTS.md, fall back to home directory."""
        home = tmp_path / "home"
        home.mkdir()
        home_md = home / "AGENTS.md"
        home_md.write_text("home rules")
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value=str(home)),
        ):
            result = runtime._read_preference_files()
        assert len(result) == 1
        assert str(home_md) in result
        assert "home rules" in result[str(home_md)]

    def test_read_preference_files_project_wins_over_home(self, runtime, tmp_path):
        """Project-level AGENTS.md wins (first-match), home is not loaded."""
        home = tmp_path / "home"
        home.mkdir()
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("project rules")
        home_md = home / "AGENTS.md"
        home_md.write_text("home rules")
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value=str(home)),
        ):
            result = runtime._read_preference_files()
        assert len(result) == 1, "Only project-level should be loaded"
        assert str(agents_md) in result
        assert str(home_md) not in result

    @pytest.mark.anyio
    async def test_poll_uses_first_match_wins(self, runtime, tmp_path):
        """poll_new_preferences uses the same first-match-wins logic."""
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("project rule")
        runtime._preferences = None
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            await runtime._load_preferences()
        agents_md.write_text("changed project rule")
        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("os.path.expanduser", return_value="/nonexistent"),
        ):
            result = await runtime.poll_new_preferences()
        assert "changed project rule" in result
        assert len(runtime._preference_files) == 1


class TestPreferenceResolution:
    """Tests for resolve_preferences / clear_preference_claims."""

    def test_resolve_preferences_walks_up_from_file(self, runtime, tmp_path):
        """resolve_preferences walks upward from the file to find AGENTS.md."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        outer_md = outer / "AGENTS.md"
        outer_md.write_text("outer project rules")
        src = inner / "src.py"
        src.write_text("code")
        instructions = runtime.resolve_preferences(
            str(src), "msg-1", root=str(tmp_path),
        )
        assert len(instructions) == 1
        assert "outer project rules" in instructions[0]["content"]

    def test_resolve_preferences_claims_prevent_duplicates(self, runtime, tmp_path):
        """Same file on same message_id not returned twice."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        outer_md = outer / "AGENTS.md"
        outer_md.write_text("rules")
        src = inner / "src.py"
        src.write_text("code")
        # First call — returns instruction
        first = runtime.resolve_preferences(str(src), "msg-1", root=str(tmp_path))
        assert len(first) == 1
        # Second call — claimed, so returns empty
        second = runtime.resolve_preferences(str(src), "msg-1", root=str(tmp_path))
        assert len(second) == 0

    def test_resolve_preferences_different_messages_separate_claims(
        self, runtime, tmp_path
    ):
        """Different message IDs get separate claims."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        outer_md = outer / "AGENTS.md"
        outer_md.write_text("rules")
        src = inner / "src.py"
        src.write_text("code")
        first = runtime.resolve_preferences(str(src), "msg-1", root=str(tmp_path))
        assert len(first) == 1
        # Different message — not claimed yet
        second = runtime.resolve_preferences(str(src), "msg-2", root=str(tmp_path))
        assert len(second) == 1

    def test_clear_preference_claims_releases_tracking(self, runtime, tmp_path):
        """After clearing claims, same message can get instructions again."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        outer_md = outer / "AGENTS.md"
        outer_md.write_text("rules")
        src = inner / "src.py"
        src.write_text("code")
        runtime.resolve_preferences(str(src), "msg-1", root=str(tmp_path))
        runtime.clear_preference_claims("msg-1")
        # After clear, same message can get instructions again
        second = runtime.resolve_preferences(str(src), "msg-1", root=str(tmp_path))
        assert len(second) == 1
    def test_creates_agent_state(self, runtime):
        sys_msg = SystemMessage(content="You are a bot.")
        state = AgentState(
            messages=[sys_msg],
            session_id=SessionID("test-sid"),
            usage=SessionUsage(context_size=runtime.context_size),
        )
        assert state.session_id is not None
        assert len(state.messages) == 1
        assert state.messages[0].content == "You are a bot."

    def test_usage_context_size_default(self, runtime):
        state = AgentState(
            messages=[SystemMessage(content="hi")],
            session_id=SessionID("test-sid"),
            usage=SessionUsage(context_size=128000),
        )
        assert state.usage.context_size == 128000


class TestCompleteSession:
    def test_completes_session(self, runtime, session_manager):
        session = session_manager.create()
        runtime.session_manager.complete(session.id)
        fetched = session_manager.get(session.id)
        assert fetched is not None
        assert fetched.status == "completed"

    def test_noop_for_nonexistent(self, runtime):
        runtime.session_manager.complete("nonexistent")


class TestLoadSessionState:
    def test_loads_existing_session(self, runtime, session_manager):
        session = session_manager.create(messages=[UserMessage(content="hi")])
        result = runtime.load_session_state(session.id)
        assert result is not None
        assert result.session_id == session.id

    def test_switches_to_in_memory_state(self, runtime):
        """Session in _states but not in DB can still be loaded."""
        state = AgentState(
            messages=[SystemMessage(content="in-memory only")],
            session_id=SessionID("mem-sess"),
            usage=SessionUsage(context_size=0),
        )
        runtime._states["mem-sess"] = state
        result = runtime.load_session_state("mem-sess")
        assert result is state

    def test_returns_none_for_nonexistent(self, runtime):
        result = runtime.load_session_state("nonexistent")
        assert result is None

    def test_load_session_via_states(self, runtime):
        """State in _states is returned directly by load_session_state."""
        session_id = "sess-from-state"
        state = AgentState(
            messages=[SystemMessage(content="state flow")],
            session_id=SessionID(session_id),
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session_id] = state

        result = runtime.load_session_state(session_id)
        assert result is state
        assert runtime.get_state(session_id) is state

    def test_load_session_state_repeated_calls(self, runtime, session_manager):
        """load_session_state can be called multiple times with the same id."""
        from laffyhand.agent.session.models import Session as SessionModel

        session = SessionModel(provider="test", model="test")
        state = AgentState(
            messages=[SystemMessage(content="system prompt")],
            session_id=SessionID(session.id),
            usage=SessionUsage(context_size=0),
        )
        runtime.session_manager.set_pending_meta(session.id, title="", cwd="", provider="", model="", agent_version="build")
        runtime._states[session.id] = state

        assert runtime.load_session_state(session.id) is state
        assert runtime.load_session_state(session.id) is state

        other = session_manager.create(messages=[UserMessage(content="other")])
        other_state = AgentState(messages=[], session_id=SessionID(other.id), usage=SessionUsage(context_size=0))
        runtime._states[other.id] = other_state
        assert runtime.load_session_state(other.id) is other_state
        assert runtime.load_session_state(session.id) is state


class TestForkSession:
    def test_forks_current_session(self, runtime, session_manager):
        session = session_manager.create(messages=[UserMessage(content="hi")])
        state = AgentState(
            messages=[SystemMessage(content="test")],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state
        child_id = runtime.fork_session(session.id)
        assert child_id is not None
        assert child_id != session.id
        assert runtime._states[child_id].session_id == child_id

    def test_returns_none_when_no_state(self, runtime):
        result = runtime.fork_session("nonexistent")
        assert result is None

    def test_returns_none_without_valid_session_id(self, runtime):
        state = AgentState(
            messages=[],
            session_id=SessionID(""),
            usage=SessionUsage(context_size=0),
        )
        runtime._states[""] = state
        result = runtime.fork_session("")
        assert result is None


class TestAddMcpServer:
    @pytest.mark.anyio
    async def test_adds_and_registers_tools(self, runtime):
        from laffyhand.agent.mcp.config import LocalMCPConfig

        cfg = LocalMCPConfig(command=["echo", "hello"])
        tool_def = MagicMock()
        tool_def.name = "greet"
        tool_def.description = "Greet someone"
        tool_def.input_schema = {"type": "object", "properties": {}}
        runtime.mcp_service.connect_server = AsyncMock(return_value=[tool_def])

        tool_names = await runtime.add_mcp_server("test-server", cfg)
        assert len(tool_names) == 1
        assert tool_names[0] == "mcp_test-server_greet"
        runtime.mcp_service.connect_server.assert_awaited_once_with("test-server", cfg)
        registered = runtime.tool_registry.list_tools()
        assert "mcp_test-server_greet" in registered

    @pytest.mark.anyio
    async def test_raises_on_connection_failure(self, runtime):
        from laffyhand.agent.mcp.config import LocalMCPConfig

        cfg = LocalMCPConfig(command=["invalid-command"])
        runtime.mcp_service.connect_server = AsyncMock(
            side_effect=RuntimeError("connection failed")
        )
        with pytest.raises(RuntimeError):
            await runtime.add_mcp_server("bad-server", cfg)


class TestRemoveMcpServer:
    @pytest.mark.anyio
    async def test_unregisters_tools_and_disconnects(self, runtime):
        from laffyhand.agent.mcp.config import LocalMCPConfig

        runtime.mcp_service.disconnect = AsyncMock()
        tool_def = MagicMock()
        tool_def.name = "greet"
        tool_def.description = "Greet"
        tool_def.input_schema = {"type": "object", "properties": {}}
        runtime.mcp_service.connect_server = AsyncMock(return_value=[tool_def])
        cfg = LocalMCPConfig(command=["echo"])
        await runtime.add_mcp_server("test-server", cfg)
        assert "mcp_test-server_greet" in runtime.tool_registry.list_tools()

        count = await runtime.remove_mcp_server("test-server")
        assert count == 1
        assert "mcp_test-server_greet" not in runtime.tool_registry.list_tools()
        runtime.mcp_service.disconnect.assert_awaited_once_with("test-server")

    @pytest.mark.anyio
    async def test_noop_for_nonexistent(self, runtime):
        runtime.mcp_service.disconnect = AsyncMock()
        count = await runtime.remove_mcp_server("nonexistent-server")
        assert count == 0
        runtime.mcp_service.disconnect.assert_awaited_once_with("nonexistent-server")


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
        agent_info = AgentInfo(name="test", system_prompt="You are test.")
        with patch.object(
            session_manager, "get_depth", return_value=MAX_SUBAGENT_DEPTH + 1
        ):
            result = await runtime.create_subagent(session.id, agent_info, "Do it")
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
        agent_info = AgentInfo(name="test", system_prompt="You are test.")

        with patch("laffyhand.agent.runtime.agent_loop") as mock_loop:

            async def mock_agent_loop(*args, **kwargs):
                child_state = args[0]
                child_state.messages.append(
                    AssistantMessage(content="final answer")
                )
                from laffyhand.agent.schemas import StepFinish

                yield StepFinish(index=1, reason="stop")

            mock_loop.side_effect = mock_agent_loop

            result = await runtime.create_subagent(session.id, agent_info, "Do the task")

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
        agent_info = AgentInfo(name="test", system_prompt="You are test.")

        with patch("laffyhand.agent.runtime.agent_loop") as mock_loop:

            async def mock_agent_loop(*args, **kwargs):
                from laffyhand.agent.schemas import StepFinish

                yield StepFinish(index=1, reason="stop")

            mock_loop.side_effect = mock_agent_loop

            result = await runtime.create_subagent(session.id, agent_info, "Do it")
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
        agent_info = AgentInfo(name="test", system_prompt="You are test.")

        with patch.object(
            runtime.subagent_manager, "spawn", new_callable=AsyncMock
        ) as mock_spawn:
            mock_spawn.return_value = "abc123def456"
            result = await runtime.create_subagent(
                session.id,
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
        agent_info = AgentInfo(name="test", system_prompt="You are test.")

        with patch.object(
            runtime.subagent_manager, "spawn", new_callable=AsyncMock
        ) as mock_spawn:
            await runtime.create_subagent(session.id, agent_info, "Do it", background=True)
            _call_session = mock_spawn.call_args[1]["session_manager"]
            _call_compaction = mock_spawn.call_args[1]["compaction_config"]
            assert _call_session is runtime.session_manager
            assert _call_compaction is runtime.compaction_config


class TestGenerateTitleForCurrent:
    @pytest.mark.anyio
    async def test_generates_title(self, runtime, session_manager):
        session = session_manager.create(messages=[UserMessage(content="Hello")])
        state = AgentState(
            messages=[UserMessage(content="Hello")],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        runtime._states[session.id] = state

        with patch(
            "laffyhand.agent.title.generate_title", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = "My Title"
            result = await runtime._do_generate_title(session.id)
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
        runtime.mcp_service.disconnect_all = AsyncMock()
        await runtime.shutdown()
        runtime.mcp_service.disconnect_all.assert_awaited_once()
        assert runtime.session_manager is not None
