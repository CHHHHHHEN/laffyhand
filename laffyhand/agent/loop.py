from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Optional, Literal

from loguru import logger
from pydantic import BaseModel

from laffyhand.agent.schemas import (
    AgentState, AssistantMessage, CompactionConfig, StreamText, StreamReasoning,
    StreamToolCall, StreamFinish, StreamError, FinishReason,
    ToolCallContent, ToolMessage, Usage, UserMessage, estimate_tokens,
)
from laffyhand.agent.compaction import (
    compact, compact_with_chain, wrap_last_user, attach_reminder,
    estimate_messages_tokens, is_overflow,
)
from laffyhand.agent.prune import prune
from laffyhand.agent.tool_executor import ToolExecutor
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.tools import ToolRegistry

if TYPE_CHECKING:
    from laffyhand.agent.session import SessionManager
    from laffyhand.agent.subagent.manager import SubagentManager


class AgentEvent(BaseModel):
    type: Literal["reasoning", "tool_calls", "content", "tool_result", "compacting"]
    data: str
    finish_reason: Optional[FinishReason] = None
    usage: Optional[Usage] = None
    session_usage: Optional[dict] = None
    leftover_steer: Optional[str] = None


async def _compact_on_overflow(
    agent_state: AgentState,
    llm: LLM,
    compaction_config: CompactionConfig,
    session_manager: SessionManager | None = None,
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
        summary_msg = UserMessage(content=summary.strip())
        agent_state.session_id = child.id
        agent_state.messages = original_system + [summary_msg] + tail
        agent_state.step = 0
        return True

    if await compact(agent_state, llm, compaction_config):
        logger.info("Compaction succeeded")
        return True
    logger.warning("Compaction failed: could not compact conversation")
    return False


async def agent_loop(
    agent_state: AgentState,
    llm: LLM,
    tool_registry: ToolRegistry,
    compaction_config: CompactionConfig = CompactionConfig(),
    max_steps: int = 50,
    reminder: str | None = None,
    session_manager: SessionManager | None = None,
    subagent_manager: SubagentManager | None = None,
) -> AsyncIterator[AgentEvent]:
    messages = agent_state.messages
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
            messages = attach_reminder(messages, reminder)
            agent_state.messages = messages

        if agent_state.step > 1:
            messages = wrap_last_user(messages)
            agent_state.messages = messages

        if agent_state.step > 1 and context_size and not _compacted_this_step:
            if await _compact_on_overflow(
                agent_state, llm, compaction_config, session_manager,
            ):
                _compacted_this_step = True
                messages = agent_state.messages
                yield AgentEvent(type="compacting", data="Compacting conversation history...")
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
                messages.append(injected)
                agent_state.messages = messages
                logger.info(f"Injected subagent result: {bg.task_id[:8]}")

        reasoning_buf: list[str] = []
        content_buf: list[str] = []
        tool_calls: list[ToolCallContent] = []
        finish_reason: FinishReason | None = None
        usage: Usage | None = None
        tool_definitions = await tool_registry.build_tool_definitions()
        logger.debug(f"Sending {len(messages)} messages to LLM, {len(tool_definitions)} tools")

        async for event in llm.stream(messages, tools=tool_definitions):
            if isinstance(event, StreamReasoning):
                reasoning_buf.append(event.delta)
                yield AgentEvent(type="reasoning", data=event.delta)
            elif isinstance(event, StreamText):
                content_buf.append(event.delta)
                yield AgentEvent(type="content", data=event.delta)
            elif isinstance(event, StreamToolCall):
                tool_calls.append(ToolCallContent(
                    tool_call_id=event.tool_call_id,
                    tool_name=event.tool_name,
                    args=event.args,
                ))
                yield AgentEvent(type="tool_calls", data=event.args, finish_reason="tool_calls")
            elif isinstance(event, StreamFinish):
                finish_reason = event.finish_reason
                usage = event.usage
            elif isinstance(event, StreamError):
                logger.error(f"Stream error: {event.error}")
                finish_reason = "error"

        agent_state.turn_count += 1
        logger.debug(f"Turn {agent_state.turn_count} complete, finish_reason={finish_reason}")

        if usage is None:
            logger.warning("API did not return usage, falling back to estimate_tokens")
            usage = Usage(
                input_tokens=estimate_messages_tokens(messages),
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
        messages.append(assistant_msg)
        agent_state.usage.add(usage)
        yield AgentEvent(type="content", data="", finish_reason=finish_reason, usage=usage)

        if finish_reason == "tool_calls" and tool_calls:
            logger.debug(f"Executing {len(tool_calls)} tool call(s)")
            for tc in tool_calls:
                exec_result = await ToolExecutor.execute(tool_registry, tc)
                messages.append(exec_result.message)
                yield AgentEvent(type="tool_result", data=exec_result.event_data)

            # Inject pending steer into the last tool result
            if agent_state.pending_steer and messages and isinstance(messages[-1], ToolMessage):
                steer_text = agent_state.pending_steer
                agent_state.pending_steer = None
                messages[-1].content += f"\n\n[User steers: {steer_text}]"
                logger.debug("Injected steer text into tool result")

            if compaction_config.prune:
                logger.debug("Pruning after tool calls")
                messages = prune(messages)
                agent_state.messages = messages
            if session_manager is not None and agent_state.session_id:
                session_manager.append_messages(agent_state.session_id, agent_state.messages)
            continue

        if finish_reason is not None:
            if session_manager is not None and agent_state.session_id:
                session_manager.append_messages(agent_state.session_id, agent_state.messages)
            if context_size and not _compacted_this_step and await _compact_on_overflow(
                agent_state, llm, compaction_config, session_manager,
            ):
                _compacted_this_step = True
                messages = agent_state.messages
                yield AgentEvent(type="compacting", data="Compacting conversation history...")
                if compaction_config.auto_continue:
                    messages.append(UserMessage(
                        content="Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.",
                    ))
                    yield AgentEvent(type="compacting", data="Continuing after compaction...")
                    continue
            break
