from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from loguru import logger

from laffyhand.agent.llm.specs.models import AssistantMessage, SystemMessage, ToolMessage, UserMessage
from laffyhand.agent.llm.specs.models import (
    StreamText,
    StreamReasoning,
    StreamToolCall,
    StreamFinish,
    StreamError,
    FinishReason,
    ToolCallContent,
    Usage,
)
from laffyhand.agent.schemas import (
    AgentState,
    CompactionConfig,
    estimate_tokens,
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
    StreamEvent,
)
from laffyhand.agent.compaction import (
    compact,
    compact_with_chain,
    wrap_last_user,
    attach_reminder,
    estimate_messages_tokens,
    is_overflow,
)
from laffyhand.agent.prune import prune
from laffyhand.agent.tool_executor import ToolExecutor
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.tools import ToolRegistry

if TYPE_CHECKING:
    from laffyhand.agent.session import SessionManager
    from laffyhand.agent.subagent.manager import SubagentManager


# ── Helpers ────────────────────────────────────────────────────


async def _compact_on_overflow(
    agent_state: AgentState,
    llm: LLM,
    compaction_config: CompactionConfig,
    session_manager: SessionManager | None = None,
    on_compacted: Callable[[str], None] | None = None,
) -> bool:
    tokens = estimate_messages_tokens(agent_state.messages)
    if not is_overflow(tokens, agent_state.usage.context_size):
        logger.debug(f"No compaction needed: {tokens} tokens within context limit")
        return False
    logger.info(f"Compaction triggered: {tokens} tokens")

    if session_manager is not None and agent_state.session_id:
        result = await compact_with_chain(agent_state, llm, compaction_config)
        if result is None:
            return False
        summary, original_system, tail = result
        child = session_manager.create_compacted_child(
            parent_id=agent_state.session_id,
            system_messages=original_system,
            summary_content=summary,
            tail_messages=tail,
        )
        summary_msg = SystemMessage(content=summary.strip())
        agent_state.session_id = child.id
        agent_state.messages = original_system + [summary_msg] + tail
        agent_state.step = 0
        if on_compacted is not None:
            on_compacted(child.id)
        return True

    if await compact(agent_state, llm, compaction_config):
        logger.info("Compaction succeeded")
        return True
    logger.warning("Compaction failed: could not compact conversation")
    return False


# ── Main agent loop ────────────────────────────────────────────


async def agent_loop(
    agent_state: AgentState,
    llm: LLM,
    tool_registry: ToolRegistry,
    compaction_config: CompactionConfig = CompactionConfig(),
    max_steps: int = 50,
    reminder: str | None = None,
    session_manager: SessionManager | None = None,
    subagent_manager: SubagentManager | None = None,
    preference_checker: Callable[[], Awaitable[str]] | None = None,
    on_compacted: Callable[[str], None] | None = None,
) -> AsyncIterator[StreamEvent]:
    context_size = agent_state.usage.context_size
    _compacted_this_step = False

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

        if reminder and agent_state.step == 1:
            agent_state.messages = attach_reminder(agent_state.messages, reminder)

        if agent_state.step > 1:
            agent_state.messages = wrap_last_user(agent_state.messages)

        if agent_state.step > 1 and context_size and not _compacted_this_step:
            if await _compact_on_overflow(
                agent_state,
                llm,
                compaction_config,
                session_manager,
                on_compacted=on_compacted,
            ):
                _compacted_this_step = True
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
                agent_state.messages.append(SystemMessage(content=wrapped))
                logger.info("Injected new preferences via <system-reminder>")

        reasoning_buf: list[str] = []
        content_buf: list[str] = []
        tool_calls: list[ToolCallContent] = []
        finish_reason: FinishReason | None = None
        usage: Usage | None = None
        step_index = agent_state.step
        text_id: str | None = None
        reasoning_id: str | None = None
        tool_definitions = await tool_registry.build_tool_definitions()
        logger.debug(
            f"Sending {len(agent_state.messages)} messages to LLM, {len(tool_definitions)} tools"
        )

        yield StepStart(index=step_index)

        async for event in llm.stream(agent_state.messages, tools=tool_definitions):
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

        agent_state.turn_count += 1
        logger.debug(
            f"Turn {agent_state.turn_count} complete, finish_reason={finish_reason}"
        )

        if usage is None:
            logger.warning("API did not return usage, falling back to estimate_tokens")
            usage = Usage(
                input_tokens=estimate_messages_tokens(agent_state.messages),
                output_tokens=estimate_tokens("".join(content_buf)),
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
        agent_state.usage.add(usage)

        if finish_reason == "tool_calls" and tool_calls:
            logger.debug(f"Executing {len(tool_calls)} tool call(s)")
            exec_context = {"session_id": agent_state.session_id}
            for tc in tool_calls:
                exec_result = await ToolExecutor.execute(
                    tool_registry,
                    tc,
                    context=exec_context,
                )
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

            # Inject pending steer into the last tool result
            if (
                agent_state.pending_steer
                and agent_state.messages
                and isinstance(agent_state.messages[-1], ToolMessage)
            ):
                steer_text = agent_state.pending_steer
                agent_state.pending_steer = None
                last_tool: ToolMessage = agent_state.messages[-1]
                steer_content = (
                    last_tool.content + f"\n\n[User steers: {steer_text}]"
                    if last_tool.content
                    else f"[User steers: {steer_text}]"
                )
                agent_state.messages[-1] = ToolMessage(
                    tool_call_id=last_tool.tool_call_id,
                    content=steer_content,
                    is_error=last_tool.is_error,
                )
                logger.debug("Injected steer text into tool result")

            yield StepFinish(
                index=step_index, reason=finish_reason or "stop", usage=usage
            )

            if compaction_config.prune:
                logger.debug("Pruning after tool calls")
                agent_state.messages = prune(agent_state.messages)
            if session_manager is not None and agent_state.session_id:
                session_manager.append_messages(
                    agent_state.session_id, agent_state.messages
                )
            continue

        yield StepFinish(index=step_index, reason=finish_reason or "stop", usage=usage)

        if finish_reason is not None:
            if session_manager is not None and agent_state.session_id:
                session_manager.append_messages(
                    agent_state.session_id, agent_state.messages
                )
            if (
                context_size
                and not _compacted_this_step
                and await _compact_on_overflow(
                    agent_state,
                    llm,
                    compaction_config,
                    session_manager,
                    on_compacted=on_compacted,
                )
            ):
                _compacted_this_step = True
                yield Compacting(data="Compacting conversation history...")
                if compaction_config.auto_continue:
                    agent_state.messages.append(
                        UserMessage(
                            content="Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.",
                        )
                    )
                    yield Compacting(data="Continuing after compaction...")
                    continue
            break
