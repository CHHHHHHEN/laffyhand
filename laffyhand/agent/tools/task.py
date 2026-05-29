from __future__ import annotations

from typing import TYPE_CHECKING, Any

from laffyhand.agent.schemas import (
    AgentState, CompactionConfig, SessionUsage, SystemMessage, UserMessage,
)
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.permission import PermissionManager

if TYPE_CHECKING:
    from laffyhand.agent.agent import AgentInfo, AgentRegistry
    from laffyhand.agent.llm.facade import LLM
    from laffyhand.agent.session.manager import SessionManager
    from laffyhand.agent.tools.registry import ToolRegistry


class SubagentPermissions:
    @staticmethod
    def compose(
        parent_permission: PermissionManager,
        agent_permission: dict[str, Any],
        parent_session_permission: PermissionManager | None = None,
    ) -> PermissionManager:
        combined = PermissionManager()
        for name, rule in parent_permission._rules.items():
            if rule == "allow":
                combined.allow(name)
            else:
                combined.deny(name)
        agent_deny = set(agent_permission.get("deny", []))
        for name in agent_deny:
            combined.deny(name)
        if parent_session_permission is not None:
            for name, rule in parent_session_permission._rules.items():
                if rule == "deny":
                    combined.deny(name)
        return combined

    @staticmethod
    def filter_registry(
        registry: ToolRegistry,
        permission: PermissionManager,
    ) -> ToolRegistry:
        filtered = ToolRegistry(permission=permission)
        for name, tool in registry._tools.items():
            if name == "task":
                continue
            if permission.check(name):
                filtered.register_tool(tool)
        return filtered


MAX_SUBAGENT_DEPTH = 3


class TaskTool(BaseTool):
    name = "task"
    description = "Delegate a task to a specialized sub-agent"

    def __init__(
        self,
        agent_registry: AgentRegistry,
        llm: LLM,
        session_manager: SessionManager,
        tool_registry: ToolRegistry,
        parent_session_id: str,
        parent_permission: PermissionManager,
        compaction_config: CompactionConfig | None = None,
        subagent_manager: Any | None = None,
    ) -> None:
        self._agent_registry = agent_registry
        self._llm = llm
        self._session_manager = session_manager
        self._tool_registry = tool_registry
        self._parent_session_id = parent_session_id
        self._parent_permission = parent_permission
        self._compaction_config = compaction_config or CompactionConfig()
        self._subagent_manager = subagent_manager

    def _input_schema(self) -> dict:
        agents = self._agent_registry.list_subagents()
        enum_agents = [a.name for a in agents]
        return {
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

    async def run(self, params: dict[str, Any]) -> str:
        subagent_type = params["subagent_type"]
        prompt = params["prompt"]
        description = params.get("description", "")
        background = params.get("background", False)

        agent_info = self._agent_registry.get(subagent_type)
        if agent_info is None:
            return f"Error: unknown sub-agent '{subagent_type}'"

        depth = self._session_manager.get_depth(self._parent_session_id)
        if depth > MAX_SUBAGENT_DEPTH:
            return (
                f"Error: maximum sub-agent depth ({MAX_SUBAGENT_DEPTH}) exceeded. "
                "Cannot spawn further sub-agents."
            )

        if background:
            if self._subagent_manager is None:
                return "Error: background execution not available"
            return await self._run_background(agent_info, prompt, description)

        return await self._run_foreground(agent_info, prompt, description)

    async def _run_foreground(
        self,
        agent_info: AgentInfo,
        prompt: str,
        description: str,
    ) -> str:
        child_session = self._session_manager.create_child(
            parent_id=self._parent_session_id,
            model=agent_info.model or "",
        )

        system_content = (
            agent_info.prompt
            or "You are a helpful sub-agent. Complete the assigned task."
        )
        system_msg = SystemMessage(content=system_content)
        user_msg = UserMessage(content=prompt)

        child_permission = SubagentPermissions.compose(
            self._parent_permission,
            agent_info.permission,
        )
        child_registry = SubagentPermissions.filter_registry(
            self._tool_registry, child_permission,
        )

        child_state = AgentState(
            messages=[system_msg, user_msg],
            session_id=child_session.id,
            usage=SessionUsage(context_size=0),
        )

        from laffyhand.agent.loop import agent_loop

        result_parts: list[str] = []
        async for event in agent_loop(
            child_state,
            self._llm,
            child_registry,
            compaction_config=CompactionConfig(
                tail_turns=self._compaction_config.tail_turns,
            ),
            max_steps=agent_info.max_steps,
            session_manager=self._session_manager,
        ):
            if event.type == "content" and event.finish_reason is not None:
                last_msg = child_state.messages[-1]
                if isinstance(last_msg, SystemMessage):
                    pass
                elif hasattr(last_msg, "content") and last_msg.content:
                    result_parts.append(last_msg.content)

        self._session_manager.save_state(child_session.id, child_state)
        self._session_manager.complete(child_session.id)

        result = "\n".join(part for part in result_parts if part).strip()
        if not result:
            result = "[No output]"
        return f"<task>\n{result}\n</task>"

    async def _run_background(
        self,
        agent_info: AgentInfo,
        prompt: str,
        description: str,
    ) -> str:
        assert self._subagent_manager is not None
        task_id: str = await self._subagent_manager.spawn(  # type: ignore[assignment]
            parent_session_id=self._parent_session_id,
            agent_info=agent_info,
            prompt=prompt,
            llm=self._llm,
            tool_registry=self._tool_registry,
            parent_permission=self._parent_permission,
            compaction_config=self._compaction_config,
        )
        return f"Sub-agent [{agent_info.name}] started (id: {task_id[:8]}). I'll notify you when it completes."
