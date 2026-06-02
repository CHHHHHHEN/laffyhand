from typing import Any, Optional, Literal, cast, get_args
from pydantic import BaseModel, Field as F
from loguru import logger

from laffyhand.agent.schemas import (
    LLMRequest,
    Message,
    AssistantMessage,
    ToolDefinition,
    StreamEvent,
    StreamText,
    StreamReasoning,
    StreamToolCall,
    StreamFinish,
    Usage,
    FinishReason,
)
from laffyhand.agent.llm.specs import Protocol, Endpoint


# ─── OpenAI raw wire models ─────────────────────────────────────


class OpenAIToolCallDeltaFunction(BaseModel):
    name: Optional[str] = None
    arguments: Optional[str] = None


class OpenAIToolCallDelta(BaseModel):
    index: int
    id: Optional[str] = None
    type: Optional[Literal["function"]] = None
    function: Optional[OpenAIToolCallDeltaFunction] = None


class OpenAIDelta(BaseModel):
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[list[OpenAIToolCallDelta]] = None


class OpenAIChoice(BaseModel):
    delta: OpenAIDelta
    finish_reason: Optional[str] = None
    index: int = 0


class OpenAIChatUsageDetails(BaseModel):
    cached_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None


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
    choices: list[OpenAIChoice] = F(default_factory=list)
    usage: Optional[OpenAIChatUsage] = None


# ─── Internal → OpenAI conversion ────────────────────────────────


def _message_to_openai(msg: Message) -> dict[str, Any]:
    if msg.role == "system":
        return {"role": "system", "content": msg.content}
    if msg.role == "user":
        return {"role": "user", "content": msg.content}
    if msg.role == "assistant":
        assert isinstance(msg, AssistantMessage)
        d: dict[str, Any] = {"role": "assistant"}
        if msg.content is not None:
            d["content"] = msg.content
        elif not msg.tool_calls:
            # API requires at least content or tool_calls; provide a fallback.
            d["content"] = "[Empty response]"
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
        return {
            "role": "tool",
            "tool_call_id": msg.tool_call_id,
            "content": msg.content,
        }
    logger.warning(f"Unknown message role: {msg.role}")
    return {}


def _tool_definitions_to_openai(
    definitions: list[ToolDefinition],
) -> list[dict[str, Any]]:
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


# ─── OpenAI Protocol ─────────────────────────────────────────────


class OpenAIProtocol(Protocol):
    def __init__(self) -> None:
        self._tool_call_acc: dict[int, dict[str, Any]] = {}

    def build_request(self, request: LLMRequest) -> dict[str, Any]:
        self._tool_call_acc.clear()
        messages = [_message_to_openai(m) for m in request.messages]
        body: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            body["tools"] = _tool_definitions_to_openai(request.tools)
        logger.debug(
            f"OpenAI request: model={request.model}, {len(messages)} messages, tools={bool(request.tools)}"
        )
        return body

    @staticmethod
    def _openai_usage_to_internal(u: OpenAIChatUsage) -> Usage:
        ptd = u.prompt_tokens_details
        ctd = u.completion_tokens_details
        return Usage(
            input_tokens=u.prompt_tokens,
            output_tokens=u.completion_tokens,
            reasoning_tokens=ctd.reasoning_tokens if ctd else None,
            cache_read_tokens=ptd.cached_tokens if ptd else None,
            cache_write_tokens=ptd.cache_write_tokens if ptd else None,
        )

    def parse_frame(self, frame: dict[str, Any]) -> list[StreamEvent]:
        chunk = OpenAIChatChunk.model_validate(frame)
        events: list[StreamEvent] = []

        if not chunk.choices:
            return events

        choice = chunk.choices[0]
        delta = choice.delta
        finish_reason = choice.finish_reason

        if delta.content:
            events.append(StreamText(delta=delta.content))
        if delta.reasoning_content:
            logger.trace(f"Reasoning delta: {len(delta.reasoning_content)} chars")
            events.append(StreamReasoning(delta=delta.reasoning_content))
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if tc.id is not None:
                    logger.trace(
                        f"Tool call start: idx={idx}, id={tc.id}, name={tc.function.name if tc.function else '?'}"
                    )
                    self._tool_call_acc[idx] = {
                        "tool_call_id": tc.id,
                        "tool_name": tc.function.name if tc.function else "",
                        "args": tc.function.arguments if tc.function else "",
                    }
                elif idx in self._tool_call_acc and tc.function:
                    self._tool_call_acc[idx]["args"] += tc.function.arguments or ""

        if finish_reason:
            if finish_reason == "tool_calls" and self._tool_call_acc:
                for idx in sorted(self._tool_call_acc):
                    acc = self._tool_call_acc.pop(idx)
                    events.append(
                        StreamToolCall(
                            tool_call_id=acc["tool_call_id"],
                            tool_name=acc["tool_name"],
                            args=acc["args"],
                        )
                    )
            usage = self._openai_usage_to_internal(chunk.usage) if chunk.usage else None
            if finish_reason not in get_args(FinishReason):
                logger.warning(
                    f"Unknown finish_reason '{finish_reason}', mapping to 'other'"
                )
                finish_reason = "other"
            logger.debug(f"Finish reason: {finish_reason}, usage={usage}")
            events.append(
                StreamFinish(
                    finish_reason=cast(FinishReason, finish_reason), usage=usage
                )
            )

        return events


# ─── OpenAI Endpoint ─────────────────────────────────────────────


class OpenAIEndpoint(Endpoint):
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def build(self, model: str) -> str:
        return f"{self.base_url}/v1/chat/completions"
