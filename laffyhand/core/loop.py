from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.core.llm.specs.models import AssistantMessage, Message, UserMessage
from laffyhand.core.llm.specs.models import (
    StreamText,
    StreamReasoning,
    StreamToolCall,
    StreamFinish,
    StreamError,
    FinishReason,
    ToolCallContent,
    Usage,
    LLMEvent,
)
from laffyhand.core.schemas import (
    AgentState,
    CompactionConfig,
    RetryConfig,
)
from laffyhand.core.session.state_store import SessionStateStore
from laffyhand.core.events import (
    StepStart,
    TextStart,
    TextDelta,
    TextEnd,
    ReasoningStart,
    ReasoningDelta,
    ReasoningEnd,
    ToolResult,
    ToolError,
    StepFinish,
    Compacting,
    UsageUpdate,
    TodoUpdate,
    AgentEvent,
)

from laffyhand.core._utils import exponential_backoff
from laffyhand.core.compaction import compact_on_overflow
from laffyhand.core.prune import prune
from laffyhand.core.tools.registry import ToolExecutionResult
from laffyhand.core.llm.facade import LLM
from laffyhand.core.tools import ToolRegistry

if TYPE_CHECKING:
    from laffyhand.core.session import SessionManager
    from laffyhand.core.subagent.manager import SubagentManager


# ── Helpers ────────────────────────────────────────────────────


def build_llm_context(
    agent_state: AgentState,
    compaction_config: CompactionConfig,
) -> list[Message]:
    if compaction_config.prune:
        return prune(
            agent_state.messages,
            curr_context_usage=agent_state.usage.curr_context_usage,
            context_size=agent_state.usage.context_size,
            config=compaction_config,
        )
    return agent_state.messages


# ── Message persistence helper ───────────────────────────────────


class MessageStore:
    """Tracks and persists new messages since last flush."""

    def __init__(
        self, session_manager: SessionManager | None, session_id: str | None
    ) -> None:
        self._session_manager = session_manager
        self._session_id = session_id
        self._stored_count = 0

    def sync(self, total: int) -> None:
        self._stored_count = total

    async def flush(self, messages: list[Message]) -> None:
        if self._session_manager is not None and self._session_id:
            new_msgs = messages[self._stored_count:]
            if new_msgs:
                self._session_manager.store_messages(self._session_id, new_msgs)
                self._stored_count = len(messages)


# ── Stream event conversion helper ──────────────────────────────


class StreamEventConverter:
    """Converts LLM stream events to agent-level events, managing segment IDs."""

    def __init__(self, step_index: int) -> None:
        self.step_index = step_index
        self.content_buf: list[str] = []
        self.reasoning_buf: list[str] = []
        self.tool_calls: list[ToolCallContent] = []
        self.finish_reason: FinishReason | None = None
        self.usage: Usage | None = None
        self._text_id: str | None = None
        self._reasoning_id: str | None = None

    def handle(self, event: LLMEvent) -> list[AgentEvent]:
        events: list[AgentEvent] = []
        if isinstance(event, StreamReasoning):
            self.reasoning_buf.append(event.delta)
            if self._reasoning_id is None:
                self._reasoning_id = f"reasoning-{self.step_index}"
                events.append(ReasoningStart(id=self._reasoning_id))
            events.append(ReasoningDelta(id=self._reasoning_id, text=event.delta))
        elif isinstance(event, StreamText):
            self.content_buf.append(event.delta)
            if self._text_id is None:
                self._text_id = f"text-{self.step_index}"
                events.append(TextStart(id=self._text_id))
            events.append(TextDelta(id=self._text_id, text=event.delta))
        elif isinstance(event, StreamToolCall):
            tc = ToolCallContent(
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                args=event.args,
            )
            self.tool_calls.append(tc)
            events.append(event)
        elif isinstance(event, StreamFinish):
            self.finish_reason = event.finish_reason
            self.usage = event.usage
        elif isinstance(event, StreamError):
            logger.error(f"Stream error: {event.error}")
            self.finish_reason = "error"
        return events

    def end_segments(self) -> list[AgentEvent]:
        events: list[AgentEvent] = []
        if self._text_id is not None:
            events.append(TextEnd(id=self._text_id))
        if self._reasoning_id is not None:
            events.append(ReasoningEnd(id=self._reasoning_id))
        return events


# ── Turn context ─────────────────────────────────────────────


@dataclass
class TurnContext:
    content_buf: list[str] = field(default_factory=list)
    reasoning_buf: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallContent] = field(default_factory=list)
    finish_reason: FinishReason | None = None
    usage: Usage | None = None


# ── Agent turn class ─────────────────────────────────────────


