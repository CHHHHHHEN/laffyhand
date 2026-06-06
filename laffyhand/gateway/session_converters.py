from __future__ import annotations

import itertools
import time
from typing import Any

from laffyhand.core.llm.specs.models import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)


_MESSAGE_COUNTER = itertools.count(1)


def _next_msg_id() -> str:
    return f"msg-{int(time.time() * 1000)}-{next(_MESSAGE_COUNTER)}"


def _serialize_messages(messages: list[Message]) -> list[dict[str, Any]]:
    tool_results: dict[str, tuple[str, bool]] = {}
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_results[msg.tool_call_id] = (msg.content, msg.is_error)

    result: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append(
                {
                    "id": _next_msg_id(),
                    "role": "system",
                    "content": msg.content,
                    "createdAt": int(time.time() * 1000),
                }
            )
        elif isinstance(msg, UserMessage):
            result.append(
                {
                    "id": _next_msg_id(),
                    "role": "user",
                    "content": msg.content,
                    "createdAt": int(time.time() * 1000),
                }
            )
        elif isinstance(msg, AssistantMessage):
            entry: dict[str, Any] = {
                "id": _next_msg_id(),
                "role": "assistant",
                "content": msg.content or "",
                "createdAt": int(time.time() * 1000),
            }
            if msg.reasoning:
                entry["reasoning"] = msg.reasoning
            if msg.tool_calls:
                entry["toolCalls"] = []
                for tc in msg.tool_calls:
                    result_content, is_error = tool_results.get(
                        tc.tool_call_id, (None, False)
                    )
                    tool_entry: dict[str, Any] = {
                        "id": tc.tool_call_id,
                        "name": tc.tool_name,
                        "arguments": tc.args,
                    }
                    if result_content is not None:
                        tool_entry["status"] = "error" if is_error else "completed"
                        tool_entry["result"] = result_content
                        tool_entry["isError"] = is_error
                    else:
                        tool_entry["status"] = "pending"
                    entry["toolCalls"].append(tool_entry)
            if msg.tokens:
                usage = {
                    "inputTokens": msg.tokens.input_tokens,
                    "outputTokens": msg.tokens.output_tokens,
                }
                if msg.tokens.reasoning_tokens is not None:
                    usage["reasoningTokens"] = msg.tokens.reasoning_tokens
                entry["usage"] = usage
            result.append(entry)
        elif isinstance(msg, ToolMessage):
            pass
    return result
