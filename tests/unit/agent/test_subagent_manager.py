from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from laffyhand.agent.agent import AgentInfo
from laffyhand.agent.llm.specs.models import SystemMessage, UserMessage
from laffyhand.agent.schemas import (
    AgentState,
    SessionID,
    SessionUsage,
)
from laffyhand.agent.subagent.manager import (
    SubagentManager,
    SubagentResult,
    build_subagent_state,
)
from laffyhand.agent.tools.permission import PermissionManager
from laffyhand.agent.tools.registry import ToolRegistry


@pytest.fixture
def tool_registry():
    reg = ToolRegistry()
    dummy = MagicMock()
    dummy.name = "read"
    dummy.to_definition = MagicMock(return_value=MagicMock())
    dummy.run = AsyncMock(return_value="ok")
    reg.register_tool(dummy)
    dummy2 = MagicMock()
    dummy2.name = "write"
    dummy2.to_definition = MagicMock(return_value=MagicMock())
    dummy2.run = AsyncMock(return_value="ok")
    reg.register_tool(dummy2)
    return reg


@pytest.fixture
def parent_permission():
    pm = PermissionManager()
    pm.allow("read")
    pm.allow("write")
    return pm


@pytest.fixture
def agent_info():
    return AgentInfo(
        name="test-agent",
        description="A test sub-agent",
        system_prompt="You are a test agent.",
        permission={"deny": ["write"]},
    )


@pytest.fixture
def subagent_manager():
    return SubagentManager(max_concurrent=2)


class TestSubagentResult:
    def test_default_content(self):
        r = SubagentResult(
            task_id="t1",
            session_id="s1",
            parent_session_id="p1",
            agent_type="test",
            status="completed",
        )
        assert r.content == ""
        assert r.error == ""

    def test_error_status(self):
        r = SubagentResult(
            task_id="t1",
            session_id="s1",
            parent_session_id="p1",
            agent_type="test",
            status="error",
            error="Something broke",
        )
        assert r.status == "error"
        assert r.error == "Something broke"


