from __future__ import annotations

import asyncio
import copy
import os
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.agent.llm.specs.models import AssistantMessage, ModelID, ProviderID, SystemMessage
from laffyhand.agent.schemas import (
    AgentState,
    Compacting,
    CompactionConfig,
    SessionID,
    StepFinish,
    StepStart,
    SubAgentEnd,
    SubAgentStart,
    SubAgentDelta,
    TextDelta,
    TextEnd,
    TextStart,
    ReasoningDelta,
    ReasoningEnd,
    ReasoningStart,
    ToolCall as StreamToolCall,
)
from laffyhand.agent.agent import AgentRegistry
from laffyhand.agent.skill import SkillRegistry
from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.subagent.manager import SubagentManager, build_subagent_state
from laffyhand.agent.tools.registry import ToolRegistry
from laffyhand.agent.tools.file import ReadTool, WriteTool, EditTool, GlobTool, GrepTool
from laffyhand.agent.tools.bash import BashTool
from laffyhand.agent.tools.todo import TodoTool
from laffyhand.agent.session.todo import TodoManager
from laffyhand.agent.tools.skill_tool import SkillTool
from laffyhand.agent.tools.task import TaskTool
from laffyhand.agent.tools.mcp_manage import (
    MCPListTool,
    MCPConnectTool,
    MCPDisconnectTool,
)
from laffyhand.agent.mcp import MCPService
from laffyhand.agent.loop import agent_loop
from laffyhand.agent.llm.factory import build_route
from laffyhand.agent.llm.facade import LLM

if TYPE_CHECKING:
    from laffyhand.agent.agent import AgentInfo

from laffyhand.config import LaffyConfig


MAX_SUBAGENT_DEPTH = 3

# Sentinel object marking agent turn completion
_TURN_DONE = object()


