from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from laffyhand.core._utils import estimate_tokens
from laffyhand.core.llm.specs.models import Message, ToolMessage

if TYPE_CHECKING:
    from laffyhand.core.schemas import CompactionConfig


def prune(
    messages: list[Message],
    curr_context_usage: int = 0,
    context_size: int = 0,
    config: CompactionConfig | None = None,
) -> list[Message]:
    if config is None:
        from laffyhand.core.schemas import CompactionConfig
        config = CompactionConfig()

    prune_protect = config.prune_protect
    prune_minimum = config.prune_minimum
    prune_min_savings = config.prune_min_savings

    if curr_context_usage and context_size and curr_context_usage < context_size * 0.7:
        return messages

    tool_indices: list[int] = []
    total_tokens = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, ToolMessage):
            total_tokens += estimate_tokens(msg.content)
            tool_indices.append(i)
    logger.trace(
        f"Prune: found {len(tool_indices)} ToolMessages, total_tokens={total_tokens}"
    )
    if total_tokens <= prune_protect:
        logger.trace(
            f"Total tokens {total_tokens} <= prune_protect {prune_protect}, skipping"
        )
        return messages
    target = max(prune_minimum, total_tokens // 2)
    pruned = 0
    result = list(messages)
    for idx in reversed(tool_indices):
        msg = result[idx]
        if not isinstance(msg, ToolMessage):
            continue
        old_t = estimate_tokens(msg.content)
        if old_t < prune_min_savings:
            continue
        if total_tokens - pruned <= target:
            break
        new_content = f"[Old tool result content cleared: {old_t} tokens]"
        result[idx] = ToolMessage(
            tool_call_id=msg.tool_call_id,
            content=new_content,
        )
        pruned += old_t - estimate_tokens(new_content)
        logger.trace(
            f"Pruned message at index {idx}: {old_t} -> {estimate_tokens(new_content)} tokens"
        )
    logger.info(f"Pruned {pruned} tokens from tool outputs")
    return result


__all__ = ["prune"]
