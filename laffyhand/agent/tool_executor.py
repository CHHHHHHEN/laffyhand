from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from laffyhand.agent.schemas import ToolCallContent, ToolMessage

if TYPE_CHECKING:
    from laffyhand.agent.tools.registry import ToolRegistry


@dataclass
class ToolExecutionResult:
    message: ToolMessage
    event_data: str
    is_error: bool


class ToolExecutor:
    @staticmethod
    async def execute(
        tool_registry: ToolRegistry,
        tool_call: ToolCallContent,
    ) -> ToolExecutionResult:
        try:
            params = json.loads(tool_call.args)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse tool args for {tool_call.tool_name}: {tool_call.args[:200]}")
            return ToolExecutionResult(
                message=ToolMessage(
                    tool_call_id=tool_call.tool_call_id,
                    content=f"Error: failed to parse tool arguments for {tool_call.tool_name}: {tool_call.args}",
                ),
                event_data=f"Error: invalid JSON args for {tool_call.tool_name}",
                is_error=True,
            )

        try:
            result = await tool_registry.run_tool(tool_call.tool_name, params)
        except Exception as e:
            logger.exception(f"Tool execution failed for {tool_call.tool_name}: {e}")
            return ToolExecutionResult(
                message=ToolMessage(
                    tool_call_id=tool_call.tool_call_id,
                    content=f"Error executing tool {tool_call.tool_name}: {e}",
                ),
                event_data=f"Error: {tool_call.tool_name} failed: {e}",
                is_error=True,
            )

        return ToolExecutionResult(
            message=ToolMessage(
                tool_call_id=tool_call.tool_call_id,
                content=result,
            ),
            event_data=result,
            is_error=False,
        )
