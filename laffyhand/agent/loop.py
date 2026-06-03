from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from loguru import logger

from laffyhand.agent.llm.specs.models import AssistantMessage, UserMessage
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
    AgentEvent,
)

from laffyhand.agent.compaction import compact_on_overflow
from laffyhand.agent.context import build_llm_context
from laffyhand.agent.tool_executor import ToolExecutor
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.tools import ToolRegistry

if TYPE_CHECKING:
    from laffyhand.agent.session import SessionManager
    from laffyhand.agent.subagent.manager import SubagentManager


# ── Main agent loop ────────────────────────────────────────────


async def agent_loop(
    agent_state: AgentState,
    llm: LLM,
    tool_registry: ToolRegistry,
    compaction_config: CompactionConfig = CompactionConfig(),
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

        reasoning_buf: list[str] = []
        content_buf: list[str] = []
        tool_calls: list[ToolCallContent] = []
        finish_reason: FinishReason | None = None
        usage: Usage | None = None
        step_index = agent_state.step
        text_id: str | None = None
        reasoning_id: str | None = None
        disabled_tools = agent_state.disabled_tools
        tool_definitions = await tool_registry.build_tool_definitions(exclude=disabled_tools)
        llm_context = build_llm_context(agent_state, compaction_config)
        logger.debug(
            f"Sending {len(llm_context)} messages to LLM, {len(tool_definitions)} tools"
        )

        yield StepStart(index=step_index)

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
