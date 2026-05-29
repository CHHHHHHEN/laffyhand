import json
from typing import Optional, Literal, Generator
from loguru import logger as _logger
from dataclasses import dataclass

from laffyhand.agent.schemas import (
    AgentState, AssistantMessage, CompactionConfig, StreamText, StreamReasoning,
    StreamToolCall, StreamFinish, StreamError, FinishReason,
    ToolCallContent, ToolMessage, Usage, UserMessage, estimate_tokens,
)
from laffyhand.agent.context import compact, estimate_messages_tokens, is_overflow
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.tools import ToolRegistry


@dataclass
class AgentEvent:
    type: Literal["reasoning", "tool_calls", "content", "tool_result", "compacting"]
    data: str
    finish_reason: Optional[FinishReason]
    usage: Optional[Usage] = None


# TODO: 添加 SUBTASK subagent 调用，通过 task tool 递归 agent_loop
# TODO: 添加 StructuredOutput tool（response_format=json_schema 时注入）
# TODO: 异步生成 session title（step 1 时另起 LLM 调用）
# TODO: 异步计算 summary（step 1 时另起 LLM 调用）
# TODO: 添加 StepStartPart/StepFinishPart 事件，含 worktree 快照和 diff


def agent_loop(
    agent_state: AgentState,
    llm: LLM,
    tool_registry: ToolRegistry,
    compaction_config: CompactionConfig = CompactionConfig(),
) -> Generator[AgentEvent, None, None]:
    messages = agent_state.messages
    context_size = agent_state.usage.context_size

    while True:
        reasoning_buf: list[str] = []
        content_buf: list[str] = []
        tool_calls: list[ToolCallContent] = []
        finish_reason: FinishReason | None = None
        usage: Usage | None = None
        tool_definitions = tool_registry.build_tool_definitions()

        for event in llm.stream(messages, tools=tool_definitions):
            if isinstance(event, StreamReasoning):
                reasoning_buf.append(event.delta)
                yield AgentEvent("reasoning", event.delta, None)
            elif isinstance(event, StreamText):
                content_buf.append(event.delta)
                yield AgentEvent("content", event.delta, None)
            elif isinstance(event, StreamToolCall):
                tool_calls.append(ToolCallContent(
                    tool_call_id=event.tool_call_id,
                    tool_name=event.tool_name,
                    args=event.args,
                ))
                yield AgentEvent("tool_calls", event.args, "tool_calls")
            elif isinstance(event, StreamFinish):
                finish_reason = event.finish_reason
                usage = event.usage
            elif isinstance(event, StreamError):
                _logger.error(f"Stream error: {event.error}")
                finish_reason = "error"

        agent_state.turn_count += 1

        if usage is None:
            content_text = "".join(content_buf)
            _logger.warning("API did not return usage, falling back to estimate_tokens")
            usage = Usage(
                input_tokens=estimate_tokens(content_text),
                output_tokens=estimate_tokens(content_text),
            )

        assistant_msg = AssistantMessage(
            content="".join(content_buf) if content_buf else None,
            reasoning="".join(reasoning_buf) if reasoning_buf else None,
            tool_calls=tool_calls if tool_calls else None,
            tokens=usage,
        )
        messages.append(assistant_msg)
        agent_state.usage.add(usage)
        yield AgentEvent("content", "", finish_reason, usage=usage)

        if finish_reason == "tool_calls" and tool_calls:
            for tc in tool_calls:
                params = json.loads(tc.args)
                result = tool_registry.run_tool(tc.tool_name, params)
                messages.append(ToolMessage(
                    tool_call_id=tc.tool_call_id,
                    content=result.result,
                ))
                yield AgentEvent("tool_result", result.result, None)
            continue

        if finish_reason is not None:
            _curr_tokens = estimate_messages_tokens(messages)

            if context_size and is_overflow(_curr_tokens, context_size):
                _logger.info("Context overflow detected, compacting...")
                yield AgentEvent("compacting", "Compacting conversation history...", None)
                if compact(agent_state, llm, compaction_config):
                    messages = agent_state.messages
                    if compaction_config.auto_continue:
                        messages.append(UserMessage(
                            content="Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.",
                        ))
                        yield AgentEvent("compacting", "Continuing after compaction...", None)
                        continue
                else:
                    _logger.warning("Context compaction failed, stopping to avoid overflow")
            break
