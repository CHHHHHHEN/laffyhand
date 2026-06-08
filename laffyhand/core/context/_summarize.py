from __future__ import annotations

from collections.abc import Sequence


from laffyhand.core.llm.specs.models import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from laffyhand.core._utils import truncate_output
from laffyhand.core.llm.facade import LLM, stream_text
from laffyhand.core.agent import get_builtin

_SUMMARY_TAG_OPEN = "<summary>"
_SUMMARY_TAG_CLOSE = "</summary>"

SUMMARY_PROMPT_TEMPLATE = """Please summarize the following conversation history:

{head_text}

---

Provide a concise structured summary covering:
- Goal: What is the user trying to achieve?
- Progress: What has been done so far?
- Key Decisions: Important choices made.
- Relevant Files: Files created, read, or modified.
- Next Steps: What remains to be done."""


def _is_summary_content(content: str) -> bool:
    s = content.strip()
    return s.startswith(_SUMMARY_TAG_OPEN) and s.endswith(_SUMMARY_TAG_CLOSE)


def _summary_depth(messages: list[Message], max_depth: int = 3) -> int:
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

    info = get_builtin("compaction")
    system_prompt = info.system_prompt if info else ""
    summary_messages: list[Message] = [
        SystemMessage(content=system_prompt),
        UserMessage(content=summary_prompt),
    ]

    return await stream_text(llm, summary_messages)
