from typing import List, Optional, Literal, Union
from pydantic import BaseModel
from loguru import logger as _logger

from laffyhand.agent.models import (
    AssistantMessage, Message, ToolDefinition, StreamEvent, StreamText,
    StreamReasoning, StreamToolCall, StreamFinish, Usage,
)


# ─── OpenAI API-specific wire models ─────────────────────────────


class OpenAIToolCallFunction(BaseModel):
    name: str
    arguments: str


class OpenAIToolCall(BaseModel):
    id: str
    type: Literal['function'] = 'function'
    function: OpenAIToolCallFunction


class OpenAIToolCallDeltaFunction(BaseModel):
    name: Optional[str] = None
    arguments: Optional[str] = None


class OpenAIToolCallDelta(BaseModel):
    index: int
    id: Optional[str] = None
    type: Optional[Literal['function']] = None
    function: Optional[OpenAIToolCallDeltaFunction] = None


class OpenAIDelta(BaseModel):
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[OpenAIToolCallDelta]] = None


class OpenAIChoice(BaseModel):
    delta: OpenAIDelta
    finish_reason: Optional[str] = None
    index: int = 0


class OpenAIChatUsageDetails(BaseModel):
    cached_tokens: Optional[int] = None


class OpenAIChatCompletionDetails(BaseModel):
    reasoning_tokens: Optional[int] = None


class OpenAIChatUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    prompt_tokens_details: Optional[OpenAIChatUsageDetails] = None
    completion_tokens_details: Optional[OpenAIChatCompletionDetails] = None


class OpenAIChatChunk(BaseModel):
    id: Optional[str] = None
    object: Optional[str] = None
    created: Optional[int] = None
    model: Optional[str] = None
    system_fingerprint: Optional[str] = None
    choices: List[OpenAIChoice] = []
    usage: Optional[OpenAIChatUsage] = None


# ─── Internal → OpenAI conversion ────────────────────────────────


def message_to_openai(msg: Message) -> dict:
    if msg.role == "system":
        return {"role": "system", "content": msg.content}
    if msg.role == "user":
        return {"role": "user", "content": msg.content}
    if msg.role == "assistant":
        assert isinstance(msg, AssistantMessage)
        d: dict = {"role": "assistant"}
        if msg.content is not None:
            d["content"] = msg.content
        if msg.reasoning is not None:
            d["reasoning_content"] = msg.reasoning
        if msg.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.tool_call_id,
                    "type": "function",
                    "function": {"name": tc.tool_name, "arguments": tc.args},
                }
                for tc in msg.tool_calls
            ]
        return d
    if msg.role == "tool":
        return {"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content}
    _logger.warning(f"Unknown message role: {msg.role}")
    return {}


def tool_definitions_to_openai_tools(definitions: List[ToolDefinition]) -> List[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": d.name,
                "description": d.description.strip(),
                "parameters": d.input_schema,
            },
        }
        for d in definitions
    ]


# ─── OpenAI → Internal (streaming) ──────────────────────────────


class OpenAIStreamParser:
    """Accumulates tool call arguments across streaming chunks."""

    def __init__(self) -> None:
        self._tool_call_acc: dict[int, dict] = {}

    def feed(self, data: dict) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        choice = data.get("choices", [{}])[0] if data.get("choices") else {}
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")

        if delta.get("content"):
            events.append(StreamText(delta=delta["content"]))
        if delta.get("reasoning_content"):
            events.append(StreamReasoning(delta=delta["reasoning_content"]))
        if delta.get("tool_calls"):
            for tc in delta["tool_calls"]:
                idx = tc.get("index", 0)
                if "id" in tc:
                    self._tool_call_acc[idx] = {
                        "tool_call_id": tc["id"],
                        "tool_name": tc["function"]["name"],
                        "args": tc["function"].get("arguments", ""),
                    }
                elif idx in self._tool_call_acc:
                    self._tool_call_acc[idx]["args"] += tc.get("function", {}).get("arguments", "")

        if finish_reason:
            if finish_reason == "tool_calls" and self._tool_call_acc:
                for idx in sorted(self._tool_call_acc.keys()):
                    acc = self._tool_call_acc.pop(idx)
                    events.append(StreamToolCall(
                        tool_call_id=acc["tool_call_id"],
                        tool_name=acc["tool_name"],
                        args=acc["args"],
                    ))
            usage = None
            if data.get("usage"):
                u = data["usage"]
                ptd = u.get("prompt_tokens_details") or {}
                ctd = u.get("completion_tokens_details") or {}
                usage = Usage(
                    input_tokens=u.get("prompt_tokens"),
                    output_tokens=u.get("completion_tokens"),
                    reasoning_tokens=ctd.get("reasoning_tokens"),
                    cache_read_tokens=ptd.get("cached_tokens"),
                    cache_write_tokens=ptd.get("cache_write_tokens"),
                )
            events.append(StreamFinish(finish_reason=finish_reason, usage=usage))

        return events
