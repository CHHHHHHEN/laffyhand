from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field

from laffyhand.core.domain.messages import (
    FinishReason,
    Message,
    ModelID,
    ProviderID,
    ToolDefinition,
    Usage,
)

# ─── Frame / Header / Provider Request ──────────────────────────


class Frame(BaseModel):
    data: Dict[str, Any]


class Header(BaseModel):
    key: str = Field(description="Header key name")
    value: str = Field(description="Header value")


class ProviderRequest(BaseModel):
    pass


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


class StreamFinish(BaseModel):
    type: Literal["finish"] = "finish"
    finish_reason: FinishReason
    usage: Optional[Usage] = None


class StreamError(BaseModel):
    type: Literal["error"] = "error"
    error: str


LLMEvent = Union[StreamText, StreamReasoning, StreamToolCall, StreamFinish, StreamError]


class LLMRequest(BaseModel):
    model: ModelID
    provider: ProviderID
    messages: list[Message]
    tools: Optional[list[ToolDefinition]] = None
