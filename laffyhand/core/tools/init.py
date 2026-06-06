from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laffyhand.core.mcp import MCPService
    from laffyhand.core.tools.registry import ToolRegistry
    from laffyhand.core.session.todo import TodoManager
    from laffyhand.core.skill import SkillRegistry
    from laffyhand.core.agent import AgentRegistry
    from laffyhand.core.subagent import SubagentOrchestrator
    from laffyhand.core.db.repository import FileTagRepo


class ToolInitializer:
    def __init__(
        self,
        *,
        mcp_service: MCPService,
        tool_registry: ToolRegistry,
        todo_manager: TodoManager,
        skill_registry: SkillRegistry,
        agent_registry: AgentRegistry,
        subagent_orchestrator: SubagentOrchestrator,
        file_tag_repo: FileTagRepo,
    ) -> None:
        self._mcp_service = mcp_service
        self._tool_registry = tool_registry
        self._todo_manager = todo_manager
        self._skill_registry = skill_registry
        self._agent_registry = agent_registry
        self._subagent_orchestrator = subagent_orchestrator
        self._file_tag_repo = file_tag_repo

    async def register_all(self) -> None:
        from laffyhand.core.tools.file import ReadTool, ListDirTool, WriteTool, EditTool, GlobTool, GrepTool
        from laffyhand.core.tools.bash import BashTool
        from laffyhand.core.tools.web_fetch import WebFetchTool
        from laffyhand.core.tools.todo import TodoTool
        from laffyhand.core.tools.tag import TagTool, annotate_result
        from laffyhand.core.tools.skill_tool import SkillTool
        from laffyhand.core.tools.task import TaskTool
        from laffyhand.core.tools.mcp_manage import (
            MCPListTool,
            MCPConnectTool,
            MCPDisconnectTool,
        )

        # MCP tools
        for mcp_tool in await self._mcp_service.get_wrapped_tools():
            self._tool_registry.register_tool(mcp_tool)

        # Built-in tools
        self._tool_registry.register_tool(ReadTool())
        self._tool_registry.register_tool(ListDirTool())
        self._tool_registry.register_tool(
            WriteTool(permission_manager=self._tool_registry.permission)
        )
        self._tool_registry.register_tool(EditTool())
        self._tool_registry.register_tool(GlobTool())
        self._tool_registry.register_tool(GrepTool())
        self._tool_registry.register_tool(BashTool())
        self._tool_registry.register_tool(WebFetchTool())
        self._tool_registry.register_tool(TodoTool(self._todo_manager))

        skill_tool = SkillTool(self._skill_registry, self._tool_registry.permission)
        self._tool_registry.register_tool(skill_tool)

        task_tool = TaskTool(
            agent_registry=self._agent_registry,
            orchestrator=self._subagent_orchestrator,
        )
        self._tool_registry.register_tool(task_tool)

        # Tag tool
        self._tool_registry.register_tool(TagTool(self._file_tag_repo))

        # Post-process glob/read results with tag annotations
        repo = self._file_tag_repo

        def _post_process(name: str, result: str, params: dict) -> str:
            if name in ("glob", "list_dir"):
                return annotate_result(name, result, params, repo)
            return result

        self._tool_registry.result_post_processor = _post_process

        # MCP management tools
        self._tool_registry.register_tool(MCPListTool(self._mcp_service))
        self._tool_registry.register_tool(
            MCPConnectTool(self._mcp_service, self._tool_registry)
        )
        self._tool_registry.register_tool(
            MCPDisconnectTool(self._mcp_service, self._tool_registry)
        )

        # Dynamic skill description update
        def _update_skill_description() -> None:
            summary = self._skill_registry.build_skills_summary()
            if summary:
                skill_tool.description = (
                    f"Load and inject a skill into context.\n\n{summary}"
                )
            else:
                skill_tool.description = "Load and inject a skill into context."

        self._tool_registry.on_build_defs(_update_skill_description)
        _update_skill_description()
