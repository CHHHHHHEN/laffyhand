from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.agent.schemas import (
    AgentState, CompactionConfig, SessionUsage, SystemMessage,
)
from laffyhand.agent.agent import AgentRegistry
from laffyhand.agent.skill import SkillRegistry
from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.subagent.manager import SubagentManager, build_subagent_state
from laffyhand.agent.tools.registry import ToolRegistry
from laffyhand.agent.tools.file import ReadTool, WriteTool, EditTool, GlobTool, GrepTool
from laffyhand.agent.tools.bash import BashTool
from laffyhand.agent.tools.todo import TodoTool
from laffyhand.agent.tools.skill_tool import SkillTool
from laffyhand.agent.tools.task import TaskTool
from laffyhand.agent.mcp import MCPService
from laffyhand.agent.loop import agent_loop

if TYPE_CHECKING:
    from laffyhand.agent.agent import AgentInfo


MAX_SUBAGENT_DEPTH = 3


class AgentRuntime:
    def __init__(
        self,
        llm: Any,
        session_manager: SessionManager,
        mcp_service: MCPService,
        compaction_config: CompactionConfig,
        title_config: TitleConfig,
        max_steps: int,
        max_subagents: int,
        db_path: str,
    ) -> None:
        self.llm = llm
        self.session_manager = session_manager
        self.mcp_service = mcp_service
        self.compaction_config = compaction_config
        self.title_config = title_config
        self.max_steps = max_steps

        self.tool_registry = ToolRegistry()
        self.agent_registry = AgentRegistry()
        self.skill_registry = SkillRegistry()
        self.subagent_manager = SubagentManager(max_concurrent=max_subagents)

        self._state: AgentState | None = None
        self._task_tool: TaskTool | None = None

    async def init_tools(self) -> None:
        for mcp_tool in await self.mcp_service.get_wrapped_tools():
            self.tool_registry.register_tool(mcp_tool)
        self.tool_registry.register_tool(ReadTool())
        self.tool_registry.register_tool(WriteTool())
        self.tool_registry.register_tool(EditTool())
        self.tool_registry.register_tool(GlobTool())
        self.tool_registry.register_tool(GrepTool())
        self.tool_registry.register_tool(BashTool())
        self.tool_registry.register_tool(TodoTool(
            todo_path=os.getenv("TODOS_PATH", ".todos.json"),
        ))

        skill_tool = SkillTool(self.skill_registry, self.tool_registry.permission)
        self.tool_registry.register_tool(skill_tool)

        self._task_tool = TaskTool(runtime=self)
        self.tool_registry.register_tool(self._task_tool)

        def _update_skill_description():
            summary = self.skill_registry.build_skills_summary()
            if summary:
                skill_tool.description = (
                    f"Load and inject a skill into context.\n\nAvailable skills:\n{summary}"
                )
            else:
                skill_tool.description = "Load and inject a skill into context."
        self.tool_registry.on_build_defs(_update_skill_description)
        _update_skill_description()

    @property
    def state(self) -> AgentState | None:
        return self._state

    @state.setter
    def state(self, new_state: AgentState) -> None:
        self._state = new_state

    @property
    def current_session_id(self) -> str | None:
        return self._state.session_id if self._state else None

    def load_agents(self, agent_dirs: Sequence[str | Path]) -> None:
        self.agent_registry.discover(list(agent_dirs))

    def load_skills(self, skill_dirs: Sequence[str | Path]) -> None:
        self.skill_registry.discover(list(skill_dirs))

    def build_system_prompt(self, base_prompt: str) -> str:
        content = base_prompt + self.tool_registry.build_tool_prompt()
        if self.skill_registry.all():
            content += "\n\n" + self.skill_registry.build_skills_summary()
        return content

    def create_initial_state(self, system_message: SystemMessage) -> AgentState:
        session = self.session_manager.create(cwd=os.getcwd(), model="")
        self._state = AgentState(
            messages=[system_message],
            session_id=session.id,
            usage=SessionUsage(context_size=0),
        )
        return self._state

    def save_current_state(self) -> None:
        if self._state and self._state.session_id:
            if self.session_manager.get(self._state.session_id):
                self.session_manager.save_state(self._state.session_id, self._state)

    def complete_current_session(self) -> None:
        if self._state and self._state.session_id:
            if self.session_manager.get(self._state.session_id):
                self.session_manager.save_state(self._state.session_id, self._state)
            self.session_manager.complete(self._state.session_id)

    def switch_session(self, session_id: str) -> bool:
        self.save_current_state()
        tip = self.session_manager.get_compression_tip(session_id)
        loaded = self.session_manager.load_state(tip)
        if loaded is None:
            return False
        loaded.usage.context_size = 0
        self._state = loaded
        return True

    def new_session(self, system_message: SystemMessage) -> AgentState:
        self.complete_current_session()
        session = self.session_manager.create(cwd=os.getcwd(), model="")
        self._state = AgentState(
            messages=[system_message] if system_message else [],
            session_id=session.id,
            turn_count=0,
            step=0,
            usage=SessionUsage(context_size=0),
        )
        return self._state

    def fork_session(self) -> str | None:
        if not self._state or not self._state.session_id:
            return None
        self.save_current_state()
        child = self.session_manager.fork(self._state.session_id)
        self._state.session_id = child.id
        return child.id

    async def run_agent_turn(self) -> Any:
        assert self._state is not None
        async for event in agent_loop(
            self._state,
            self.llm,
            self.tool_registry,
            compaction_config=self.compaction_config,
            max_steps=self.max_steps,
            session_manager=self.session_manager,
            subagent_manager=self.subagent_manager,
        ):
            yield event

    async def create_subagent(
        self,
        agent_info: AgentInfo,
        prompt: str,
        description: str = "",
        background: bool = False,
    ) -> str:
        assert self._state is not None
        parent_session_id = self._state.session_id
        assert parent_session_id is not None

        depth = self.session_manager.get_depth(parent_session_id)
        if depth > MAX_SUBAGENT_DEPTH:
            return (
                f"Error: maximum sub-agent depth ({MAX_SUBAGENT_DEPTH}) exceeded. "
                "Cannot spawn further sub-agents."
            )

        if background:
            assert self.subagent_manager is not None
            task_id: str = await self.subagent_manager.spawn(
                parent_session_id=parent_session_id,
                agent_info=agent_info,
                prompt=prompt,
                llm=self.llm,
                tool_registry=self.tool_registry,
                parent_permission=self.tool_registry.permission,
                session_manager=self.session_manager,
                compaction_config=self.compaction_config,
            )
            return f"Sub-agent [{agent_info.name}] started (id: {task_id[:8]}). I'll notify you when it completes."

        return await self._run_subagent_foreground(
            parent_session_id, agent_info, prompt,
        )

    async def _run_subagent_foreground(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
    ) -> str:
        _, child_state, child_registry = build_subagent_state(
            self.session_manager, parent_session_id, agent_info, prompt,
            self.tool_registry.permission, self.tool_registry,
        )

        result_parts: list[str] = []
        async for event in agent_loop(
            child_state,
            self.llm,
            child_registry,
            compaction_config=CompactionConfig(
                tail_turns=self.compaction_config.tail_turns,
            ),
            max_steps=agent_info.max_steps,
            session_manager=self.session_manager,
        ):
            if event.type == "content" and event.finish_reason is not None:
                last_msg = child_state.messages[-1]
                if isinstance(last_msg, SystemMessage):
                    pass
                elif hasattr(last_msg, "content") and last_msg.content:
                    result_parts.append(last_msg.content)

        assert child_state.session_id is not None
        self.session_manager.save_state(child_state.session_id, child_state)
        self.session_manager.complete(child_state.session_id)

        result = "\n".join(part for part in result_parts if part).strip()
        if not result:
            result = "[No output]"
        return f"<task>\n{result}\n</task>"

    async def generate_title_for_current(self) -> str | None:
        if self.title_config.mode == "off":
            return None
        if not self._state or not self._state.session_id:
            return None
        from laffyhand.agent.title import generate_title
        return await generate_title(
            self.session_manager, self._state.session_id, self.llm, self.title_config,
        )

    async def shutdown(self) -> None:
        self.save_current_state()
        if self._state and self._state.session_id:
            logger.info(f"Session state saved: {self._state.session_id}")
        await self.mcp_service.disconnect_all()
        self.session_manager.close()
        logger.info("Agent shutdown complete")
