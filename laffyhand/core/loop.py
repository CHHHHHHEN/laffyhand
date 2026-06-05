from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

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
)
from laffyhand.core.schemas import (
    AgentState,
    CompactionConfig,
    RetryConfig,
    StepStart,
    TextStart,
    TextDelta,
    TextEnd,
    ReasoningStart,
    ReasoningDelta,
    ReasoningEnd,
    ToolCall,
    ToolResult,
    ToolError,
    StepFinish,
    Compacting,
    UsageUpdate,
    TodoUpdate,
    AgentEvent,
)

from laffyhand.core.compaction import compact_on_overflow
from laffyhand.core.prune import prune
from laffyhand.core.tools.tool_executor import ToolExecutionResult, ToolExecutor
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
        )
    return agent_state.messages


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
    # Track how many messages have been persisted to DB,
    # so we can store all new messages (not just [-1:]) each turn.
    _stored_count = len(agent_state.messages)

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
                # Messages were replaced by compaction summary, reset store tracker
                _stored_count = len(agent_state.messages)
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
            content_buf: list[str] = []
            reasoning_buf: list[str] = []
            tool_calls: list[ToolCallContent] = []
            finish_reason: FinishReason | None = None
            usage: Usage | None = None
            text_id: str | None = None
            reasoning_id: str | None = None

            async for event in llm.stream(llm_context, tools=tool_definitions):
                if isinstance(event, StreamReasoning):
                    reasoning_buf.append(event.delta)
                    if reasoning_id is None:
                        reasoning_id = f"reasoning-{step_index}"
                        yield ReasoningStart(id=reasoning_id)
                    yield ReasoningDelta(id=reasoning_id, text=event.delta)
                elif isinstance(event, StreamText):
                    content_buf.append(event.delta)
                    if text_id is None:
                        text_id = f"text-{step_index}"
                        yield TextStart(id=text_id)
                    yield TextDelta(id=text_id, text=event.delta)
                elif isinstance(event, StreamToolCall):
                    tool_calls.append(
                        ToolCallContent(
                            tool_call_id=event.tool_call_id,
                            tool_name=event.tool_name,
                            args=event.args,
                        )
                    )
                    yield ToolCall(
                        id=event.tool_call_id,
                        name=event.tool_name,
                        input=event.args,
                    )
                elif isinstance(event, StreamFinish):
                    finish_reason = event.finish_reason
                    usage = event.usage
                elif isinstance(event, StreamError):
                    logger.error(f"Stream error: {event.error}")
                    finish_reason = "error"

            # End in-flight content segments
            if text_id is not None:
                yield TextEnd(id=text_id)
            if reasoning_id is not None:
                yield ReasoningEnd(id=reasoning_id)

            # Decide whether to retry, commit partial, or commit error
            if finish_reason != "error":
                _final_content = content_buf
                _final_reasoning = reasoning_buf
                _final_tool_calls = tool_calls
                _final_finish_reason = finish_reason
                _final_usage = usage
                break

            if content_buf or tool_calls:
                _final_content = content_buf
                _final_reasoning = reasoning_buf
                _final_tool_calls = tool_calls
                _final_finish_reason = finish_reason
                _final_usage = usage
                break

            if _retry_count >= retry_config.max_retries:
                _final_content = content_buf
                _final_reasoning = reasoning_buf
                _final_finish_reason = finish_reason
                _final_usage = usage
                break

            _retry_count += 1
            delay = min(
                retry_config.base_delay * (2 ** (_retry_count - 1)),
                retry_config.max_delay,
            )
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
                    await ToolExecutor.execute(
                        tool_registry,
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

            if session_manager is not None and agent_state.session_id:
                new_msgs = agent_state.messages[_stored_count:]
                if new_msgs:
                    session_manager.store_messages(
                        agent_state.session_id, new_msgs
                    )
                    _stored_count = len(agent_state.messages)
            continue

        yield StepFinish(index=step_index, reason=finish_reason or "stop", usage=usage)

        if finish_reason is not None:
            if session_manager is not None and agent_state.session_id:
                new_msgs = agent_state.messages[_stored_count:]
                if new_msgs:
                    session_manager.store_messages(
                        agent_state.session_id, new_msgs
                    )
                    _stored_count = len(agent_state.messages)
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
                # Messages were replaced by compaction summary, reset store tracker
                _stored_count = len(agent_state.messages)
                yield Compacting(data="Compacting conversation history...")
                if compaction_config.auto_continue:
                    agent_state.messages.append(
                        UserMessage(
                            content="Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.",
                        )
                    )
                    if session_manager is not None and agent_state.session_id:
                        session_manager.store_messages(
                            agent_state.session_id, agent_state.messages[_stored_count:]
                        )
                        _stored_count = len(agent_state.messages)
                    yield Compacting(data="Continuing after compaction...")
                    continue
            break
