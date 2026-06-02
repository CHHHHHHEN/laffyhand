from __future__ import annotations

from loguru import logger
from pydantic import BaseModel
from typing import Any, Optional, List, Literal, Union

from laffyhand.agent.llm.specs.models import Message, Usage


CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(0, round(len(text) / CHARS_PER_TOKEN))


class CompactionConfig(BaseModel):
    tail_turns: int = 2
    preserve_recent_tokens: Optional[int] = None
    reserved: Optional[int] = None
    prune: bool = True
    auto_continue: bool = True
    summary_tool_truncate: int = 500


class SessionUsage(BaseModel):
    total_input: int = 0
    total_output: int = 0
    total_reasoning: int = 0
    total_cache_read: int = 0
    context_size: int = 0

    def add(self, usage: Usage) -> None:
        self.total_input += usage.input_tokens or 0
        self.total_output += usage.output_tokens or 0
        self.total_reasoning += usage.reasoning_tokens or 0
        self.total_cache_read += usage.cache_read_tokens or 0
        logger.debug(
            f"Usage added: +{usage.input_tokens or 0} in, +{usage.output_tokens or 0} out"
        )


# ─── Agent-level stream events ──────────────────────────────────


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


class ToolCall(BaseModel):
    type: str = "tool-call"
    id: str
    name: str
    input: str


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


class ProviderError(BaseModel):
    type: str = "provider-error"
    message: str
    retryable: bool = False


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
    mode: Literal["foreground", "background"]
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


StreamEvent = Union[
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
    ProviderError,
    Compacting,
    PermissionRequest,
    SubAgentStart,
    SubAgentDelta,
    SubAgentEnd,
]


class AgentState(BaseModel):
    messages: List[Message]
    turn_count: int = 0
    step: int = 0
    usage: SessionUsage = SessionUsage()
    session_id: Optional[str] = None
    interrupt_requested: bool = False
    pending_steer: Optional[str] = None