class AgentTurn:
    """Encapsulates one agent turn lifecycle.

    Responsibilities: interrupt/step-gate checks, pre-turn compaction,
    subagent/preference injection, LLM streaming with retry, assistant
    message construction, tool execution, post-turn compaction, persistence.
    """

    def __init__(
        self,
        agent_state: AgentState,
        llm: LLM,
        tool_registry: ToolRegistry,
        compaction_config: CompactionConfig = CompactionConfig(),
        *,
        retry_config: RetryConfig = RetryConfig(),
        max_steps: int = 50,
        session_manager: SessionManager | None = None,
        subagent_manager: SubagentManager | None = None,
        preference_checker: Callable[[], Awaitable[str]] | None = None,
        on_compacted: Callable[[str], None] | None = None,
    ) -> None:
        self._agent_state = agent_state
        self._llm = llm
        self._tool_registry = tool_registry
        self._compaction_config = compaction_config
        self._retry_config = retry_config
        self._max_steps = max_steps
        self._session_manager = session_manager
        self._subagent_manager = subagent_manager
        self._preference_checker = preference_checker
        self._on_compacted = on_compacted

        self._context_size = agent_state.usage.context_size
        self._compacted_this_step = False
        self._store = MessageStore(session_manager, agent_state.session_id)
        self._tc: TurnContext | None = None

    async def run(self) -> AsyncIterator[AgentEvent]:
        self._store.sync(len(self._agent_state.messages))

        while True:
            if self._check_interrupt():
                break

            self._agent_state.step += 1
            self._compacted_this_step = False

            if self._agent_state.step > self._max_steps:
                logger.info(f"Reached max steps ({self._max_steps}), stopping")
                break

            if await self._compact_pre():
                yield Compacting(data="Compacting conversation history...")
                continue

            await self._inject_subagent_results()
            await self._inject_preferences()

            step_index = self._agent_state.step
            disabled_tools = self._agent_state.disabled_tools
            tool_definitions = await self._tool_registry.build_tool_definitions(
                exclude=disabled_tools,
            )
            llm_context = build_llm_context(self._agent_state, self._compaction_config)
            logger.debug(
                f"Sending {len(llm_context)} messages to LLM, {len(tool_definitions)} tools"
            )

            yield StepStart(index=step_index)

            self._tc = None
            async for ev in self._retry_llm(llm_context, tool_definitions, step_index):
                yield ev

            turn_ctx = self._tc
            assert turn_ctx is not None

            self._agent_state.turn_count += 1
            logger.debug(
                f"Turn {self._agent_state.turn_count} complete, finish_reason={turn_ctx.finish_reason}"
            )

            assistant_msg = self._build_assistant_message(turn_ctx)
            self._agent_state.messages.append(assistant_msg)

            if turn_ctx.usage is not None:
                self._agent_state.usage.add(turn_ctx.usage)
                yield UsageUpdate(
                    session_usage=self._agent_state.usage.model_dump(),
                )

            if turn_ctx.finish_reason == "tool_calls" and turn_ctx.tool_calls:
                async for ev in self._execute_tools(turn_ctx, step_index):
                    yield ev
                continue

            yield StepFinish(
                index=step_index,
                reason=turn_ctx.finish_reason or "stop",
                usage=turn_ctx.usage,
            )

            if turn_ctx.finish_reason is not None:
                await self._store.flush(self._agent_state.messages)
                if await self._compact_post():
                    yield Compacting(data="Compacting conversation history...")
                    if self._compaction_config.auto_continue:
                        self._agent_state.messages.append(
                            UserMessage(
                                content="Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.",
                            )
                        )
                        await self._store.flush(self._agent_state.messages)
                        yield Compacting(data="Continuing after compaction...")
                        continue
                break

    # ── Step lifecycle methods ──────────────────────────────────

    def _check_interrupt(self) -> bool:
        if self._agent_state.interrupt_requested:
            self._agent_state.interrupt_requested = False
            logger.debug("Agent loop interrupted by user request")
            return True
        return False

    async def _compact_pre(self) -> bool:
        if (
            self._agent_state.step > 1
            and self._context_size
            and not self._compacted_this_step
            and await compact_on_overflow(
                self._agent_state,
                self._llm,
                self._compaction_config,
                self._session_manager,
                on_compacted=self._on_compacted,
            )
        ):
            self._store.sync(len(self._agent_state.messages))
            self._compacted_this_step = True
            return True
        return False

    async def _inject_subagent_results(self) -> None:
        if self._subagent_manager is not None and self._agent_state.session_id:
            bg_results = await self._subagent_manager.poll_results(
                self._agent_state.session_id
            )
            for bg in bg_results:
                content = bg.content or bg.error or "[No output]"
                injected = UserMessage(
                    content=(
                        f"[Background task '{bg.agent_type}' (id: {bg.task_id[:8]}) completed]\n\n"
                        f"{content}"
                    ),
                )
                self._agent_state.messages.append(injected)
                logger.info(f"Injected subagent result: {bg.task_id[:8]}")

    async def _inject_preferences(self) -> None:
        if self._preference_checker is not None:
            new_prefs = await self._preference_checker()
            if new_prefs:
                wrapped = f"<system-reminder>\n{new_prefs}\n</system-reminder>"
                self._agent_state.messages.append(
                    UserMessage(content=wrapped),
                )
                logger.info("Injected new preferences via <system-reminder>")

    # ── LLM streaming & retry ──────────────────────────────────

    async def _retry_llm(
        self,
        context: list[Message],
        tool_definitions: list[Any],
        step_index: int,
    ) -> AsyncIterator[AgentEvent]:
        _retry_count = 0
        while True:
            converter = StreamEventConverter(step_index)

            async for event in self._llm.stream(context, tools=tool_definitions):
                for ev in converter.handle(event):
                    yield ev

            for ev in converter.end_segments():
                yield ev

            tc = self._decide_retry(converter, _retry_count)
            if tc is not None:
                self._tc = tc
                return

            _retry_count += 1
            delay = exponential_backoff(
                self._retry_config.base_delay,
                _retry_count,
                self._retry_config.max_delay,
            )
            logger.warning(
                f"LLM stream error (attempt {_retry_count}/{self._retry_config.max_retries}), "
                f"retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)

    def _decide_retry(
        self,
        converter: StreamEventConverter,
        retry_count: int,
    ) -> TurnContext | None:
        if converter.finish_reason != "error":
            return TurnContext(
                content_buf=converter.content_buf,
                reasoning_buf=converter.reasoning_buf,
                tool_calls=converter.tool_calls,
                finish_reason=converter.finish_reason,
                usage=converter.usage,
            )
        if converter.content_buf or converter.tool_calls:
            return TurnContext(
                content_buf=converter.content_buf,
                reasoning_buf=converter.reasoning_buf,
                tool_calls=converter.tool_calls,
                finish_reason=converter.finish_reason,
                usage=converter.usage,
            )
        if retry_count >= self._retry_config.max_retries:
            return TurnContext(
                content_buf=converter.content_buf,
                reasoning_buf=converter.reasoning_buf,
                tool_calls=converter.tool_calls,
                finish_reason=converter.finish_reason,
                usage=converter.usage,
            )
        return None

    # ── Assistant message construction ──────────────────────────

    def _build_assistant_message(self, turn_ctx: TurnContext) -> AssistantMessage:
        combined_content = "".join(turn_ctx.content_buf) if turn_ctx.content_buf else None
        if combined_content is None and not turn_ctx.tool_calls:
            if turn_ctx.finish_reason == "error":
                combined_content = "[Error: LLM stream failed]"
            elif turn_ctx.finish_reason == "length":
                combined_content = "[Response truncated by token limit]"
            elif turn_ctx.finish_reason == "content_filter":
                combined_content = "[Response filtered by content policy]"
            else:
                combined_content = (
                    "" if turn_ctx.reasoning_buf else "[Empty response]"
                )

        return AssistantMessage(
            content=combined_content,
            reasoning="".join(turn_ctx.reasoning_buf) if turn_ctx.reasoning_buf else None,
            tool_calls=turn_ctx.tool_calls if turn_ctx.tool_calls else None,
            tokens=turn_ctx.usage,
        )

    # ── Tool execution ──────────────────────────────────────────

    async def _execute_tools(
        self,
        turn_ctx: TurnContext,
        step_index: int,
    ) -> AsyncIterator[AgentEvent]:
        logger.debug(f"Executing {len(turn_ctx.tool_calls)} tool call(s)")
        exec_context: dict[str, str | None] = {
            "session_id": self._agent_state.session_id,
            "_claim_id": f"{self._agent_state.session_id}:preferences",
        }

        async def _exec_one(
            tc: ToolCallContent,
        ) -> tuple[str, str, ToolExecutionResult]:
            return (
                tc.tool_call_id,
                tc.tool_name,
                await self._tool_registry.execute_tool_call(tc, context=exec_context),
            )

        exec_results: list[tuple[str, str, ToolExecutionResult]] = (
            await asyncio.gather(*[_exec_one(tc) for tc in turn_ctx.tool_calls])
        )

        result_by_tool_id: dict[str, ToolExecutionResult] = {}
        for tc_id, tc_name, exec_result in exec_results:
            result_by_tool_id[tc_id] = exec_result

        for tc in turn_ctx.tool_calls:
            exec_result = result_by_tool_id[tc.tool_call_id]
            self._agent_state.messages.append(exec_result.message)
            if exec_result.is_error:
                yield ToolError(
                    id=tc.tool_call_id,
                    name=tc.tool_name,
                    message=exec_result.event_data,
                )
            else:
                yield ToolResult(
                    id=tc.tool_call_id,
                    name=tc.tool_name,
                    result=exec_result.event_data,
                )
                if tc.tool_name in ("todowrite", "task"):
                    yield TodoUpdate()

        if self._agent_state.pending_steer:
            steer_text = self._agent_state.pending_steer
            self._agent_state.pending_steer = None
            self._agent_state.messages.append(
                UserMessage(content=f"[User steers: {steer_text}]"),
            )
            logger.debug("Injected steer text as UserMessage")

        yield StepFinish(
            index=step_index,
            reason=turn_ctx.finish_reason or "stop",
            usage=turn_ctx.usage,
        )
        await self._store.flush(self._agent_state.messages)

    # ── Post-turn compaction ────────────────────────────────────

    async def _compact_post(self) -> bool:
        if (
            self._context_size
            and not self._compacted_this_step
            and await compact_on_overflow(
                self._agent_state,
                self._llm,
                self._compaction_config,
                self._session_manager,
                on_compacted=self._on_compacted,
            )
        ):
            self._store.sync(len(self._agent_state.messages))
            self._compacted_this_step = True
            return True
        return False


# ── Backward-compatible wrapper ────────────────────────────────


async def agent_loop(
    agent_state: AgentState,
    llm: LLM,
    tool_registry: ToolRegistry,
    compaction_config: CompactionConfig = CompactionConfig(),
    *,
    retry_config: RetryConfig = RetryConfig(),
    max_steps: int = 50,
    session_manager: SessionManager | None = None,
    subagent_manager: SubagentManager | None = None,
    preference_checker: Callable[[], Awaitable[str]] | None = None,
    on_compacted: Callable[[str], None] | None = None,
) -> AsyncIterator[AgentEvent]:
    turn = AgentTurn(
        agent_state,
        llm,
        tool_registry,
        compaction_config,
        retry_config=retry_config,
        max_steps=max_steps,
        session_manager=session_manager,
        subagent_manager=subagent_manager,
        preference_checker=preference_checker,
        on_compacted=on_compacted,
    )
    async for event in turn.run():
        yield event


# ── Orchestrator ────────────────────────────────────────────────

_TURN_DONE = object()


class LoopOrchestrator:
    """Manages agent turn lifecycle: foreground execution, background tasks, and cancellation."""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        tool_registry: ToolRegistry,
        subagent_manager: SubagentManager | None,
        llm_provider: Callable[[str], LLM],
        compaction_config: CompactionConfig,
        max_steps: int,
        preference_checker: Callable[[], Awaitable[str]] | None,
        title_scheduler: Callable[[str, str], None],
        session_store: SessionStateStore,
    ) -> None:
        self._session_manager = session_manager
        self._tool_registry = tool_registry
        self._subagent_manager = subagent_manager
        self._llm_provider = llm_provider
        self._compaction_config = compaction_config
        self._max_steps = max_steps
        self._preference_checker = preference_checker
        self._title_scheduler = title_scheduler
        self._session_store = session_store
        self._session_tasks: dict[str, asyncio.Task[None]] = {}
        self._session_event_queues: dict[str, asyncio.Queue[Any]] = {}

    async def run_agent_turn(
        self,
        session_id: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
    ):
        state = self._session_store.get(session_id)
        assert state is not None, f"state not found for session {session_id}"
        if event_sink is not None:
            self._session_store.set_event_sink(session_id, event_sink)
        llm = self._llm_provider(session_id)
        try:
            async for event in agent_loop(
                state,
                llm,
                self._tool_registry,
                compaction_config=self._compaction_config,
                max_steps=self._max_steps,
                session_manager=self._session_manager,
                subagent_manager=self._subagent_manager,
                preference_checker=self._preference_checker,
                on_compacted=lambda child_sid: self._title_scheduler(
                    child_sid, "on_compact"
                ),
            ):
                yield event
        finally:
            self._session_store.pop_event_sink(session_id)

    def is_session_running(self, session_id: str) -> bool:
        return session_id in self._session_tasks and not self._session_tasks[session_id].done()

    async def start_background_agent_turn(
        self,
        session_id: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
    ) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
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
                self._session_store.pop_event_sink(session_id)

        task = asyncio.create_task(_run())
        self._session_tasks[session_id] = task
        return queue

    def cancel_background_agent_turn(self, session_id: str) -> None:
        task = self._session_tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()

    async def cancel_all(self) -> None:
        for sid in list(self._session_tasks):
            self.cancel_background_agent_turn(sid)
        if self._session_tasks:
            await asyncio.wait(list(self._session_tasks.values()), timeout=5.0)


__all__ = [
    "AgentTurn",
    "TurnContext",
    "build_llm_context",
    "MessageStore",
    "StreamEventConverter",
    "agent_loop",
    "LoopOrchestrator",
]
