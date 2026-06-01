from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock

import pytest

from laffyhand.agent.schemas import ToolCallContent, ToolMessage
from laffyhand.agent.tool_executor import ToolExecutor, ToolExecutionResult


class TestToolExecutionResult:
    def test_dataclass_fields(self):
        msg = ToolMessage(tool_call_id="c1", content="result")
        result = ToolExecutionResult(message=msg, event_data="result", is_error=False)
        assert result.message == msg
        assert result.event_data == "result"
        assert result.is_error is False

    def test_error_result(self):
        msg = ToolMessage(tool_call_id="c1", content="error")
        result = ToolExecutionResult(
            message=msg, event_data="Error: bad", is_error=True
        )
        assert result.is_error is True


class TestToolExecutor:
    @pytest.mark.anyio
    async def test_successful_execution(self):
        registry = MagicMock()
        registry.run_tool = AsyncMock(return_value="tool result")
        tool_call = ToolCallContent(
            tool_call_id="tc1",
            tool_name="my_tool",
            args='{"key": "val"}',
        )

        result = await ToolExecutor.execute(registry, tool_call)

        assert result.is_error is False
        assert result.event_data == "tool result"
        assert isinstance(result.message, ToolMessage)
        assert result.message.tool_call_id == "tc1"
        assert result.message.content == "tool result"
        registry.run_tool.assert_awaited_once_with("my_tool", {"key": "val"})

    @pytest.mark.anyio
    async def test_invalid_json_returns_error(self):
        registry = MagicMock()
        registry.run_tool = AsyncMock()
        tool_call = ToolCallContent(
            tool_call_id="tc1",
            tool_name="my_tool",
            args="not valid json",
        )

        result = await ToolExecutor.execute(registry, tool_call)

        assert result.is_error is True
        assert "invalid JSON args" in result.event_data
        assert "failed to parse tool arguments" in result.message.content
        assert result.message.tool_call_id == "tc1"
        registry.run_tool.assert_not_called()

    @pytest.mark.anyio
    async def test_empty_args(self):
        registry = MagicMock()
        registry.run_tool = AsyncMock(return_value="ok")
        tool_call = ToolCallContent(
            tool_call_id="tc2",
            tool_name="empty_args",
            args="{}",
        )

        result = await ToolExecutor.execute(registry, tool_call)

        assert result.is_error is False
        assert result.message.content == "ok"
        registry.run_tool.assert_awaited_once_with("empty_args", {})

    @pytest.mark.anyio
    async def test_truncated_args_in_warning(self):
        registry = MagicMock()
        registry.run_tool = AsyncMock()
        long_args = "x" * 500
        tool_call = ToolCallContent(
            tool_call_id="tc3",
            tool_name="big",
            args=long_args,
        )

        await ToolExecutor.execute(registry, tool_call)

        registry.run_tool.assert_not_called()
