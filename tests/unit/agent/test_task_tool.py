from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock

import pytest

from laffyhand.agent.agent import AgentInfo, AgentRegistry
from laffyhand.agent.tools.task import TaskTool


@pytest.fixture
def runtime():
    rt = MagicMock()
    rt.agent_registry = AgentRegistry()
    rt.create_subagent = AsyncMock()
    return rt


@pytest.fixture
def task_tool(runtime):
    return TaskTool(runtime=runtime)


class TestTaskTool:
    @pytest.mark.anyio
    async def test_run_calls_create_subagent(self, task_tool, runtime):
        runtime.create_subagent.return_value = "<task>\nDone\n</task>"
        result = await task_tool.run({
            "subagent_type": "explore",
            "prompt": "Find the main function",
        })
        assert result == "<task>\nDone\n</task>"
        agent = runtime.agent_registry.get("explore")
        runtime.create_subagent.assert_awaited_once_with(
            agent, "Find the main function",
            description="", background=False,
        )

    @pytest.mark.anyio
    async def test_run_with_background(self, task_tool, runtime):
        runtime.create_subagent.return_value = "Sub-agent started"
        result = await task_tool.run({
            "subagent_type": "general",
            "prompt": "Do something",
            "background": True,
        })
        assert result == "Sub-agent started"
        agent = runtime.agent_registry.get("general")
        runtime.create_subagent.assert_awaited_once_with(
            agent, "Do something",
            description="", background=True,
        )

    @pytest.mark.anyio
    async def test_run_with_description(self, task_tool, runtime):
        runtime.create_subagent.return_value = "<task>ok</task>"
        result = await task_tool.run({
            "subagent_type": "build",
            "prompt": "Fix the bug",
            "description": "Fix bug",
        })
        agent = runtime.agent_registry.get("build")
        runtime.create_subagent.assert_awaited_once_with(
            agent, "Fix the bug",
            description="Fix bug", background=False,
        )

    @pytest.mark.anyio
    async def test_unknown_agent_returns_error(self, task_tool, runtime):
        result = await task_tool.run({
            "subagent_type": "nonexistent",
            "prompt": "Do something",
        })
        assert "unknown sub-agent" in result.lower()
        runtime.create_subagent.assert_not_called()

    def test_input_schema_includes_agent_enum(self, task_tool):
        schema = task_tool._input_schema()
        assert schema["type"] == "object"
        props = schema["properties"]
        assert "subagent_type" in props
        assert "prompt" in props
        assert "description" in props
        assert "background" in props
        assert schema["required"] == ["subagent_type", "prompt"]

    def test_input_schema_enum_contains_subagents(self, task_tool):
        schema = task_tool._input_schema()
        enum = schema["properties"]["subagent_type"]["enum"]
        subagent_names = {a.name for a in task_tool._runtime.agent_registry.list_subagents()}
        for name in subagent_names:
            assert name in enum

    def test_input_schema_background_default_false(self, task_tool):
        schema = task_tool._input_schema()
        bg = schema["properties"]["background"]
        assert bg.get("default") is False

    def test_name_and_description(self, task_tool):
        assert task_tool.name == "task"
        assert "sub-agent" in task_tool.description
