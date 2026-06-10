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


class FilePart(BaseModel):
    path: str
    content: str
    reference: str


class SystemMessage(BaseModel):
    role: Literal["system"] = "system"
    content: str


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str
    files: list[FilePart] = []
    agents: list[str] = []
    references: list[str] = []


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = None
    reasoning: Optional[str] = None
    tool_calls: Optional[List[ToolCallContent]] = None
    tokens: Optional[Usage] = None
    agent: str = ""
    model_info: dict[str, Any] = {}
    finish_reason: str = "stop"
    cost: int = 0


class ToolMessage(BaseModel):
    role: Literal["tool"] = "tool"
    tool_call_id: str
    content: str
    is_error: bool = False
    tool_name: Optional[str] = None
    args: Optional[str] = None


class CompactionMessage(BaseModel):
    role: Literal["compaction"] = "compaction"
    reason: str
    summary: str
    child_session_id: Optional[str] = None


class AgentSwitchedMessage(BaseModel):
    role: Literal["agent-switched"] = "agent-switched"
    agent: str


class ModelSwitchedMessage(BaseModel):
    role: Literal["model-switched"] = "model-switched"
    model: dict[str, Any]


Message = Union[
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
    CompactionMessage,
    AgentSwitchedMessage,
    ModelSwitchedMessage,
]


class ToolCallAccumulator(BaseModel):
    tool_call_id: str
    tool_name: str
    args: str
