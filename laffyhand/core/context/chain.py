from __future__ import annotations

from loguru import logger

from laffyhand.core.domain.messages import (
    AssistantMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from laffyhand.core.domain.messages import (
    Message,
)
from laffyhand.core.models import AgentState, CompactionConfig
from laffyhand.core._utils import (
    estimate_message_tokens,
    estimate_tokens,
)
from laffyhand.core.llm.facade import LLM
from laffyhand.core.context._summarize import (
    _is_summary_content,
    _summary_depth,
    _summarize,
    _SUMMARY_TAG_OPEN,
    _SUMMARY_TAG_CLOSE,
)


def is_overflow(tokens: int, context_size: int, reserved: int) -> bool:
    if context_size <= 0:
        return False
    usable = max(context_size - reserved, context_size // 10)
    overflow = tokens >= usable
    if overflow:
        logger.trace(
            f"Overflow: {tokens} tokens vs usable {usable} (context_size={context_size})"
        )
    return overflow


def select_tail(
    messages: list[Message],
    config: CompactionConfig,
    context_size: int = 128_000,
) -> tuple[list[Message], list[Message]]:
    preserve_recent = config.preserve_recent_tokens
    if not preserve_recent:
        reserved = config.reserved or min(config.reserved_buffer, context_size // 4)
        usable = context_size - reserved
        preserve_recent = max(2_000, min(8_000, int(usable * 0.25)))

    system_msgs: list[Message] = []
    content_start = 0
    for m in messages:
        if isinstance(m, SystemMessage):
            system_msgs.append(m)
            content_start += 1
        else:
            break

    content_msgs = messages[content_start:]
    if not content_msgs:
        logger.debug("No content messages to split, returning full list")
        return [], messages

    tail_tokens = 0
    user_turns = 0
    split_at = len(content_msgs)

    tool_truncate = config.summary_tool_truncate

    for i in range(len(content_msgs) - 1, -1, -1):
        msg = content_msgs[i]
        if isinstance(msg, ToolMessage) and tool_truncate:
            tokens = min(estimate_tokens(msg.content), tool_truncate)
        else:
            tokens = estimate_message_tokens(msg)

        if isinstance(msg, UserMessage):
            user_turns += 1

        if user_turns >= config.tail_turns:
            if tail_tokens + tokens > preserve_recent:
                split_at = i + 1
                break

        tail_tokens += tokens

    if split_at == len(content_msgs):
        logger.debug("Tail covers all content messages, no split needed")
        return [], messages

    head_content = content_msgs[:split_at]
    tail_content = content_msgs[split_at:]
    head = system_msgs + head_content
    tail = tail_content
    logger.trace(f"select_tail: head={len(head)} messages, tail={len(tail)} messages")
    return head, tail


def _select_compaction_targets(
    messages: list[Message],
    config: CompactionConfig,
    context_size: int,
) -> tuple[list[Message], list[SystemMessage], list[Message]] | None:
    head, tail = select_tail(messages, config, context_size)
    if not head:
        logger.info("No messages to compact")
        return None

    if _summary_depth(head, config.max_summary_depth) >= config.max_summary_depth:
        logger.info(
            f"Summary depth {_summary_depth(head, config.max_summary_depth)} >= max {config.max_summary_depth}, skipping"
        )
        return None

    original_system: list[SystemMessage] = []
    head_to_summarize: list[Message] = []
    for m in head:
        if isinstance(m, SystemMessage) and not _is_summary_content(m.content):
            original_system.append(m)
        else:
            head_to_summarize.append(m)

    if not head_to_summarize:
        logger.info("Only system messages in head, nothing to compact")
        return None

    return head_to_summarize, original_system, tail


async def compact_with_chain(
    agent_state: AgentState,
    llm: LLM,
    config: CompactionConfig,
) -> tuple[list[SystemMessage], list[Message], list[Message]] | None:
    targets = _select_compaction_targets(
        agent_state.messages,
        config,
        agent_state.usage.context_size,
    )
    if targets is None:
        return None

    head_to_summarize, original_system, tail = targets
    logger.info(
        f"Chain-compacting {len(head_to_summarize)} messages into summary, "
        f"keeping {len(tail)} messages verbatim"
    )

    summary = await _summarize(
        llm, head_to_summarize, tool_truncate=config.summary_tool_truncate
    )
    if not summary:
        logger.warning("Chain compaction failed: no summary generated")
        return None

    logger.info(f"Chain compaction summary generated ({len(summary)} chars)")
    summary_text = f"{_SUMMARY_TAG_OPEN}\n{summary.strip()}\n{_SUMMARY_TAG_CLOSE}"

    compaction_prompt = UserMessage(
        content="What did we do in the earlier part of our conversation? Please summarize."
    )
    summary_response = AssistantMessage(content=summary_text, tool_calls=None)

    return (
        original_system,
        [compaction_prompt, summary_response],
        tail,
    )
