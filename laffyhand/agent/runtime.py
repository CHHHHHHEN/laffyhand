from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Sequence
from threading import Lock
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.agent.schemas import (
    AgentState,
    CompactionConfig,
    SessionUsage,
    SystemMessage,
)
from laffyhand.agent.agent import AgentRegistry
from laffyhand.agent.skill import SkillRegistry
from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.subagent.manager import SubagentManager, build_subagent_state
from laffyhand.agent.tools.registry import ToolRegistry
from laffyhand.agent.tools.file import ReadTool, WriteTool, EditTool, GlobTool, GrepTool
from laffyhand.agent.tools.bash import BashTool
from laffyhand.agent.tools.todo import TodowriteTool
from laffyhand.agent.session.todo import TodoManager
from laffyhand.agent.tools.skill_tool import SkillTool
from laffyhand.agent.tools.task import TaskTool
from laffyhand.agent.tools.mcp_manage import (
    MCPListTool,
    MCPConnectTool,
    MCPDisconnectTool,
)
from laffyhand.agent.mcp import MCPService
from laffyhand.agent.loop import agent_loop, StepFinish
from laffyhand.agent.llm.factory import build_route
from laffyhand.agent.llm.facade import LLM

if TYPE_CHECKING:
    from laffyhand.agent.agent import AgentInfo

from laffyhand.config import LaffyConfig


MAX_SUBAGENT_DEPTH = 3


