from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel

from laffyhand.core.domain.messages import Usage


class ToolCall(BaseModel):
    type: Literal["tool-call"] = "tool-call"
    tool_call_id: str
    tool_name: str
    args: str


class StepStart(BaseModel):
    type: str = "step-start"
    index: int


class TextStart(BaseModel):
    type: str = "text-start"
    id: str


class TextDelta(BaseModel):
    type: str = "text-delta"
    id: str
    text: str


class TextEnd(BaseModel):
    type: str = "text-end"
    id: str


class ReasoningStart(BaseModel):
    type: str = "reasoning-start"
    id: str


class ReasoningDelta(BaseModel):
    type: str = "reasoning-delta"
    id: str
    text: str


class ReasoningEnd(BaseModel):
    type: str = "reasoning-end"
    id: str


class ToolResult(BaseModel):
    type: str = "tool-result"
    id: str
    name: str
    result: str


class ToolError(BaseModel):
    type: str = "tool-error"
    id: str
    name: str
    message: str
    error: bool = True


class StepFinish(BaseModel):
    type: str = "step-finish"
    index: int
    reason: str
    usage: Usage | None = None


class Finish(BaseModel):
    type: str = "finish"
    reason: str
    usage: Usage | None = None
    session_id: str | None = None
    session_usage: dict[str, Any] | None = None
    leftover_steer: str | None = None


class Compacting(BaseModel):
    type: str = "compacting"
    data: str


class PermissionRequest(BaseModel):
    type: str = "permission-request"
    request_id: str
    permission: str
    pattern: str


class SubAgentStart(BaseModel):
    type: str = "subagent-start"
    id: str
    parent_id: str | None = None
    agent_type: str
    description: str
    prompt: str = ""
    depth: int = 0


class SubAgentDelta(BaseModel):
    type: str = "subagent-delta"
    id: str
    kind: Literal["text", "reasoning", "tool", "tool_result", "error"]
    content: str | None = None
    tool_name: str | None = None
    tool_input: str | None = None


class SubAgentEnd(BaseModel):
    type: str = "subagent-end"
    id: str
    status: Literal["completed", "error", "cancelled"]
    summary: str | None = None
    tool_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class UsageUpdate(BaseModel):
    type: str = "usage-update"
    session_usage: dict[str, Any]


class TodoUpdate(BaseModel):
    type: str = "todo-update"


AgentEvent = Union[
    StepStart,
    TextStart,
    TextDelta,
    TextEnd,
    ReasoningStart,
    ReasoningDelta,
    ReasoningEnd,
    ToolCall,
    ToolResult,
    ToolError,
    StepFinish,
    Finish,
    Compacting,
    PermissionRequest,
    SubAgentStart,
    SubAgentDelta,
    SubAgentEnd,
    UsageUpdate,
    TodoUpdate,
]

__all__ = [
    "StepStart",
    "TextStart",
    "TextDelta",
    "TextEnd",
    "ReasoningStart",
    "ReasoningDelta",
    "ReasoningEnd",
    "ToolCall",
    "ToolResult",
    "ToolError",
    "StepFinish",
    "Finish",
    "Compacting",
    "PermissionRequest",
    "SubAgentStart",
    "SubAgentDelta",
    "SubAgentEnd",
    "UsageUpdate",
    "TodoUpdate",
    "AgentEvent",
]