@dataclass
class SessionContext:
    """Per-call context attached to a running agent turn."""
    subagent_id: str | None = None
    subagent_depth: int = 0


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

        self.tool_registry = ToolRegistry()
        self.agent_registry = AgentRegistry()
        self.skill_registry = SkillRegistry()

        self.todo_manager = TodoManager.from_session_manager(self.session_manager)

        self._states: dict[str, AgentState] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_contexts: dict[str, SessionContext] = {}
        self._pending_permissions: dict[
            str, tuple[asyncio.Event, str, str, bool | None]
        ] = {}
        self._task_tool: TaskTool | None = None
        self._preferences: str | None = None
        self._preference_files: dict[str, str] = {}
        self._pref_lock = asyncio.Lock()
        self._prefs_initialized: bool = False

        # Background session tasks (decoupled from HTTP connections)
        self._session_tasks: dict[str, asyncio.Task[None]] = {}
        self._session_event_queues: dict[str, asyncio.Queue] = {}



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
        self.tool_registry.register_tool(
            WriteTool(permission_manager=self.tool_registry.permission)
        )
        self.tool_registry.register_tool(EditTool())
        self.tool_registry.register_tool(GlobTool())
        self.tool_registry.register_tool(GrepTool())
        self.tool_registry.register_tool(BashTool())
        self.tool_registry.register_tool(TodoTool(self.todo_manager))

        skill_tool = SkillTool(self.skill_registry, self.tool_registry.permission)
        self.tool_registry.register_tool(skill_tool)

        self._task_tool = TaskTool(runtime=self)
        self.tool_registry.register_tool(self._task_tool)

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
            raise RuntimeError(f"Session not found: {session_id}")
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
    ) -> dict[str, tuple[asyncio.Event, str, str, bool | None]]:
        return self._pending_permissions

    @property
    def config(self) -> LaffyConfig:
        return self._config

    def load_agents(self, agent_dirs: Sequence[str | Path]) -> None:
        self.agent_registry.discover(list(agent_dirs))

    def load_skills(self, skill_dirs: Sequence[str | Path]) -> None:
        self.skill_registry.discover(list(skill_dirs))

    @staticmethod
    def _preference_roots() -> list[Path]:
        return [Path(os.getcwd()), Path(os.path.expanduser("~"))]

    def _read_preference_files(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for root in self._preference_roots():
            path = root / "AGENTS.md"
            if path.is_file():
                result[str(path)] = path.read_text(encoding="utf-8").strip()
        return result

    async def _load_preferences(self) -> str:
        async with self._pref_lock:
            if self._preferences is not None:
                return self._preferences
            self._preference_files = self._read_preference_files()
            sections = [
                f"<preference>\n{text}\n</preference>"
                for text in self._preference_files.values()
            ]
            self._preferences = "\n".join(sections) if sections else ""
            self._prefs_initialized = True
            return self._preferences

    async def poll_new_preferences(self) -> str:
        current = self._read_preference_files()

        async with self._pref_lock:
            if not self._prefs_initialized:
                # Not yet loaded into system prompt — just populate cache without emitting
                self._preference_files = current
                return ""

            changed = False
            sections: list[str] = []

            # Detect new/changed files
            for path, text in current.items():
                prev = self._preference_files.get(path)
                if prev == text:
                    continue
                self._preference_files[path] = text
                sections.append(f"<preference>\n{text}\n</preference>")
                changed = True
                logger.info(f"New/changed preferences: {path}")

            # Detect deleted files
            for path in list(self._preference_files):
                if path not in current:
                    del self._preference_files[path]
                    changed = True
                    logger.info(f"Removed preferences from deleted file: {path}")

            if changed:
                self._preferences = (
                    None  # invalidate cache so next _load_preferences re-reads
                )
        return "\n".join(sections) if sections else ""

    async def build_system_prompt(self, base_prompt: str, disabled_tools: set[str] | None = None) -> str:
        parts: list[str] = []
        parts.append(f"<soul>\n{base_prompt.strip()}\n</soul>")

        env_parts = [
            f"Working directory: {os.getcwd()}",
            f"Platform: {sys.platform}",
        ]
        parts.append("<env>\n" + "\n".join(env_parts) + "\n</env>")

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
        from laffyhand.agent.mcp.service import MCPWrappedTool

        tool_defs = await self.mcp_service.connect_server(name, cfg)
        tool_names: list[str] = []
        for td in tool_defs:
            wrapper = MCPWrappedTool(name, td, self.mcp_service)
            self.tool_registry.register_tool(wrapper)
            tool_names.append(wrapper.name)
        return tool_names

    async def remove_mcp_server(self, name: str) -> int:
        prefix = f"mcp_{name}_"
        unregistered = 0
        for tool_name in list(self.tool_registry.list_tools()):
            if tool_name.startswith(prefix):
                self.tool_registry.unregister_tool(tool_name)
                unregistered += 1
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
        raise RuntimeError("No LLM available for session")

    async def run_agent_turn(  # type: ignore[no-untyped-def]
        self,
        session_id: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
    ):
        state = self._states.get(session_id)
        assert state is not None, f"state not found for session {session_id}"
        if event_sink is not None:
            self._event_sinks[session_id] = event_sink
        llm = self._llm_for_session(session_id)
        try:
            async for event in agent_loop(
                state,
                llm,
                self.tool_registry,
                compaction_config=self.compaction_config,
                max_steps=self.max_steps,
                session_manager=self.session_manager,
                subagent_manager=self.subagent_manager,
                preference_checker=self.poll_new_preferences,
                on_compacted=lambda child_sid: self._schedule_title_generation(
                    child_sid, "on_compact"
                ),
            ):
                yield event
        finally:
            self._event_sinks.pop(session_id, None)

    # ── Background session tasks ──────────────────────────────

    def is_session_running(self, session_id: str) -> bool:
        return session_id in self._session_tasks and not self._session_tasks[session_id].done()

    async def start_background_agent_turn(
        self,
        session_id: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
    ) -> asyncio.Queue:
        """Run agent_loop in a background task, pushing events to a per-session queue.

        The queue remains valid even after the HTTP connection drops.
        Returns the event queue for the caller to drain.
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._session_event_queues[session_id] = queue

        async def _run() -> None:
            try:
                async for event in self.run_agent_turn(
                    session_id=session_id,
                    event_sink=event_sink,
                ):
                    await queue.put(event)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(f"Background agent turn failed for {session_id}")
            finally:
                await queue.put(_TURN_DONE)
                self._session_tasks.pop(session_id, None)
                self._session_event_queues.pop(session_id, None)
                self._event_sinks.pop(session_id, None)

        task = asyncio.create_task(_run())
        self._session_tasks[session_id] = task
        return queue

    def cancel_background_agent_turn(self, session_id: str) -> None:
        task = self._session_tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()

    async def create_subagent(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
        description: str = "",
        background: bool = False,
        todo_id: str | None = None,
    ) -> str:
        depth = self.session_manager.get_depth(parent_session_id)
        if depth > MAX_SUBAGENT_DEPTH:
            return (
                f"Error: maximum sub-agent depth ({MAX_SUBAGENT_DEPTH}) exceeded. "
                "Cannot spawn further sub-agents."
            )

        task_id = uuid.uuid4().hex[:12]
        ctx = self._session_contexts.get(parent_session_id)
        parent_subagent_id = ctx.subagent_id if ctx else None
        subagent_depth = (ctx.subagent_depth + 1) if ctx else 1

        if todo_id:
            from laffyhand.agent.session.todo import TodoUpdate

            self.todo_manager.update_task(
                todo_id,
                parent_session_id,
                TodoUpdate(status="in_progress"),
            )

        if background:
            assert self.subagent_manager is not None
            bg_llm = self._llm_for_session(parent_session_id)

            def _on_complete(_task_id: str, success: bool) -> None:
                if todo_id:
                    from laffyhand.agent.session.todo import TodoUpdate

                    self.todo_manager.update_task(
                        todo_id,
                        parent_session_id,
                        TodoUpdate(
                            status="completed" if success else "pending",
                        ),
                    )

            await self.subagent_manager.spawn(
                parent_session_id=parent_session_id,
                agent_info=agent_info,
                prompt=prompt,
                llm=bg_llm,
                tool_registry=self.tool_registry,
                parent_permission=self.tool_registry.permission,
                session_manager=self.session_manager,
                compaction_config=self.compaction_config,
                on_complete=_on_complete,
                event_sink=self._event_sinks.get(parent_session_id),
                task_id=task_id,
                parent_subagent_id=parent_subagent_id,
                subagent_depth=subagent_depth,
                description=description,
            )
            return f"Sub-agent [{agent_info.name}] started (id: {task_id[:8]}). I'll notify you when it completes."

        # Track nesting for foreground
        ctx = self._session_contexts.get(parent_session_id)
        prev_subagent_id = ctx.subagent_id if ctx else None
        prev_subagent_depth = ctx.subagent_depth if ctx else 0
        if ctx:
            ctx.subagent_id = task_id
            ctx.subagent_depth = subagent_depth

        try:
            result = await self._run_subagent_foreground(
                parent_session_id,
                agent_info,
                prompt,
                event_sink=self._event_sinks.get(parent_session_id),
                task_id=task_id,
                parent_subagent_id=parent_subagent_id,
                subagent_depth=subagent_depth,
                description=description,
            )
        finally:
            if ctx:
                ctx.subagent_id = prev_subagent_id
                ctx.subagent_depth = prev_subagent_depth

        if todo_id:
            from laffyhand.agent.session.todo import TodoUpdate

            self.todo_manager.update_task(
                todo_id,
                parent_session_id,
                TodoUpdate(status="completed"),
            )

        return result

    async def _run_subagent_foreground(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
        task_id: str = "",
        parent_subagent_id: str | None = None,
        subagent_depth: int = 0,
        description: str = "",
    ) -> str:
        child_state, child_registry = build_subagent_state(
            self.session_manager,
            parent_session_id,
            agent_info,
            prompt,
            self.tool_registry.permission,
            self.tool_registry,
        )

        llm = self._llm_for_session(parent_session_id)

        if event_sink:
            await event_sink(
                SubAgentStart(
                    id=task_id,
                    parent_id=parent_subagent_id,
                    agent_type=agent_info.name,
                    description=description or prompt[:80],
                    mode="foreground",
                    depth=subagent_depth,
                )
            )

        result_content = ""
        tool_call_count = 0
        async for event in agent_loop(
            child_state,
            llm,
            child_registry,
            compaction_config=CompactionConfig(
                tail_turns=self.compaction_config.tail_turns,
            ),
            max_steps=agent_info.max_steps,
            session_manager=self.session_manager,
        ):
            if event_sink:
                if isinstance(event, TextDelta):
                    await event_sink(
                        SubAgentDelta(
                            id=task_id,
                            kind="text",
                            content=event.text,
                        )
                    )
                elif isinstance(event, ReasoningDelta):
                    await event_sink(
                        SubAgentDelta(
                            id=task_id,
                            kind="reasoning",
                            content=event.text,
                        )
                    )
                elif isinstance(event, StreamToolCall):
                    tool_call_count += 1
                    await event_sink(
                        SubAgentDelta(
                            id=task_id,
                            kind="tool",
                            tool_name=event.name,
                            tool_input=event.input,
                        )
                    )
                elif isinstance(event, (StepStart, TextStart, TextEnd, ReasoningStart, ReasoningEnd, Compacting)):
                    await event_sink(event)
            if isinstance(event, StepFinish):
                last_assistant_msg = None
                for msg in reversed(child_state.messages):
                    if isinstance(msg, AssistantMessage) and msg.content:
                        last_assistant_msg = msg
                        break
                if last_assistant_msg is not None and last_assistant_msg.content:
                    result_content = last_assistant_msg.content

        assert child_state.session_id is not None
        self.session_manager.save_state(child_state.session_id, child_state)
        self.session_manager.complete(child_state.session_id)

        result = result_content.strip()
        if not result:
            result = "[No output]"

        if event_sink:
            step_usage = child_state.usage
            await event_sink(
                SubAgentEnd(
                    id=task_id,
                    status="completed",
                    summary=result[:200],
                    tool_count=tool_call_count,
                    input_tokens=step_usage.total_input,
                    output_tokens=step_usage.total_output,
                )
            )

        return f"<task>\n{result}\n</task>"

    def _should_generate_title(self, session_id: str, trigger: str) -> bool:
        """Check if title generation should proceed based on mode, trigger, and session state."""
        if self.title_config.mode == "off":
            return False
        if self.title_config.mode != trigger:
            return False
        session = self.session_manager.get(session_id)
        return session is not None and not session.title

    def _schedule_title_generation(self, session_id: str, trigger: str) -> None:
        """Fire-and-forget title generation for background triggers (on_create, on_compact)."""
        if not self._should_generate_title(session_id, trigger):
            return
        asyncio.create_task(self._do_generate_title(session_id))

    async def _generate_title(self, session_id: str, trigger: str) -> bool:
        """Synchronously generate and save title. Returns True if title was generated."""
        if not self._should_generate_title(session_id, trigger):
            return False
        title = await self._do_generate_title(session_id)
        return bool(title)

    async def _do_generate_title(self, session_id: str) -> str | None:
        """Call LLM to generate a title and save to DB. Returns the title or None."""
        try:
            from laffyhand.agent.title import generate_title

            llm = self._llm_for_session(session_id)
            title = await generate_title(
                self.session_manager,
                session_id,
                llm,
                self.title_config,
            )
            if title:
                logger.info(f"Auto-generated title for session {session_id}: {title}")
            return title
        except Exception:
            logger.exception(f"Title generation failed for session {session_id}")
            return None

    def interrupt_session(self, session_id: str) -> bool:
        state = self._states.get(session_id)
        if state is None:
            return False
        state.interrupt_requested = True
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
        for sid, state in list(self._states.items()):
            save_id = state.session_id or sid
            if self.session_manager.get(save_id):
                self.session_manager.save_state(save_id, state)
                logger.info(f"Session state saved: {sid} (session_id={save_id})")
        self._states.clear()
        await self.mcp_service.disconnect_all()
        self.session_manager.close()
        logger.info("Agent shutdown complete")
