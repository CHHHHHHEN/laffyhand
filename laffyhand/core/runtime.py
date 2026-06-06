from __future__ import annotations

import asyncio
import copy
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.core.llm.specs.models import ModelID, ProviderID, SystemMessage
from laffyhand.core.schemas import (
    AgentState,
    CompactionConfig,
    SessionID,
)
from laffyhand.core.agent import AgentRegistry
from laffyhand.core.skill import SkillRegistry
from laffyhand.core.session import SessionManager, TitleConfig
from laffyhand.core.subagent import SubagentManager, SubagentOrchestrator, SessionContext
from laffyhand.core.tools.registry import ToolRegistry
from laffyhand.core.tools.file import ReadTool, ListDirTool, WriteTool, EditTool, GlobTool, GrepTool
from laffyhand.core.tools.bash import BashTool
from laffyhand.core.tools.web_fetch import WebFetchTool
from laffyhand.core.tools.todo import TodoTool
from laffyhand.core.tools.tag import TagTool, annotate_result
from laffyhand.core.session.todo import TodoManager
from laffyhand.core.tools.skill_tool import SkillTool
from laffyhand.core.tools.task import TaskTool
from laffyhand.core.tools.mcp_manage import (
    MCPListTool,
    MCPConnectTool,
    MCPDisconnectTool,
)
from laffyhand.core.mcp import MCPService
from laffyhand.core.db.repository import FileTagRepo
from laffyhand.core.loop import LoopOrchestrator
from laffyhand.core.llm.factory import build_route
from laffyhand.core.llm.facade import LLM
from laffyhand.core.exceptions import SessionError, ConfigError
from laffyhand.core.events import AgentEvent
from laffyhand.core._utils import build_env_block
from laffyhand.core.preference import PreferenceService
from laffyhand.core.title import TitleService
from laffyhand.core.workspace import WorkspaceService

if TYPE_CHECKING:
    from laffyhand.core.agent import AgentInfo
    from laffyhand.config import LaffyConfig


