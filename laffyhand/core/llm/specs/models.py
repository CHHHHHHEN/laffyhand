from pydantic import BaseModel, Field
from typing import NewType, Any, Dict, List, Literal, Union, Optional

ModelID = NewType("ModelID", str)
ProviderID = NewType("ProviderID", str)

# ─── Frame / Header / Provider Request ──────────────────────────


class Frame(BaseModel):
    data: Dict[str, Any]


class Header(BaseModel):
    key: str = Field(description="Header key name")
    value: str = Field(description="Header value")


class ProviderRequest(BaseModel):
    pass


# ─── Tool Definition (provider-agnostic) ────────────────────────


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCallContent(BaseModel):
    type: Literal["tool-call"] = "tool-call"
    tool_call_id: str
    tool_name: str
    args: str


# ─── Usage ──────────────────────────────────────────────────────


class Usage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None


# ─── Stream Events ──────────────────────────────────────────────


class StreamText(BaseModel):
    type: Literal["text"] = "text"
    delta: str


class StreamReasoning(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    delta: str


class StreamToolCall(BaseModel):
    type: Literal["tool-call"] = "tool-call"
    tool_call_id: str
    tool_name: str
    args: str


FinishReason = Literal[
    "stop", "length", "content_filter", "tool_calls", "error", "other"
]


class StreamFinish(BaseModel):
    type: Literal["finish"] = "finish"
    finish_reason: FinishReason
    usage: Optional[Usage] = None


class StreamError(BaseModel):
    type: Literal["error"] = "error"
    error: str


LLMEvent = Union[StreamText, StreamReasoning, StreamToolCall, StreamFinish, StreamError]


# ─── Messages ───────────────────────────────────────────────────


class SystemMessage(BaseModel):
    role: Literal["system"] = "system"
    content: str


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = None
    reasoning: Optional[str] = None
    tool_calls: Optional[List[ToolCallContent]] = None
    tokens: Optional[Usage] = None


class ToolMessage(BaseModel):
    role: Literal["tool"] = "tool"
    tool_call_id: str
    content: str
    is_error: bool = False
    tool_name: str | None = None
    args: str | None = None


Message = Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]


class LLMRequest(BaseModel):
    model: ModelID
    provider: ProviderID
    messages: list[Message]
    tools: Optional[list[ToolDefinition]] = None


class ToolCallAccumulator(BaseModel):
    tool_call_id: str
    tool_name: str
    args: str