class AgentRuntime:
    def __init__(
        self,
        config: LaffyConfig,
        llm: Any = None,
        *,
        session_manager: SessionManager | None = None,
        mcp_service: MCPService | None = None,
    ) -> None:
        self._config = config
        self.llm = llm

        self.session_manager = session_manager or SessionManager(config.db.path)
        self.mcp_service = mcp_service or MCPService()
        self.compaction_config = CompactionConfig(
            tail_turns=config.agent.compaction_tail_turns,
        )
        self.title_config = TitleConfig(mode=config.agent.title_mode)  # type: ignore[arg-type]
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

        self.todo_manager = TodoManager(self.session_manager.connection)

        self._states: dict[str, AgentState] = {}
        self._pending_permissions: dict[str, tuple[asyncio.Event, str, str, bool | None]] = {}
        self._session_id: str | None = None
        self._active_session_id: str | None = None
        self._task_tool: TaskTool | None = None
        self._preferences: str | None = None
        self._preference_files: dict[str, str] = {}
        self._pref_lock = Lock()

    def _build_llm(self, provider: str, model: str) -> LLM:
        from laffyhand.config import resolve_provider
        provider_key, provider_cfg = resolve_provider(self._config.llm, provider)
        route = build_route(provider_cfg.type, provider_cfg.base_url, provider_cfg.api_key)
        logger.info(f"Built LLM: provider={provider_key}, model={model}")
        return LLM(model=model, route=route)

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
        self.tool_registry.register_tool(TodowriteTool(self.todo_manager))

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

        def _update_skill_description():
            summary = self.skill_registry.build_skills_summary()
            if summary:
                skill_tool.description = f"Load and inject a skill into context.\n\n{summary}"
            else:
                skill_tool.description = "Load and inject a skill into context."

        self.tool_registry.on_build_defs(_update_skill_description)
        _update_skill_description()

    @property
    def context_size(self) -> int:
        return self._context_size

    @property
    def state(self) -> AgentState | None:
        if self._session_id is None:
            return None
        return self._states.get(self._session_id)

    @state.setter
    def state(self, new_state: AgentState) -> None:
        if new_state.session_id:
            self._session_id = new_state.session_id
            self._states[new_state.session_id] = new_state

    @property
    def current_session_id(self) -> str | None:
        return self._session_id

    def get_state(self, session_id: str) -> AgentState | None:
        return self._states.get(session_id)

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

    def _load_preferences(self) -> str:
        with self._pref_lock:
            if self._preferences is not None:
                return self._preferences
            self._preference_files = self._read_preference_files()
            sections = [
                f"<preference>\n{text}\n</preference>"
                for text in self._preference_files.values()
            ]
            self._preferences = "\n".join(sections) if sections else ""
            return self._preferences

    def poll_new_preferences(self) -> str:
        current = self._read_preference_files()
        changed = False
        sections: list[str] = []

        with self._pref_lock:
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
                self._preferences = None  # invalidate cache so next _load_preferences re-reads
        return "\n".join(sections) if sections else ""

    def build_system_prompt(self, base_prompt: str) -> str:
        parts: list[str] = []
        parts.append(f"<soul>\n{base_prompt.strip()}\n</soul>")

        env_parts = [
            f"Working directory: {os.getcwd()}",
            f"Platform: {sys.platform}",
        ]
        parts.append("<env>\n" + "\n".join(env_parts) + "\n</env>")

        parts.append(self.tool_registry.build_tool_prompt())

        if self.skill_registry.all():
            parts.append(self.skill_registry.build_skills_summary())

        preferences = self._load_preferences()
        if preferences:
            parts.append(preferences)

        return "\n".join(parts)

    def create_initial_state(
        self,
        system_message: SystemMessage,
        provider: str = "",
        model: str = "",
    ) -> AgentState:
        session = self.session_manager.create(
            cwd=os.getcwd(), provider=provider, model=model,
        )
        state = AgentState(
            messages=[system_message],
            session_id=session.id,
            usage=SessionUsage(context_size=self._context_size),
        )
        self._states[session.id] = state
        self._session_id = session.id
        return state

    def save_current_state(self) -> None:
        if self._session_id is not None:
            state = self._states.get(self._session_id)
            if state is not None:
                sid = state.session_id or self._session_id
                if self.session_manager.get(sid):
                    self.session_manager.save_state(sid, state)
                else:
                    logger.warning(f"save_current_state: session {sid} not found in DB, skipping")

    def complete_current_session(self) -> None:
        if self._session_id is not None:
            state = self._states.get(self._session_id)
            if state is not None:
                sid = state.session_id or self._session_id
                if self.session_manager.get(sid):
                    self.session_manager.save_state(sid, state)
                self.session_manager.complete(sid)

    def switch_session(self, session_id: str) -> bool:
        self.save_current_state()
        tip = self.session_manager.get_compression_tip(session_id)
        loaded = self.session_manager.load_state(tip)
        if loaded is None:
            return False
        loaded.usage.context_size = self._context_size
        loaded.session_id = session_id  # keep key consistent with _states dict
        self._states[session_id] = loaded
        self._session_id = session_id
        return True

    def new_session(
        self,
        system_message: SystemMessage,
        provider: str = "",
        model: str = "",
    ) -> AgentState:
        self.complete_current_session()
        session = self.session_manager.create(
            cwd=os.getcwd(), provider=provider, model=model,
        )
        state = AgentState(
            messages=[system_message] if system_message else [],
            session_id=session.id,
            turn_count=0,
            step=0,
            usage=SessionUsage(context_size=self._context_size),
        )
        self._states[session.id] = state
        self._session_id = session.id
        return state

    def fork_session(self) -> str | None:
        if self._session_id is None:
            return None
        state = self._states.get(self._session_id)
        if state is None or not state.session_id:
            return None
        self.save_current_state()
        child = self.session_manager.fork(state.session_id)
        import copy
        forked = copy.deepcopy(state)
        forked.session_id = child.id
        self._states[child.id] = forked
        self._session_id = child.id
        return child.id

    def _llm_for_session(self, session_id: str) -> LLM:
        from laffyhand.config import resolve_provider, resolve_model

        session = self.session_manager.get(session_id)
        provider = session.provider if session and session.provider else None
        model = session.model if session and session.model else None
        if not provider or not model:
            try:
                provider_key, provider_cfg = resolve_provider(self._config.llm)
                provider = provider_key
                model = model or resolve_model(provider_cfg).name
            except ValueError:
                logger.warning(
                    f"Session {session_id}: could not resolve provider/model, "
                    f"falling back to default LLM"
                )
        if provider and model:
            return self._build_llm(provider, model)
        if self.llm is not None:
            return self.llm  # type: ignore[return-value]
        raise RuntimeError("No LLM available for session")

    async def run_agent_turn(self, session_id: str | None = None):
        sid = session_id or self._session_id
        assert sid is not None
        state = self._states.get(sid)
        assert state is not None, f"state not found for session {sid}"
        self._active_session_id = sid
        llm = self._llm_for_session(sid)
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
                on_compacted=lambda child_sid: self._schedule_title_generation(child_sid, "on_compact"),
            ):
                yield event
        finally:
            self._active_session_id = None

    async def create_subagent(
        self,
        agent_info: AgentInfo,
        prompt: str,
        description: str = "",
        background: bool = False,
        todo_id: str | None = None,
    ) -> str:
        parent_session_id = self._active_session_id or self._session_id
        assert parent_session_id is not None

        depth = self.session_manager.get_depth(parent_session_id)
        if depth > MAX_SUBAGENT_DEPTH:
            return (
                f"Error: maximum sub-agent depth ({MAX_SUBAGENT_DEPTH}) exceeded. "
                "Cannot spawn further sub-agents."
            )

        if todo_id:
            from laffyhand.agent.session.models import TodoUpdate
            self.todo_manager.update_task(
                todo_id, parent_session_id,
                TodoUpdate(status="in_progress"),
            )

        if background:
            assert self.subagent_manager is not None
            bg_llm = self._llm_for_session(parent_session_id)

            def _on_complete(_task_id: str, success: bool) -> None:
                if todo_id:
                    from laffyhand.agent.session.models import TodoUpdate
                    self.todo_manager.update_task(
                        todo_id, parent_session_id,
                        TodoUpdate(
                            status="completed" if success else "pending",
                        ),
                    )

            task_id: str = await self.subagent_manager.spawn(
                parent_session_id=parent_session_id,
                agent_info=agent_info,
                prompt=prompt,
                llm=bg_llm,
                tool_registry=self.tool_registry,
                parent_permission=self.tool_registry.permission,
                session_manager=self.session_manager,
                compaction_config=self.compaction_config,
                on_complete=_on_complete,
            )
            return f"Sub-agent [{agent_info.name}] started (id: {task_id[:8]}). I'll notify you when it completes."

        result = await self._run_subagent_foreground(
            parent_session_id,
            agent_info,
            prompt,
        )

        if todo_id:
            from laffyhand.agent.session.models import TodoUpdate
            self.todo_manager.update_task(
                todo_id, parent_session_id,
                TodoUpdate(status="completed"),
            )

        return result

    async def _run_subagent_foreground(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
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

        result_parts: list[str] = []
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
            if isinstance(event, StepFinish):
                last_msg = child_state.messages[-1]
                if hasattr(last_msg, "content") and last_msg.content:
                    if not isinstance(last_msg, SystemMessage):
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
        if self._session_id is None:
            return None
        state = self._states.get(self._session_id)
        sid = state.session_id if state and state.session_id else self._session_id
        from laffyhand.agent.title import generate_title

        llm = self._llm_for_session(sid)
        return await generate_title(
            self.session_manager,
            sid,
            llm,
            self.title_config,
        )

    def _schedule_title_generation(self, session_id: str, trigger: str) -> None:
        if self.title_config.mode == "off":
            return
        if self.title_config.mode != trigger:
            return
        session = self.session_manager.get(session_id)
        if session is None or session.title:
            return
        asyncio.create_task(self._do_generate_title(session_id))

    async def _do_generate_title(self, session_id: str) -> None:
        try:
            from laffyhand.agent.title import generate_title

            llm = self._llm_for_session(session_id)
            title = await generate_title(
                self.session_manager, session_id, llm, self.title_config,
            )
            if title:
                logger.info(f"Auto-generated title for session {session_id}: {title}")
        except Exception:
            logger.exception(f"Title generation failed for session {session_id}")

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