class TestBuildSubagentState:
    def test_creates_child_session(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        parent = session_manager.create()
        child_state, child_registry = build_subagent_state(
            session_manager,
            parent.id,
            agent_info,
            "Do the thing",
            parent_permission,
            tool_registry,
        )
        assert child_state.session_id is not None
        assert child_state.session_id != parent.id

    def test_state_contains_system_and_user_messages(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        parent = session_manager.create()
        child_state, _ = build_subagent_state(
            session_manager,
            parent.id,
            agent_info,
            "Do the thing",
            parent_permission,
            tool_registry,
        )
        assert len(child_state.messages) == 2
        assert isinstance(child_state.messages[0], SystemMessage)
        assert "You are a test agent." in child_state.messages[0].content
        assert "<soul>" in child_state.messages[0].content
        assert "<env>" in child_state.messages[0].content
        assert "Workspace:" in child_state.messages[0].content
        assert "<tools>" in child_state.messages[0].content
        assert isinstance(child_state.messages[1], UserMessage)
        assert child_state.messages[1].content == "Do the thing"

    def test_default_prompt_when_none(
        self, session_manager, tool_registry, parent_permission
    ):
        info = AgentInfo(name="minimal", system_prompt="")
        parent = session_manager.create()
        child_state, _ = build_subagent_state(
            session_manager,
            parent.id,
            info,
            "task",
            parent_permission,
            tool_registry,
        )
        assert "helpful sub-agent" in child_state.messages[0].content
        assert "<env>" in child_state.messages[0].content
        assert "<tools>" in child_state.messages[0].content

    def test_permission_filters_registry(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        parent = session_manager.create()
        _, child_registry = build_subagent_state(
            session_manager,
            parent.id,
            agent_info,
            "task",
            parent_permission,
            tool_registry,
        )
        # "read" is allowed, "write" is denied by agent_info.permission
        assert child_registry.permission.check("read") is True
        assert child_registry.permission.check("write") is False

    def test_task_tool_not_in_filtered_registry(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        from laffyhand.agent.tools.task import TaskTool

        task_tool = MagicMock(spec=TaskTool)
        task_tool.name = "task"
        tool_registry.register_tool(task_tool)
        parent = session_manager.create()
        _, child_registry = build_subagent_state(
            session_manager,
            parent.id,
            agent_info,
            "task",
            parent_permission,
            tool_registry,
        )
        assert child_registry._tools.get("task") is None

    def test_session_usage_zero_context(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        parent = session_manager.create()
        child_state, _ = build_subagent_state(
            session_manager,
            parent.id,
            agent_info,
            "task",
            parent_permission,
            tool_registry,
        )
        assert child_state.usage.context_size == 0


class TestSubagentManager:
    @pytest.mark.anyio
    async def test_active_count_starts_zero(self, subagent_manager):
        assert subagent_manager.active_count() == 0

    @pytest.mark.anyio
    async def test_active_count_by_session(self, subagent_manager):
        assert subagent_manager.active_count("sess1") == 0

    @pytest.mark.anyio
    async def test_list_active_empty_session(self, subagent_manager):
        assert subagent_manager.list_active("nonexistent") == []

    @pytest.mark.anyio
    async def test_spawn_returns_task_id(
        self,
        subagent_manager,
        session_manager,
        tool_registry,
        parent_permission,
        agent_info,
    ):
        parent = session_manager.create()
        llm = MagicMock()

        with patch(
            "laffyhand.agent.subagent.manager.build_subagent_state"
        ) as mock_build:
            mock_build.return_value = (
                AgentState(
                    messages=[],
                    session_id=SessionID("child-session"),
                    usage=SessionUsage(context_size=0),
                ),
                tool_registry,
            )
            task_id = await subagent_manager.spawn(
                parent_session_id=parent.id,
                agent_info=agent_info,
                prompt="Do it",
                llm=llm,
                tool_registry=tool_registry,
                parent_permission=parent_permission,
                session_manager=session_manager,
            )
        assert isinstance(task_id, str)
        assert len(task_id) == 12

    @pytest.mark.anyio
    async def test_spawn_registers_task(
        self,
        subagent_manager,
        session_manager,
        tool_registry,
        parent_permission,
        agent_info,
    ):
        parent = session_manager.create()
        llm = MagicMock()

        with patch(
            "laffyhand.agent.subagent.manager.build_subagent_state"
        ) as mock_build:
            mock_build.return_value = (
                AgentState(
                    messages=[],
                    session_id=SessionID("child-session"),
                    usage=SessionUsage(context_size=0),
                ),
                tool_registry,
            )
            task_id = await subagent_manager.spawn(
                parent_session_id=parent.id,
                agent_info=agent_info,
                prompt="Do it",
                llm=llm,
                tool_registry=tool_registry,
                parent_permission=parent_permission,
                session_manager=session_manager,
            )
        assert subagent_manager.active_count() == 1
        assert subagent_manager.active_count(parent.id) == 1
        active = subagent_manager.list_active(parent.id)
        assert len(active) == 1
        assert active[0]["task_id"] == task_id
        assert active[0]["agent_type"] == "test-agent"
        assert active[0]["status"] == "pending"

    @pytest.mark.anyio
    async def test_poll_results_empty_when_no_tasks(self, subagent_manager):
        results = await subagent_manager.poll_results("some-session")
        assert results == []

    @pytest.mark.anyio
    async def test_cancel_session_cleans_up(
        self,
        subagent_manager,
        session_manager,
        tool_registry,
        parent_permission,
        agent_info,
    ):
        parent = session_manager.create()
        llm = MagicMock()

        with patch(
            "laffyhand.agent.subagent.manager.build_subagent_state"
        ) as mock_build:
            mock_build.return_value = (
                AgentState(
                    messages=[],
                    session_id=SessionID("child-session"),
                    usage=SessionUsage(context_size=0),
                ),
                tool_registry,
            )
            await subagent_manager.spawn(
                parent_session_id=parent.id,
                agent_info=agent_info,
                prompt="Do it",
                llm=llm,
                tool_registry=tool_registry,
                parent_permission=parent_permission,
                session_manager=session_manager,
            )

        subagent_manager.cancel_session(parent.id)
        assert subagent_manager.active_count(parent.id) == 0

    @pytest.mark.anyio
    async def test_cancel_session_noop_for_empty_session(self, subagent_manager):
        subagent_manager.cancel_session("empty")
        assert subagent_manager.active_count() == 0

    @pytest.mark.anyio
    async def test_poll_results_filters_by_session(self, subagent_manager):
        r1 = SubagentResult(
            task_id="t1",
            session_id="s1",
            parent_session_id="session-a",
            agent_type="test",
            status="completed",
            content="done",
        )
        r2 = SubagentResult(
            task_id="t2",
            session_id="s2",
            parent_session_id="session-b",
            agent_type="test",
            status="completed",
            content="done",
        )
        await subagent_manager._pending_results.put(r1)
        await subagent_manager._pending_results.put(r2)

        results_a = await subagent_manager.poll_results("session-a")
        assert len(results_a) == 1
        assert results_a[0].task_id == "t1"

        results_b = await subagent_manager.poll_results("session-b")
        assert len(results_b) == 1
        assert results_b[0].task_id == "t2"

    @pytest.mark.anyio
    async def test_poll_results_max_count(self, subagent_manager):
        for i in range(10):
            r = SubagentResult(
                task_id=f"t{i}",
                session_id=f"s{i}",
                parent_session_id="session-x",
                agent_type="test",
                status="completed",
            )
            await subagent_manager._pending_results.put(r)

        results = await subagent_manager.poll_results("session-x", max_count=3)
        assert len(results) == 3

    @pytest.mark.anyio
    async def test_poll_results_non_matching_returned_to_queue(self, subagent_manager):
        r1 = SubagentResult(
            task_id="t1",
            session_id="s1",
            parent_session_id="session-a",
            agent_type="test",
            status="completed",
        )
        r2 = SubagentResult(
            task_id="t2",
            session_id="s2",
            parent_session_id="session-b",
            agent_type="test",
            status="completed",
        )
        await subagent_manager._pending_results.put(r1)
        await subagent_manager._pending_results.put(r2)

        results_a = await subagent_manager.poll_results("session-a")
        assert len(results_a) == 1

        results_b = await subagent_manager.poll_results("session-b")
        assert len(results_b) == 1