class AgentRuntime:
    def __init__(
        self,
        config: LaffyConfig,
        llm: LLM | None = None,
        *,
        session_manager: SessionManager | None = None,
        mcp_service: MCPService | None = None,
    ) -> None:
        self._config = config
        self.llm = llm

        self._event_sinks: dict[str, Callable[[Any], Awaitable[None]]] = {}

        self.session_manager = session_manager or SessionManager(config.db.path)
        self.mcp_service = mcp_service or MCPService()
        self.compaction_config = CompactionConfig(
            tail_turns=config.agent.compaction_tail_turns,
        )
        self.title_config = TitleConfig(mode=config.agent.title_mode)
        self.title_service = TitleService(
            session_manager=self.session_manager,
            title_config=self.title_config,
            llm_provider=self._llm_for_session,
        )
        self.max_steps = config.agent.max_steps
        self.subagent_manager = SubagentManager(
            max_concurrent=config.agent.max_concurrent_subagents,
        )
        try:
            from laffyhand.config import resolve_provider, resolve_model

            _, provider_cfg = resolve_provider(config.llm)
            model_cfg = resolve_model(provider_cfg)
            self._context_size = model_cfg.context_size
        except (ValueError, KeyError) as e:
            logger.warning(f"Could not resolve provider/model for context_size: {e}")
            self._context_size = 128_000

        self.workspace_service = WorkspaceService(self._config)
        self.tool_registry = ToolRegistry()
        self.tool_registry.workspace = self.workspace_service.resolve_workspace()
        self.agent_registry = AgentRegistry()
        self.skill_registry = SkillRegistry()

        self.todo_manager = TodoManager.from_session_manager(self.session_manager)

        self._file_tag_repo = FileTagRepo(self.session_manager.connection)

        self.subagent_orchestrator = SubagentOrchestrator(
            session_manager=self.session_manager,
            tool_registry=self.tool_registry,
            subagent_manager=self.subagent_manager,
            llm_provider=self._llm_for_session,
            compaction_config=self.compaction_config,
            todo_manager=self.todo_manager,
            event_sink_provider=lambda sid: self._event_sinks.get(sid),
        )

        self._states: dict[str, AgentState] = {}

        self.loop_orchestrator = LoopOrchestrator(
            session_manager=self.session_manager,
            tool_registry=self.tool_registry,
            subagent_manager=self.subagent_manager,
            llm_provider=self._llm_for_session,
            compaction_config=self.compaction_config,
            max_steps=self.max_steps,
            preference_checker=self.poll_new_preferences,
            title_scheduler=self._schedule_title_generation,
            states=self._states,
            event_sinks=self._event_sinks,
        )
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_contexts: dict[str, SessionContext] = {}
        self._pending_permissions: dict[
            str, tuple[asyncio.Event, str, str, bool | None, str | None]
        ] = {}
        self._task_tool: TaskTool | None = None
        self.preference_service = PreferenceService()



    def _build_llm(self, provider: str, model: str) -> LLM:
        from laffyhand.config import resolve_provider

        provider_key, provider_cfg = resolve_provider(self._config.llm, provider)
        route = build_route(
            provider_cfg.type, provider_cfg.base_url, provider_cfg.api_key
        )
        logger.info(f"Built LLM: provider={provider_key}, model={model}")
        return LLM(model=ModelID(model), provider=ProviderID(provider_cfg.type), route=route)

    async def init_tools(self) -> None:
        for mcp_tool in await self.mcp_service.get_wrapped_tools():
            self.tool_registry.register_tool(mcp_tool)
        self.tool_registry.register_tool(ReadTool())
        self.tool_registry.register_tool(ListDirTool())
        self.tool_registry.register_tool(
            WriteTool(permission_manager=self.tool_registry.permission)
        )
        self.tool_registry.register_tool(EditTool())
        self.tool_registry.register_tool(GlobTool())
        self.tool_registry.register_tool(GrepTool())
        self.tool_registry.register_tool(BashTool())
        self.tool_registry.register_tool(WebFetchTool())
        self.tool_registry.register_tool(TodoTool(self.todo_manager))

        skill_tool = SkillTool(self.skill_registry, self.tool_registry.permission)
        self.tool_registry.register_tool(skill_tool)

        self._task_tool = TaskTool(agent_registry=self.agent_registry, orchestrator=self.subagent_orchestrator)
        self.tool_registry.register_tool(self._task_tool)

        # Tag tool
        self.tool_registry.register_tool(TagTool(self._file_tag_repo))

        # Post-process glob/read results with tag annotations
        repo = self._file_tag_repo

        def _post_process(name: str, result: str, params: dict) -> str:
            if name in ("glob", "list_dir"):
                return annotate_result(name, result, params, repo)
            return result

        self.tool_registry.result_post_processor = _post_process

        # MCP management tools
        self.tool_registry.register_tool(MCPListTool(self.mcp_service))
        self.tool_registry.register_tool(
            MCPConnectTool(self.mcp_service, self.tool_registry)
        )
        self.tool_registry.register_tool(
            MCPDisconnectTool(self.mcp_service, self.tool_registry)
        )

        def _update_skill_description() -> None:
            summary = self.skill_registry.build_skills_summary()
            if summary:
                skill_tool.description = (
                    f"Load and inject a skill into context.\n\n{summary}"
                )
            else:
                skill_tool.description = "Load and inject a skill into context."

        self.tool_registry.on_build_defs(_update_skill_description)
        _update_skill_description()

    @property
    def context_size(self) -> int:
        return self._context_size

    def get_state(self, session_id: str) -> AgentState | None:
        return self._states.get(session_id)

    def get_session_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    @asynccontextmanager
    async def use_session(self, session_id: str) -> AsyncIterator[tuple[AgentState, SessionContext]]:
        """Context manager: holds the per-session lock and provides (state, ctx).

        Usage:
            async with runtime.use_session(sid) as (state, ctx):
                state.messages.append(...)
                ctx.subagent_id = ...
        """
        state = self._states.get(session_id)
        if state is None:
            raise SessionError(f"Session not found: {session_id}")
        ctx = SessionContext()
        self._session_contexts[session_id] = ctx
        lock = self.get_session_lock(session_id)
        async with lock:
            try:
                yield (state, ctx)
            finally:
                self._session_contexts.pop(session_id, None)

    def get_session_context(self, session_id: str) -> SessionContext | None:
        return self._session_contexts.get(session_id)

    @property
    def pending_permissions(
        self,
    ) -> dict[str, tuple[asyncio.Event, str, str, bool | None, str | None]]:
        return self._pending_permissions

    @property
    def config(self) -> LaffyConfig:
        return self._config

    def load_agents(self, agent_dirs: Sequence[str | Path]) -> None:
        self.agent_registry.discover(list(agent_dirs))

    def load_skills(self, skill_dirs: Sequence[str | Path]) -> None:
        self.skill_registry.discover(list(skill_dirs))

    # ── Preference delegation ────────────────────────────────────

    async def _load_preferences(self) -> str:
        return await self.preference_service.load_preferences()

    async def poll_new_preferences(self) -> str:
        return await self.preference_service.poll_new_preferences()

    def resolve_preferences(
        self,
        file_path: str,
        message_id: str,
        *,
        root: str | None = None,
    ) -> list[dict[str, str]]:
        return self.preference_service.resolve_preferences(file_path, message_id, root=root)

    def clear_preference_claims(self, message_id: str) -> None:
        self.preference_service.clear_preference_claims(message_id)

    async def build_system_prompt(self, base_prompt: str, disabled_tools: set[str] | None = None) -> str:
        parts: list[str] = []
        parts.append(f"<soul>\n{base_prompt.strip()}\n</soul>")

        parts.append(build_env_block(self.tool_registry.workspace))

        parts.append(self.tool_registry.build_tool_prompt(exclude=disabled_tools or set()))

        if self.skill_registry.all():
            parts.append(self.skill_registry.build_skills_summary())

        preferences = await self._load_preferences()
        if preferences:
            parts.append(preferences)

        return "\n".join(parts)

    def fork_session(self, session_id: str) -> str | None:
        state = self._states.get(session_id)
        if state is None or not state.session_id:
            return None
        child = self.session_manager.fork(state.session_id)
        forked = copy.deepcopy(state)
        forked.session_id = SessionID(child.id)
        self._states[child.id] = forked
        return child.id

    async def add_mcp_server(self, name: str, cfg: Any) -> list[str]:
        from laffyhand.core.mcp.service import MCPWrappedTool

        tool_defs = await self.mcp_service.connect_server(name, cfg)
        tool_names: list[str] = []
        for td in tool_defs:
            wrapper = MCPWrappedTool(name, td, self.mcp_service)
            self.tool_registry.register_tool(wrapper)
            tool_names.append(wrapper.name)
        return tool_names

    async def remove_mcp_server(self, name: str) -> int:
        prefix = f"mcp_{name}_"
        unregistered = self.tool_registry.unregister_by_prefix(prefix)
        await self.mcp_service.disconnect(name)
        return unregistered

    def load_session_state(self, session_id: str) -> AgentState | None:
        """Load session state from in-memory cache or DB into _states."""
        if session_id in self._states:
            return self._states[session_id]
        loaded = self.session_manager.load_state(session_id)
        if loaded is None:
            return None
        system_message = loaded.messages[0] if loaded.messages else None
        if system_message and isinstance(system_message, SystemMessage):
            compressed = self.session_manager.load_compressed_state(
                session_id, system_message, self.context_size,
            )
            if compressed is not None:
                loaded = compressed
        if loaded.usage:
            loaded.usage.context_size = self.context_size
        self._states[session_id] = loaded
        return loaded

    def _llm_for_session(self, session_id: str) -> LLM:
        from laffyhand.config import resolve_provider, resolve_model

        session = self.session_manager.get(session_id)
        provider = session.provider if session and session.provider else None
        model = session.model if session and session.model else None
        if not provider or not model:
            try:
                provider_key, provider_cfg = resolve_provider(self._config.llm)
                provider = ProviderID(provider_key)
                model = model or ModelID(resolve_model(provider_cfg).name)
            except ValueError:
                logger.warning(
                    f"Session {session_id}: could not resolve provider/model, "
                    f"falling back to default LLM"
                )
        if provider and model:
            return self._build_llm(provider, model)
        if self.llm is not None:
            return self.llm
        raise ConfigError("No LLM available for session")

    async def run_agent_turn(
        self,
        session_id: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        async for event in self.loop_orchestrator.run_agent_turn(session_id, event_sink=event_sink):
            yield event

    async def compact_session(self, session_id: str) -> str | None:
        """Manually trigger compaction for a session. Returns new session_id or None."""
        from laffyhand.core.compaction import compact_with_chain

        state = self._states.get(session_id)
        if state is None:
            state = self.load_session_state(session_id)
        if state is None:
            logger.warning(f"compact_session: state not found for {session_id}")
            return None
        llm = self._llm_for_session(session_id)
        result = await compact_with_chain(state, llm, self.compaction_config)
        if result is None:
            logger.info(f"compact_session: nothing to compact for {session_id}")
            return None
        summary, original_system, tail = result
        child = self.session_manager.create_compacted_child(
            parent_id=session_id,
            system_messages=original_system,
            summary_content=summary,
            tail_messages=tail,
        )
        summary_msg = SystemMessage(content=summary.strip())
        state.session_id = SessionID(child.id)
        state.messages = original_system + [summary_msg] + tail
        state.step = 0
        self._schedule_title_generation(child.id, "on_compact")
        logger.info(f"Manual compaction: {session_id} -> {child.id}")
        return child.id

    # ── Background session tasks ──────────────────────────────

    def is_session_running(self, session_id: str) -> bool:
        return self.loop_orchestrator.is_session_running(session_id)

    async def start_background_agent_turn(
        self,
        session_id: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
    ) -> asyncio.Queue:
        return await self.loop_orchestrator.start_background_agent_turn(session_id, event_sink=event_sink)

    def cancel_background_agent_turn(self, session_id: str) -> None:
        self.loop_orchestrator.cancel_background_agent_turn(session_id)

    async def create_subagent(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
        description: str = "",
        background: bool = False,
        todo_id: str | None = None,
    ) -> str:
        return await self.subagent_orchestrator.create_subagent(
            parent_session_id, agent_info, prompt,
            description=description, background=background, todo_id=todo_id,
        )

    def _should_generate_title(self, session_id: str, trigger: str) -> bool:
        return self.title_service.should_generate(session_id, trigger)

    def _schedule_title_generation(self, session_id: str, trigger: str) -> None:
        self.title_service.schedule_generation(session_id, trigger)

    async def _generate_title(self, session_id: str, trigger: str) -> bool:
        if not self._should_generate_title(session_id, trigger):
            return False
        title = await self._do_generate_title(session_id)
        return bool(title)

    async def _do_generate_title(self, session_id: str) -> str | None:
        try:
            llm = self._llm_for_session(session_id)
        except Exception:
            logger.exception(f"Failed to resolve LLM for session {session_id}")
            return None
        return await self.title_service.generate_title(session_id, llm=llm)

    def interrupt_session(self, session_id: str) -> bool:
        state = self._states.get(session_id)
        if state is None:
            return False
        state.interrupt_requested = True
        # Cascade interrupt to all child (sub-agent) sessions
        self.subagent_orchestrator.cancel_session(session_id)
        logger.debug(f"Interrupt requested for session {session_id}")
        return True

    def steer_session(self, session_id: str, text: str) -> bool:
        state = self._states.get(session_id)
        if state is None:
            return False
        if state.pending_steer:
            state.pending_steer += "\n" + text
        else:
            state.pending_steer = text
        logger.debug(f"Steer text set for session {session_id}")
        return True

    async def shutdown(self) -> None:
        # Cancel in-flight background agent turns before saving state
        await self.loop_orchestrator.cancel_all()

        # Cancel in-flight subagent tasks
        await self.subagent_orchestrator.cancel_all()

        # Now save state — no more in-flight tasks modifying state
        for sid, state in list(self._states.items()):
            save_id = state.session_id or sid
            if self.session_manager.get(save_id):
                self.session_manager.save_state(save_id, state)
                logger.info(f"Session state saved: {sid} (session_id={save_id})")
        self._states.clear()
        await self.mcp_service.disconnect_all()
        self.session_manager.close()
        logger.info("Agent shutdown complete")


__all__ = ["AgentRuntime"]
