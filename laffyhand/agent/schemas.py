from __future__ import annotations

from loguru import logger
from pydantic import BaseModel, Field
from typing import Any, Optional, List, Literal, Union, NewType

from laffyhand.agent.llm.specs.models import Message, Usage


SessionID = NewType("SessionID", str)


class CompactionConfig(BaseModel):
    tail_turns: int = Field(default=2, description="保留的最近对话轮次数")
    preserve_recent_tokens: int = Field(default=0, description="保留轮次的 Token 预算上限，0 表示自动")
    reserved: int = Field(default=0, description="为 LLM 输出预留的 Token 缓冲，0 表示自动")
    prune: bool = Field(default=True, description="工具调用后是否修剪历史工具输出")
    auto_continue: bool = Field(default=True, description="压缩后是否自动注入继续提示")
    summary_tool_truncate: int = Field(default=2000, description="摘要中单条工具输出截断长度（Token）")


class SessionUsage(BaseModel):
    curr_context_usage: int = Field(default=0, description="当前单次请求已使用Token数量")
    total_input: int = Field(default=0, description="整个会话累积的输入 Token 数")
    total_output: int = Field(default=0, description="整个会话累积的输出 Token 数")
    total_reasoning: int = Field(default=0, description="整个会话累积的推理 Token 数")
    total_cache_read: int = Field(default=0, description="整个会话累积的缓存命中 Token 数")
    total_cache_write: int = Field(default=0, description="整个会话累积的缓存写入 Token 数")
    context_size: int = Field(default=0, description="模型上下文窗口大小（Token）")

    def add(self, usage: Usage) -> None:
        self.curr_context_usage = usage.input_tokens or 0

        self.total_input += usage.input_tokens or 0
        self.total_output += usage.output_tokens or 0
        self.total_reasoning += usage.reasoning_tokens or 0
        self.total_cache_read += usage.cache_read_tokens or 0
        self.total_cache_write += usage.cache_write_tokens or 0
        logger.debug(
            f"Usage added: +{usage.input_tokens or 0} in, +{usage.output_tokens or 0} out"
        )

class AgentState(BaseModel):
    messages: List[Message] = Field(description="当前会话的消息列表")
    turn_count: int = Field(default=0, description="已完成的对话轮次数")
    step: int = Field(default=0, description="当前轮次内的步骤计数")
    usage: SessionUsage = Field(default_factory=SessionUsage, description="整个会话的Token用量统计")
    session_id: SessionID = Field(description="当前会话 ID")
    interrupt_requested: bool = Field(default=False, description="用户请求中断标志")
    pending_steer: Optional[str] = Field(default=None, description="待注入的用户引导文本")
    
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
]
