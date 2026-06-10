from __future__ import annotations

from collections.abc import Sequence

from loguru import logger

from laffyhand.core._utils import estimate_tokens
from laffyhand.core.domain.messages import (
    AgentSwitchedMessage,
    CompactionMessage,
    Message,
    ModelSwitchedMessage,
    ToolMessage,
)
from laffyhand.core.models import CompactionConfig


def prune(
    messages: Sequence[Message],
    curr_context_usage: int = 0,
    context_size: int = 0,
    config: CompactionConfig | None = None,
) -> list[Message]:
    if config is None:
        config = CompactionConfig()

    protect_window = config.prune_protect  # 40K default
    min_savings = config.prune_min_savings  # 50 default

    result = list(messages)
    has_tool_msgs = any(isinstance(m, ToolMessage) for m in result)
    if not has_tool_msgs:
        return result

    modified = False

    # Walk backwards from end, accumulate token distance
    # Tool messages outside the recent protect_window get pruned
    accumulated = 0
    pruned_tokens = 0
    for i in range(len(result) - 1, -1, -1):
        msg = result[i]
        tokens = _estimate_message_tokens_fast(msg)
        accumulated += tokens
        if accumulated <= protect_window:
            continue
        if not isinstance(msg, ToolMessage):
            continue
        old_t = estimate_tokens(msg.content)
        if old_t < min_savings:
            continue
        result[i] = ToolMessage(
            tool_call_id=msg.tool_call_id,
            tool_name=msg.tool_name,
            args=msg.args,
            content=f"[Old tool result content cleared: {old_t} tokens]",
        )
        pruned_tokens += old_t
        modified = True

    if not modified:
        return result
    logger.info(f"Pruned {pruned_tokens} tokens from tool outputs outside {protect_window}-token window")
    return result


def _estimate_message_tokens_fast(msg: Message) -> int:
    if isinstance(msg, ToolMessage):
        return estimate_tokens(msg.content)
    if isinstance(msg, (CompactionMessage, AgentSwitchedMessage, ModelSwitchedMessage)):
        return 0
    content = msg.content or ""
    return estimate_tokens(content)
