from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from laffyhand.core.tools.base import BaseTool


class TaskParams(BaseModel):
    subagent_type: str = Field(description="Which sub-agent to delegate to")
    prompt: str = Field(description="Detailed task description for the sub-agent")
    description: str | None = Field(
        None, description="Short 3-5 word summary of the task"
    )
    todo_id: str | None = Field(
        None, description="Link to a TODO task ID (auto-updates status)"
    )


if TYPE_CHECKING:
    from laffyhand.core.agent import AgentRegistry
    from laffyhand.core.subagent.orchestrator import SubagentOrchestrator


class TaskTool(BaseTool):
    name = "task"
    description = "Delegate a task to a specialized sub-agent"
    timeout = 0

    def __init__(
        self,
        agent_registry: AgentRegistry,
        orchestrator: SubagentOrchestrator,
    ) -> None:
        self._agent_registry = agent_registry
        self._orchestrator = orchestrator
        self._cached_schema: dict[str, Any] | None = None

    def _input_schema(self) -> dict[str, Any]:
        if self._cached_schema is not None:
            return self._cached_schema
        agents = self._agent_registry.list_subagents()
        enum_agents = [a.name for a in agents]
        schema = TaskParams.model_json_schema()
        schema.pop("title", None)
        schema["properties"]["subagent_type"]["enum"] = enum_agents
        schema["properties"]["subagent_type"]["description"] = (
            "Which sub-agent to delegate to. "
            + " ".join(f"{a.name}: {a.description}" for a in agents)
        )
        self._cached_schema = schema
        return schema

    async def run(self, params: dict[str, Any]) -> str:
        subagent_type = params["subagent_type"]
        prompt = params["prompt"]
        description = params.get("description", "")
        todo_id = params.get("todo_id")

        parent_session_id = params.get("session_id", "")
        if not parent_session_id:
            return "Error: no active session"

        agent_info = self._agent_registry.get(subagent_type)
        if agent_info is None:
            return f"Error: unknown sub-agent '{subagent_type}'"

        result = await self._orchestrator.create_subagent(
            parent_session_id,
            agent_info,
            prompt,
            description=description,
            todo_id=todo_id,
        )
        return result
