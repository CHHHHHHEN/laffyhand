from __future__ import annotations

from typing import TYPE_CHECKING, Any

from laffyhand.agent.tools.base import BaseTool

if TYPE_CHECKING:
    from laffyhand.agent.runtime import AgentRuntime


class TaskTool(BaseTool):
    name = "task"
    description = "Delegate a task to a specialized sub-agent"

    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime
        self._cached_schema: dict | None = None

    def _input_schema(self) -> dict:
        if self._cached_schema is not None:
            return self._cached_schema
        agents = self._runtime.agent_registry.list_subagents()
        enum_agents = [a.name for a in agents]
        schema = {
            "type": "object",
            "properties": {
                "subagent_type": {
                    "type": "string",
                    "enum": enum_agents,
                    "description": "Which sub-agent to delegate to. "
                    + " ".join(f"{a.name}: {a.description}" for a in agents),
                },
                "prompt": {
                    "type": "string",
                    "description": "Detailed task description for the sub-agent",
                },
                "description": {
                    "type": "string",
                    "description": "Short 3-5 word summary of the task",
                },
                "background": {
                    "type": "boolean",
                    "description": "Run in background (non-blocking)",
                    "default": False,
                },
            },
            "required": ["subagent_type", "prompt"],
        }
        self._cached_schema = schema
        return schema

    async def run(self, params: dict[str, Any]) -> str:
        subagent_type = params["subagent_type"]
        prompt = params["prompt"]
        description = params.get("description", "")
        background = params.get("background", False)

        agent_info = self._runtime.agent_registry.get(subagent_type)
        if agent_info is None:
            return f"Error: unknown sub-agent '{subagent_type}'"

        return await self._runtime.create_subagent(
            agent_info, prompt, description=description, background=background,
        )
