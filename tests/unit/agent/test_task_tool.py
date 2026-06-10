from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from laffyhand.core.agent import AgentRegistry
from laffyhand.core.tools.task import TaskTool


@pytest.fixture
def agent_registry():
    return AgentRegistry()


@pytest.fixture
def orchestrator(agent_registry):
    orch = AsyncMock()
    orch.create_subagent = AsyncMock()
    return orch


@pytest.fixture
def task_tool(agent_registry, orchestrator):
    return TaskTool(agent_registry=agent_registry, orchestrator=orchestrator)


class TestTaskTool:
    @pytest.mark.anyio
    async def test_run_calls_create_subagent(self, task_tool, agent_registry, orchestrator):
        orchestrator.create_subagent.return_value = "<task>\nDone\n</task>"
        result = await task_tool.run(
            {
                "subagent_type": "explore",
                "prompt": "Find the main function",
                "session_id": "session-123",
            }
        )
        assert result == "<task>\nDone\n</task>"
        agent = agent_registry.get("explore")
        orchestrator.create_subagent.assert_awaited_once_with(
            "session-123",
            agent,
            "Find the main function",
            description="",
            todo_id=None,
        )

    @pytest.mark.anyio
    async def test_run_with_description(self, task_tool, agent_registry, orchestrator):
        orchestrator.create_subagent.return_value = "<task>ok</task>"
        await task_tool.run(
            {
                "subagent_type": "build",
                "prompt": "Fix the bug",
                "description": "Fix bug",
                "session_id": "session-123",
            }
        )
        agent = agent_registry.get("build")
        orchestrator.create_subagent.assert_awaited_once_with(
            "session-123",
            agent,
            "Fix the bug",
            description="Fix bug",
            todo_id=None,
        )

    @pytest.mark.anyio
    async def test_unknown_agent_returns_error(self, task_tool, orchestrator):
        result = await task_tool.run(
            {
                "subagent_type": "nonexistent",
                "prompt": "Do something",
                "session_id": "session-123",
            }
        )
        assert "unknown sub-agent" in result.lower()
        orchestrator.create_subagent.assert_not_called()

    def test_input_schema_includes_agent_enum(self, task_tool):
        schema = task_tool._input_schema()
        assert schema["type"] == "object"
        props = schema["properties"]
        assert "subagent_type" in props
        assert "prompt" in props
        assert "description" in props
        assert schema["required"] == ["subagent_type", "prompt"]

    def test_input_schema_enum_contains_subagents(self, task_tool):
        schema = task_tool._input_schema()
        enum = schema["properties"]["subagent_type"]["enum"]
        subagent_names = {
            a.name for a in task_tool._agent_registry.list_subagents()
        }
        for name in subagent_names:
            assert name in enum

    def test_name_and_description(self, task_tool):
        assert task_tool.name == "task"
        assert "sub-agent" in task_tool.description

    def test_timeout_is_zero(self, task_tool):
        assert task_tool.timeout == 0
