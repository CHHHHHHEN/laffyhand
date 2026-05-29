from collections.abc import Sequence

from loguru import logger

from laffyhand.agent.schemas import (
    AgentState, AssistantMessage, CompactionConfig, Message,
    StreamError, StreamFinish, StreamText, SystemMessage, ToolMessage,
    UserMessage, estimate_tokens,
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
        logger.debug(f"Overflow: {tokens} tokens vs usable {usable} (context_size={context_size})")
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

    for i in range(len(content_msgs) - 1, -1, -1):
        msg = content_msgs[i]
        tokens = estimate_message_tokens(msg)

        if isinstance(msg, UserMessage):
            user_turns += 1

        if user_turns >= config.tail_turns:
            # Check if adding this message would exceed the preserve budget.
            # tail_tokens reflects cumulative tokens of messages already
            # assigned to tail (more recent than current message i).
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
    logger.debug(f"select_tail: head={len(head)} messages, tail={len(tail)} messages")
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


def build_summary_text(messages: Sequence[Message], tool_truncate: int = 500) -> str:
    lines = []
    for msg in messages:
        if isinstance(msg, UserMessage):
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
            lines.append(f"[Tool Result - {msg.tool_call_id}]: {truncate_output(msg.content, tool_truncate)}")
    return "\n".join(lines)


def wrap_last_user(messages: list[Message]) -> list[Message]:
    result = list(messages)
    for i in range(len(result) - 1, -1, -1):
        msg = result[i]
        if isinstance(msg, UserMessage):
            content = msg.content
            if content.startswith("<system-reminder>") and content.rstrip().endswith("</system-reminder>"):
                logger.debug("User message already wrapped, skipping")
                return result
            result[i] = UserMessage(content=f"<system-reminder>\n{content}\n</system-reminder>")
            logger.debug("Last user message wrapped with system-reminder tags")
            return result
    logger.warning("No UserMessage found to wrap")
    return result


def attach_reminder(messages: list[Message], reminder: str) -> list[Message]:
    for i, msg in enumerate(messages):
        if isinstance(msg, SystemMessage):
            if reminder not in msg.content:
                result = list(messages)
                result[i] = SystemMessage(content=msg.content + f"\n\n{reminder}")
                logger.debug("Reminder attached to system message")
                return result
            logger.debug("Reminder already present, not re-attaching")
            return list(messages)
    logger.warning("No SystemMessage found, cannot attach reminder")
    return list(messages)


PRUNE_PROTECT = 40_000
PRUNE_MINIMUM = 20_000
_PRUNE_MIN_SAVINGS = 50


def prune(messages: list[Message]) -> list[Message]:
    tool_indices: list[int] = []
    total_tokens = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, ToolMessage):
            total_tokens += estimate_tokens(msg.content)
            tool_indices.append(i)
    logger.debug(f"Prune: found {len(tool_indices)} ToolMessages, total_tokens={total_tokens}")
    if total_tokens <= PRUNE_PROTECT:
        logger.debug(f"Total tokens {total_tokens} <= PRUNE_PROTECT {PRUNE_PROTECT}, skipping")
        return messages
    target = max(PRUNE_MINIMUM, total_tokens // 2)
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
        new_content = f"[Tool output pruned: {old_t} tokens]"
        result[idx] = ToolMessage(
            tool_call_id=msg.tool_call_id,
            content=new_content,
        )
        pruned += old_t - estimate_tokens(new_content)
    logger.info(f"Pruned {pruned} tokens from tool outputs")
    return result



def _summarize(llm: LLM, head: Sequence[Message], tool_truncate: int = 500) -> str | None:
    head_text = build_summary_text(head, tool_truncate=tool_truncate)
    summary_prompt = SUMMARY_PROMPT_TEMPLATE.format(head_text=head_text)

    summary_messages: list[Message] = [
        SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
        UserMessage(content=summary_prompt),
    ]

    text_parts: list[str] = []
    for event in llm.stream(summary_messages):
        if isinstance(event, StreamText):
            text_parts.append(event.delta)
        elif isinstance(event, StreamFinish):
            break
        elif isinstance(event, StreamError):
            logger.error(f"Summarization stream error: {event.error}")
            return None

    return "".join(text_parts) if text_parts else None


def compact(agent_state: AgentState, llm: LLM, config: CompactionConfig) -> bool:
    head, tail = select_tail(
        agent_state.messages, config, agent_state.usage.context_size,
    )
    if not head:
        logger.info("No messages to compact")
        return False

    original_system = [m for m in head if isinstance(m, SystemMessage)]
    head_to_summarize = [m for m in head if not isinstance(m, SystemMessage)]

    if not head_to_summarize:
        logger.info("Only system messages in head, nothing to compact")
        return False

    logger.info(f"Compacting {len(head_to_summarize)} messages into summary, keeping {len(tail)} messages verbatim")

    summary = _summarize(llm, head_to_summarize, tool_truncate=config.summary_tool_truncate)
    if not summary:
        logger.warning("Compaction failed: no summary generated")
        return False

    summary_msg = UserMessage(content=summary.strip())
    agent_state.messages = original_system + [summary_msg] + tail
    logger.info(f"Compaction complete: {len(head_to_summarize)} messages -> 1 summary message")
    return True
