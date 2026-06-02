from collections.abc import Sequence

from loguru import logger

from laffyhand.agent.llm.specs.models import AssistantMessage, Message, SystemMessage, ToolMessage, UserMessage
from laffyhand.agent.llm.specs.models import (
    StreamError,
    StreamFinish,
    StreamText,
)
from laffyhand.agent.schemas import (
    AgentState,
    CompactionConfig,
    estimate_tokens,
)
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.truncation import truncate_output


def estimate_message_tokens(msg: Message) -> int:
    total = 0
    if isinstance(msg, (SystemMessage, UserMessage)):
        total += estimate_tokens(msg.content)
    elif isinstance(msg, AssistantMessage):
        if msg.content:
            total += estimate_tokens(msg.content)
        if msg.reasoning:
            total += estimate_tokens(msg.reasoning)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                total += estimate_tokens(tc.tool_name + tc.args)
    elif isinstance(msg, ToolMessage):
        total += estimate_tokens(msg.content)
    return total


def estimate_messages_tokens(messages: list[Message]) -> int:
    return sum(estimate_message_tokens(m) for m in messages)


def is_overflow(tokens: int, context_size: int, reserved: int = 20_000) -> bool:
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
    if preserve_recent is None:
        reserved = config.reserved or min(20_000, context_size // 4)
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
        if (
            isinstance(msg, ToolMessage)
            and tool_truncate
            and len(msg.content) > tool_truncate
        ):
            tokens = estimate_tokens(msg.content[:tool_truncate])
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


SUMMARY_SYSTEM_PROMPT = """You are a summarization assistant. Your task is to summarize conversation history concisely while preserving critical information.

Focus on:
- Goal: What is the user trying to achieve?
- Progress: What has been done so far?
- Key Decisions: Important choices made.
- Relevant Files: Files created, read, or modified.
- Next Steps: What remains to be done.

Keep the summary concise but thorough enough that the conversation can continue naturally."""


SUMMARY_PROMPT_TEMPLATE = """Please summarize the following conversation history:

{head_text}

---

Provide a concise structured summary covering:
- Goal: What is the user trying to achieve?
- Progress: What has been done so far?
- Key Decisions: Important choices made.
- Relevant Files: Files created, read, or modified.
- Next Steps: What remains to be done."""


_SUMMARY_TAG_OPEN = "<summary>"
_SUMMARY_TAG_CLOSE = "</summary>"


def _is_summary_content(content: str) -> bool:
    s = content.strip()
    return s.startswith(_SUMMARY_TAG_OPEN) and s.endswith(_SUMMARY_TAG_CLOSE)


_MAX_SUMMARY_DEPTH = 3


def _summary_depth(messages: list[Message]) -> int:
    depth = 0
    for m in messages:
        content = ""
        if isinstance(m, SystemMessage):
            content = m.content or ""
        elif isinstance(m, UserMessage):
            content = m.content or ""
        if _is_summary_content(content):
            depth += 1
    return depth


def build_summary_text(messages: Sequence[Message], tool_truncate: int = 500) -> str:
    lines = []
    for msg in messages:
        if isinstance(msg, SystemMessage) and _is_summary_content(msg.content):
            inner = (
                msg.content.strip()
                .removeprefix(_SUMMARY_TAG_OPEN)
                .removesuffix(_SUMMARY_TAG_CLOSE)
                .strip()
            )
            lines.append(f"[Previous Summary]:\n{inner}")
        elif isinstance(msg, UserMessage) and _is_summary_content(msg.content):
            inner = (
                msg.content.strip()
                .removeprefix(_SUMMARY_TAG_OPEN)
                .removesuffix(_SUMMARY_TAG_CLOSE)
                .strip()
            )
            lines.append(f"[Previous Summary]:\n{inner}")
        elif isinstance(msg, SystemMessage):
            lines.append(f"[System]: {msg.content}")
        elif isinstance(msg, UserMessage):
            lines.append(f"[User]: {msg.content}")
        elif isinstance(msg, AssistantMessage):
            if msg.content:
                lines.append(f"[Assistant]: {msg.content}")
            if msg.reasoning:
                lines.append(f"[Reasoning]: {msg.reasoning}")
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    lines.append(f"[Tool Call: {tc.tool_name}]: {tc.args}")
        elif isinstance(msg, ToolMessage):
            lines.append(
                f"[Tool Result - {msg.tool_call_id}]: {truncate_output(msg.content, tool_truncate)}"
            )
    return "\n".join(lines)


async def _summarize(
    llm: LLM, head: Sequence[Message], tool_truncate: int = 500
) -> str | None:
    head_text = build_summary_text(head, tool_truncate=tool_truncate)
    summary_prompt = SUMMARY_PROMPT_TEMPLATE.format(head_text=head_text)

    summary_messages: list[Message] = [
        SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
        UserMessage(content=summary_prompt),
    ]

    text_parts: list[str] = []
    async for event in llm.stream(summary_messages):
        if isinstance(event, StreamText):
            text_parts.append(event.delta)
        elif isinstance(event, StreamFinish):
            break
        elif isinstance(event, StreamError):
            logger.error(f"Summarization stream error: {event.error}")
            return None

    return "".join(text_parts) if text_parts else None


def _select_compaction_targets(
    messages: list[Message],
    config: CompactionConfig,
    context_size: int,
) -> tuple[list[Message], list[SystemMessage], list[Message]] | None:
    head, tail = select_tail(messages, config, context_size)
    if not head:
        logger.info("No messages to compact")
        return None

    if _summary_depth(head) >= _MAX_SUMMARY_DEPTH:
        logger.info(
            f"Summary depth {_summary_depth(head)} >= max {_MAX_SUMMARY_DEPTH}, skipping"
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


async def compact(agent_state: AgentState, llm: LLM, config: CompactionConfig) -> bool:
    targets = _select_compaction_targets(
        agent_state.messages,
        config,
        agent_state.usage.context_size,
    )
    if targets is None:
        return False

    head_to_summarize, original_system, tail = targets
    logger.info(
        f"Compacting {len(head_to_summarize)} messages into summary, keeping {len(tail)} messages verbatim"
    )

    summary = await _summarize(
        llm, head_to_summarize, tool_truncate=config.summary_tool_truncate
    )
    if not summary:
        logger.warning("Compaction failed: no summary generated")
        return False

    summary_msg = SystemMessage(content=f"{_SUMMARY_TAG_OPEN}\n{summary.strip()}\n{_SUMMARY_TAG_CLOSE}")
    agent_state.messages = original_system + [summary_msg] + tail
    logger.info(
        f"Compaction complete: {len(head_to_summarize)} messages -> 1 summary message"
    )
    return True


async def compact_with_chain(
    agent_state: AgentState,
    llm: LLM,
    config: CompactionConfig,
) -> tuple[str, list[SystemMessage], list[Message]] | None:
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
    return f"{_SUMMARY_TAG_OPEN}\n{summary.strip()}\n{_SUMMARY_TAG_CLOSE}", original_system, tail
