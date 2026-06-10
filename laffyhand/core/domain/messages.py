from __future__ import annotations

from typing import Any, List, Literal, NewType, Optional, Union

from pydantic import BaseModel

ModelID = NewType("ModelID", str)
ProviderID = NewType("ProviderID", str)


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCallContent(BaseModel):
    type: Literal["tool-call"] = "tool-call"
    tool_call_id: str
    tool_name: str
    args: str


class Usage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None


FinishReason = Literal[
    "stop", "length", "content_filter", "tool_calls", "error", "other"
]


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


class ToolCallAccumulator(BaseModel):
    tool_call_id: str
    tool_name: str
    args: str
