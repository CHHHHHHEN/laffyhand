from typing import Any, ClassVar, Union, Optional, Literal, cast, get_args
from pydantic import BaseModel, Field as F
from loguru import logger

from laffyhand.core.llm.specs.models import (
    AssistantMessage, 
    LLMRequest, 
    Frame,
    ProviderRequest, 
    Message,
    ToolCallAccumulator,
)
from laffyhand.core.llm.specs.models import (
    ToolDefinition,
    LLMEvent,
    StreamText,
    StreamReasoning,
    StreamToolCall,
    StreamFinish,
    Usage,
    FinishReason,
)
from laffyhand.core.llm.specs import Protocol, Endpoint
from laffyhand.core.llm.specs.models import ProviderID


# ─── Request wire models ─────────────────────────────────────────


class OpenAIRequestToolCallFunction(BaseModel):
    name: str
    arguments: str


class OpenAIRequestToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: OpenAIRequestToolCallFunction


class OpenAISystemMessage(BaseModel):
    role: Literal["system"] = "system"
    content: str


class OpenAIUserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str


class OpenAIAssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[list[OpenAIRequestToolCall]] = None


class OpenAIToolMessage(BaseModel):
    role: Literal["tool"] = "tool"
    tool_call_id: str
    content: str


class OpenAIToolFunction(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = F(default_factory=dict)


class OpenAIToolDefinition(BaseModel):
    type: Literal["function"] = "function"
    function: OpenAIToolFunction


OpenAIRequestMessage = Union[OpenAISystemMessage, OpenAIUserMessage, OpenAIAssistantMessage, OpenAIToolMessage]


class OpenAICompletionRequest(ProviderRequest):
    model: str
    messages: list[OpenAIRequestMessage]
    stream: Optional[bool] = None
    stream_options: Optional[dict[str, Any]] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    stop: Optional[str | list[str]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    logit_bias: Optional[dict[str, float]] = None
    user: Optional[str] = None
    seed: Optional[int] = None
    tools: Optional[list[OpenAIToolDefinition]] = None
    tool_choice: Optional[str | dict[str, Any]] = None
    response_format: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None
    store: Optional[bool] = None
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = None


# ─── Response wire models ────────────────────────────────────────
# Streaming


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


class OpenAIChatChunk(BaseModel):
    id: Optional[str] = None
    object: Optional[str] = None
    created: Optional[int] = None
    model: Optional[str] = None
    system_fingerprint: Optional[str] = None
    choices: list[OpenAIChoice] = F(default_factory=list)
    usage: Optional["OpenAIChatUsage"] = None



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

# ─── OpenAI Protocol ─────────────────────────────────────────────


class OpenAIProtocol(Protocol):
    provider_id: ClassVar[ProviderID] = ProviderID("openai")

    def __init__(self) -> None:
        self._tool_call_acc: dict[int, ToolCallAccumulator] = {}

    @staticmethod
    def _tool_definitions_to_openai(
        definitions: list[ToolDefinition],
    ) -> list[OpenAIToolDefinition]:
        return [
            OpenAIToolDefinition(
                function=OpenAIToolFunction(
                    name=d.name,
                    description=d.description.strip(),
                    parameters=d.input_schema,
                ),
            )
            for d in definitions
        ]

    @staticmethod
    def _message_to_openai(msg: Message) -> OpenAIRequestMessage:
        if msg.role == "system":
            return OpenAISystemMessage(content=msg.content)
        if msg.role == "user":
            return OpenAIUserMessage(content=msg.content)
        if msg.role == "assistant":
            assert isinstance(msg, AssistantMessage)
            content: str | None = msg.content
            if content is None and not msg.tool_calls:
                content = "[Empty response]"
            tool_calls: list[OpenAIRequestToolCall] | None = None
            if msg.tool_calls:
                tool_calls = [
                    OpenAIRequestToolCall(
                        id=tc.tool_call_id,
                        function=OpenAIRequestToolCallFunction(name=tc.tool_name, arguments=tc.args),
                    )
                    for tc in msg.tool_calls
                ]
            return OpenAIAssistantMessage(
                content=content,
                reasoning_content=msg.reasoning,
                tool_calls=tool_calls,
            )
        if msg.role == "tool":
            return OpenAIToolMessage(
                tool_call_id=msg.tool_call_id,
                content=msg.content,
            )
        logger.warning(f"Unknown message role: {msg.role}")
        return OpenAIUserMessage(content="")

    def build_request(self, request: LLMRequest) -> OpenAICompletionRequest:
        self._tool_call_acc.clear()
        messages = [self._message_to_openai(m) for m in request.messages]
        logger.debug(
            f"OpenAI request: model={request.model}, {len(messages)} messages, tools={bool(request.tools)}"
        )
        return OpenAICompletionRequest(
            model=request.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            tools=self._tool_definitions_to_openai(request.tools) if request.tools else None,
        )

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

    def parse_frame(self, frame: Frame | dict[str, Any]) -> list[LLMEvent]:
        if isinstance(frame, dict):
            frame = Frame(data=frame)
        chunk = OpenAIChatChunk.model_validate(frame.data)
        events: list[LLMEvent] = []

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
                    self._tool_call_acc[idx] = ToolCallAccumulator(
                        tool_call_id=tc.id,
                        tool_name=(tc.function.name if tc.function else "") or "",
                        args=(tc.function.arguments if tc.function else "") or "",
                    )
                elif idx in self._tool_call_acc and tc.function:
                    self._tool_call_acc[idx].args += tc.function.arguments or ""

        if finish_reason:
            if finish_reason == "tool_calls" and self._tool_call_acc:
                for idx in sorted(self._tool_call_acc):
                    acc = self._tool_call_acc.pop(idx)
                    events.append(
                        StreamToolCall(
                            tool_call_id=acc.tool_call_id,
                            tool_name=acc.tool_name,
                            args=acc.args,
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

    def build(self) -> str:
        return f"{self.base_url}/v1/chat/completions"
