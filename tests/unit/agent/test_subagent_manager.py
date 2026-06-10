from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock

import pytest

from laffyhand.core.agent import AgentInfo
from laffyhand.core.llm.specs.models import SystemMessage, UserMessage
from laffyhand.core.subagent._shared import (
    build_subagent_state,
)
from laffyhand.core.tools.permission import PermissionManager
from laffyhand.core.tools.registry import ToolRegistry


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
    pm.add_rule("read", "allow")
    pm.add_rule("write", "allow")
    return pm


@pytest.fixture
def agent_info():
    return AgentInfo(
        name="test-agent",
        description="A test sub-agent",
        system_prompt="You are a test agent.",
        permission={"deny": ["write"]},
    )


class TestBuildSubagentState:
    @pytest.mark.anyio
    async def test_creates_child_session(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        parent = session_manager.create()
        child_state, child_registry = await build_subagent_state(
            session_manager,
            parent.id,
            agent_info,
            "Do the thing",
            parent_permission,
            tool_registry,
        )
        assert child_state.session_id is not None
        assert child_state.session_id != parent.id

    @pytest.mark.anyio
    async def test_state_contains_system_and_user_messages(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        parent = session_manager.create()
        child_state, _ = await build_subagent_state(
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

    @pytest.mark.anyio
    async def test_default_prompt_when_none(
        self, session_manager, tool_registry, parent_permission
    ):
        info = AgentInfo(name="minimal", system_prompt="")
        parent = session_manager.create()
        child_state, _ = await build_subagent_state(
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

    @pytest.mark.anyio
    async def test_permission_filters_registry(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        parent = session_manager.create()
        _, child_registry = await build_subagent_state(
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

    @pytest.mark.anyio
    async def test_task_tool_not_in_filtered_registry(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        from laffyhand.core.tools.task import TaskTool

        task_tool = MagicMock(spec=TaskTool)
        task_tool.name = "task"
        tool_registry.register_tool(task_tool)
        parent = session_manager.create()
        _, child_registry = await build_subagent_state(
            session_manager,
            parent.id,
            agent_info,
            "task",
            parent_permission,
            tool_registry,
        )
        assert child_registry._tools.get("task") is None

    @pytest.mark.anyio
    async def test_session_usage_zero_context(
        self, session_manager, tool_registry, parent_permission, agent_info
    ):
        parent = session_manager.create()
        child_state, _ = await build_subagent_state(
            session_manager,
            parent.id,
            agent_info,
            "task",
            parent_permission,
            tool_registry,
        )
        assert child_state.usage.context_size == 0
