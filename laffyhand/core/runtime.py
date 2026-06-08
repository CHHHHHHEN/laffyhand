from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.core.llm.specs.models import ModelID, ProviderID, SystemMessage
from laffyhand.core.models import (
    AgentState,
    CompactionConfig,
    SessionID,
)
from laffyhand.core.agent import AgentRegistry
from laffyhand.core.skill import SkillRegistry
from laffyhand.core.session import SessionManager, TitleConfig
from laffyhand.core.session.state_store import SessionStateStore
from laffyhand.core.subagent import (
    SubagentTaskRunner,
    SubagentOrchestrator,
    SessionContext,
)
from laffyhand.core.tools.registry import ToolRegistry
from laffyhand.core.tools.init import ToolInitializer
from laffyhand.core.session.todo import TodoManager
from laffyhand.core.mcp import MCPService
from laffyhand.core.db.repository import FileTagRepo
from laffyhand.core.loop import LoopOrchestrator
from laffyhand.core.llm.factory import build_route
from laffyhand.core.llm.facade import LLM
from laffyhand.core.exceptions import ConfigError
from laffyhand.core.models import AgentEvent
from laffyhand.core._utils import build_env_block
from laffyhand.core.memory.service import MemoryService
from laffyhand.core.preference import PreferenceService
from laffyhand.core.agent import assemble_system_prompt
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

        self._session_store = SessionStateStore()

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
        self.subagent_manager = SubagentTaskRunner(
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
            event_sink_provider=lambda sid: self._session_store.get_event_sink(sid),
        )

        self._memory_service = (
            MemoryService(
                path=config.memory.path,
                max_length=config.memory.max_length,
            )
            if config.memory.enabled
            else None
        )

        self._tool_initializer = ToolInitializer(
            mcp_service=self.mcp_service,
            tool_registry=self.tool_registry,
            todo_manager=self.todo_manager,
            skill_registry=self.skill_registry,
            agent_registry=self.agent_registry,
            subagent_orchestrator=self.subagent_orchestrator,
            file_tag_repo=self._file_tag_repo,
            memory_service=self._memory_service,
        )

        self.loop_orchestrator = LoopOrchestrator(
            session_manager=self.session_manager,
            tool_registry=self.tool_registry,
            subagent_manager=self.subagent_manager,
            llm_provider=self._llm_for_session,
            compaction_config=self.compaction_config,
            max_steps=self.max_steps,
            preference_checker=self.poll_new_preferences,
            title_scheduler=self._schedule_title_generation,
            session_store=self._session_store,
        )
        self.preference_service = PreferenceService()

    def update_sessions_workspace_env(self, new_workspace: str) -> None:
        """Replace the <env> block in all active sessions' system messages."""
        new_env_block = build_env_block(new_workspace)
        for _sid, state in self._session_store.items():
            if not state.messages:
                continue
            first = state.messages[0]
            if not isinstance(first, SystemMessage):
                continue
            old = first.content
            start = old.find("<env>\n")
            end = old.find("\n</env>")
            if start == -1 or end == -1:
                continue
            end += len("\n</env>")
            first.content = old[:start] + new_env_block + old[end:]

    def _build_llm(self, provider: str, model: str) -> LLM:
        from laffyhand.config import resolve_provider

        provider_key, provider_cfg = resolve_provider(self._config.llm, provider)
        route = build_route(
            provider_cfg.type, provider_cfg.base_url, provider_cfg.api_key
        )
        logger.info(f"Built LLM: provider={provider_key}, model={model}")
        return LLM(
            model=ModelID(model), provider=ProviderID(provider_cfg.type), route=route
        )

    async def init_tools(self) -> None:
        await self._tool_initializer.register_all()

    @property
    def context_size(self) -> int:
        return self._context_size

    def get_state(self, session_id: str) -> AgentState | None:
        return self._session_store.get(session_id)

    def get_session_lock(self, session_id: str) -> asyncio.Lock:
        return self._session_store.get_lock(session_id)

    def get_session_context(self, session_id: str) -> SessionContext | None:
        return self._session_store.get_session_context(session_id)

    @property
    def session_store(self) -> SessionStateStore:
        return self._session_store

    @property
    def pending_permissions(
        self,
    ) -> dict[str, tuple[asyncio.Event, str, str, bool | None, str | None]]:
        return self._session_store.pending_permissions

    @property
    def config(self) -> LaffyConfig:
        return self._config

    def load_agents(self, agent_dirs: Sequence[str | Path]) -> None:
        self.agent_registry.discover(list(agent_dirs))

    def load_skills(self, skill_dirs: Sequence[str | Path]) -> None:
        self.skill_registry.discover(list(skill_dirs))

    # ── Preference delegation ────────────────────────────────────

    async def poll_new_preferences(self) -> str:
        return await self.preference_service.poll_new_preferences()

    def resolve_preferences(
        self,
        file_path: str,
        message_id: str,
        *,
        root: str | None = None,
    ) -> list[dict[str, str]]:
        return self.preference_service.resolve_preferences(
            file_path, message_id, root=root
        )

    def clear_preference_claims(self, message_id: str) -> None:
        self.preference_service.clear_preference_claims(message_id)

    async def build_system_prompt(
        self, base_prompt: str, disabled_tools: set[str] | None = None
    ) -> str:
        return await assemble_system_prompt(
            base_prompt,
            workspace=self.tool_registry.workspace,
            disabled_tools=disabled_tools,
            tool_registry=self.tool_registry,
            skill_registry=self.skill_registry,
            preference_service=self.preference_service,
            memory_service=self._memory_service,
        )

    def fork_session(self, session_id: str) -> str | None:
        return self._session_store.fork(session_id, self.session_manager)

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
        """Load session state from in-memory cache or DB into the store."""
        return self._session_store.load(
            session_id, self.session_manager, self.context_size
        )

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
        async for event in self.loop_orchestrator.run_agent_turn(
            session_id, event_sink=event_sink
        ):
            yield event

    async def compact_session(self, session_id: str) -> str | None:
        """Manually trigger compaction for a session. Returns new session_id or None."""
        from laffyhand.core.context.chain import compact_with_chain

        state = self._session_store.get(session_id)
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
        return await self.loop_orchestrator.start_background_agent_turn(
            session_id, event_sink=event_sink
        )

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
            parent_session_id,
            agent_info,
            prompt,
            description=description,
            background=background,
            todo_id=todo_id,
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
        state = self._session_store.get(session_id)
        if state is None:
            return False
        state.interrupt_requested = True
        self.subagent_orchestrator.cancel_session(session_id)
        logger.debug(f"Interrupt requested for session {session_id}")
        return True

    def steer_session(self, session_id: str, text: str) -> bool:
        state = self._session_store.get(session_id)
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
        self._session_store.save_all(self.session_manager)
        await self.mcp_service.disconnect_all()
        self.session_manager.close()
        logger.info("Agent shutdown complete")


__all__ = ["AgentRuntime"]
