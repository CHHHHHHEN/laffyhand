from loguru import logger

from laffyhand.core._utils import estimate_tokens
from laffyhand.core.llm.specs.models import Message, ToolMessage


_PRUNE_PROTECT = 40_000
_PRUNE_MINIMUM = 20_000
_PRUNE_MIN_SAVINGS = 50


def prune(
    messages: list[Message],
    curr_context_usage: int = 0,
    context_size: int = 0,
) -> list[Message]:
    # If we know the actual token usage and it's well within context capacity,
    # skip pruning entirely — the char-based estimator overcounts tool tokens
    # compared to the LLM's real tokenizer, causing false positives.
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
    if total_tokens <= _PRUNE_PROTECT:
        logger.trace(
            f"Total tokens {total_tokens} <= _PRUNE_PROTECT {_PRUNE_PROTECT}, skipping"
        )
        return messages
    target = max(_PRUNE_MINIMUM, total_tokens // 2)
    pruned = 0
    result = list(messages)
    for idx in reversed(tool_indices):
        msg = result[idx]
        if not isinstance(msg, ToolMessage):
            continue
        old_t = estimate_tokens(msg.content)
        if old_t < _PRUNE_MIN_SAVINGS:
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
