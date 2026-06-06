from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
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


# ── Main agent loop ────────────────────────────────────────────


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
    context_size = agent_state.usage.context_size
    _compacted_this_step = False
    store = MessageStore(session_manager, agent_state.session_id)
    store.sync(len(agent_state.messages))

    while True:
        if agent_state.interrupt_requested:
            agent_state.interrupt_requested = False
            logger.debug("Agent loop interrupted by user request")
            break

        agent_state.step += 1
        _compacted_this_step = False
        logger.debug(f"Agent loop step {agent_state.step}")

        if agent_state.step > max_steps:
            logger.info(f"Reached max steps ({max_steps}), stopping")
            break

        if agent_state.step > 1 and context_size and not _compacted_this_step:
            if await compact_on_overflow(
                agent_state,
                llm,
                compaction_config,
                session_manager,
                on_compacted=on_compacted,
            ):
                _compacted_this_step = True
                store.sync(len(agent_state.messages))
                yield Compacting(data="Compacting conversation history...")
                continue

        # ── Mid-turn injection: drain background subagent results ──
        if subagent_manager is not None and agent_state.session_id:
            bg_results = await subagent_manager.poll_results(agent_state.session_id)
            for bg in bg_results:
                content = bg.content or bg.error or "[No output]"
                injected = UserMessage(
                    content=(
                        f"[Background task '{bg.agent_type}' (id: {bg.task_id[:8]}) completed]\n\n"
                        f"{content}"
                    ),
                )
                agent_state.messages.append(injected)
                logger.info(f"Injected subagent result: {bg.task_id[:8]}")

        # ── Preference injection: detect new/changed AGENTS.md ──
        if preference_checker is not None:
            new_prefs = await preference_checker()
            if new_prefs:
                wrapped = f"<system-reminder>\n{new_prefs}\n</system-reminder>"
                agent_state.messages.append(UserMessage(content=wrapped))
                logger.info("Injected new preferences via <system-reminder>")

        step_index = agent_state.step
        disabled_tools = agent_state.disabled_tools
        tool_definitions = await tool_registry.build_tool_definitions(exclude=disabled_tools)
        llm_context = build_llm_context(agent_state, compaction_config)
        logger.debug(
            f"Sending {len(llm_context)} messages to LLM, {len(tool_definitions)} tools"
        )

        yield StepStart(index=step_index)

        # ── Step-level retry loop ────────────────────────────────────
        _retry_count = 0
        _final_content: list[str] = []
        _final_reasoning: list[str] = []
        _final_tool_calls: list[ToolCallContent] = []
        _final_finish_reason: FinishReason | None = None
        _final_usage: Usage | None = None

        while True:
            converter = StreamEventConverter(step_index)

            async for event in llm.stream(llm_context, tools=tool_definitions):
                for ev in converter.handle(event):
                    yield ev

            for ev in converter.end_segments():
                yield ev

            # Decide whether to retry, commit partial, or commit error
            if converter.finish_reason != "error":
                _final_content = converter.content_buf
                _final_reasoning = converter.reasoning_buf
                _final_tool_calls = converter.tool_calls
                _final_finish_reason = converter.finish_reason
                _final_usage = converter.usage
                break

            if converter.content_buf or converter.tool_calls:
                _final_content = converter.content_buf
                _final_reasoning = converter.reasoning_buf
                _final_tool_calls = converter.tool_calls
                _final_finish_reason = converter.finish_reason
                _final_usage = converter.usage
                break

            if _retry_count >= retry_config.max_retries:
                _final_content = converter.content_buf
                _final_reasoning = converter.reasoning_buf
                _final_tool_calls = converter.tool_calls
                _final_finish_reason = converter.finish_reason
                _final_usage = converter.usage
                break

            _retry_count += 1
            delay = exponential_backoff(retry_config.base_delay, _retry_count, retry_config.max_delay)
            logger.warning(
                f"LLM stream error (attempt {_retry_count}/{retry_config.max_retries}), "
                f"retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)

        content_buf = _final_content
        reasoning_buf = _final_reasoning
        tool_calls = _final_tool_calls
        finish_reason = _final_finish_reason
        usage = _final_usage

        agent_state.turn_count += 1
        logger.debug(
            f"Turn {agent_state.turn_count} complete, finish_reason={finish_reason}"
        )

        # Ensure AssistantMessage always has content or tool_calls — the API rejects
        # assistant messages where both are absent (e.g. after a stream error).
        combined_content = "".join(content_buf) if content_buf else None
        if combined_content is None and not tool_calls:
            if finish_reason == "error":
                combined_content = "[Error: LLM stream failed]"
            elif finish_reason == "length":
                combined_content = "[Response truncated by token limit]"
            elif finish_reason == "content_filter":
                combined_content = "[Response filtered by content policy]"
            else:
                combined_content = "" if reasoning_buf else "[Empty response]"

        assistant_msg = AssistantMessage(
            content=combined_content,
            reasoning="".join(reasoning_buf) if reasoning_buf else None,
            tool_calls=tool_calls if tool_calls else None,
            tokens=usage,
        )
        agent_state.messages.append(assistant_msg)
        if usage is not None:
            agent_state.usage.add(usage)
            yield UsageUpdate(session_usage=agent_state.usage.model_dump())

        if finish_reason == "tool_calls" and tool_calls:
            logger.debug(f"Executing {len(tool_calls)} tool call(s)")
            exec_context = {
                "session_id": agent_state.session_id,
                "_claim_id": f"{agent_state.session_id}:preferences",
            }

            # Execute all tool calls in this turn in parallel
            async def _exec_one(
                _tc: ToolCallContent,
            ) -> tuple[str, str, ToolExecutionResult]:
                return (
                    _tc.tool_call_id,
                    _tc.tool_name,
                    await tool_registry.execute_tool_call(
                        _tc,
                        context=exec_context,
                    ),
                )

            exec_results: list[tuple[str, str, ToolExecutionResult]] = (
                await asyncio.gather(*[_exec_one(tc) for tc in tool_calls])
            )

            # Build a lookup for result ordering
            result_by_tool_id: dict[str, ToolExecutionResult] = {}
            for tc_id, tc_name, exec_result in exec_results:
                result_by_tool_id[tc_id] = exec_result

            for tc in tool_calls:
                exec_result = result_by_tool_id[tc.tool_call_id]
                agent_state.messages.append(exec_result.message)
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

            # Inject pending steer as a separate UserMessage —
            # never mutate an existing ToolMessage (preserves original for replay)
            if agent_state.pending_steer:
                steer_text = agent_state.pending_steer
                agent_state.pending_steer = None
                agent_state.messages.append(
                    UserMessage(content=f"[User steers: {steer_text}]")
                )
                logger.debug("Injected steer text as UserMessage")

            yield StepFinish(
                index=step_index, reason=finish_reason or "stop", usage=usage
            )

            await store.flush(agent_state.messages)
            continue

        yield StepFinish(index=step_index, reason=finish_reason or "stop", usage=usage)

        if finish_reason is not None:
            await store.flush(agent_state.messages)
            if (
                context_size
                and not _compacted_this_step
                and await compact_on_overflow(
                    agent_state,
                    llm,
                    compaction_config,
                    session_manager,
                    on_compacted=on_compacted,
                )
            ):
                _compacted_this_step = True
                store.sync(len(agent_state.messages))
                yield Compacting(data="Compacting conversation history...")
                if compaction_config.auto_continue:
                    agent_state.messages.append(
                        UserMessage(
                            content="Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.",
                        )
                    )
                    await store.flush(agent_state.messages)
                    yield Compacting(data="Continuing after compaction...")
                    continue
            break


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
    "build_llm_context",
    "MessageStore",
    "StreamEventConverter",
    "agent_loop",
    "LoopOrchestrator",
]
