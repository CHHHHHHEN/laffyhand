from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Sequence, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from laffyhand.agent.llm.specs.models import ModelID, ProviderID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_id() -> str:
    now = _utcnow()
    return now.strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]


ModelVariant = Literal["none", "low", "medium", "high", "xhigh"]


class Model(BaseModel):
    id: ModelID = Field(description="模型ID")
    provider: ProviderID = Field(description="LLM提供商ID")
    variant: Optional[ModelVariant] = None


# ── Message types ───────────────────────────────────────────────


class TextPart(BaseModel):
    text: str = Field(description="文本内容")


class FilePart(BaseModel):
    path: str = Field(description="文件路径")
    content: str = Field(description="文件内容")
    reference: str = Field(description="用户的引用方式，如 @path")


class UserData(BaseModel):
    text: str = Field(description="用户消息文本")
    files: List[FilePart] = Field(default_factory=list, description="通过 @ 指定文件的对应内容")
    agents: List[str] = Field(default_factory=list, description="通过 @ 指定的 Agent")
    references: List[str] = Field(default_factory=list, description="通过 @ 指定的文件路径")


class MessageTime(BaseModel):
    created: int = Field(description="创建时间（Unix 时间戳）")
    completed: Optional[int] = Field(default=None, description="完成时间（Unix 时间戳）")


class TokenCache(BaseModel):
    read: int = Field(description="缓存读取 tokens")
    write: int = Field(description="缓存写入 tokens")


class TokenDetail(BaseModel):
    input: int = Field(description="输入 tokens")
    output: int = Field(description="输出 tokens")
    reasoning: int = Field(description="推理 tokens")
    cache: TokenCache = Field(description="缓存用量")


class MessageSnapshot(BaseModel):
    start: Optional[str] = Field(default=None, description="起始快照")
    end: Optional[str] = Field(default=None, description="结束快照")


# ── Assistant Content ───────────────────────────────────────────


class AssistantTextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str = Field(description="文本内容")


class AssistantReasoningPart(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    id: str = Field(description="推理步骤 ID")
    text: str = Field(description="推理内容")


class ToolStatePending(BaseModel):
    status: Literal["pending"] = "pending"
    input: str = Field(description="工具输入文本")


class ToolStateRunning(BaseModel):
    status: Literal["running"] = "running"
    input: dict[str, Any] = Field(description="结构化输入")
    structured: Any = Field(description="结构化工具输出")
    content: list = Field(default_factory=list, description="工具输出内容")


class ToolStateCompleted(BaseModel):
    status: Literal["completed"] = "completed"
    input: dict[str, Any] = Field(description="结构化输入")
    structured: Any = Field(description="结构化工具输出")
    content: list = Field(default_factory=list, description="工具输出内容")
    attachments: Optional[list] = Field(default=None, description="附件列表")


class ToolStateError(BaseModel):
    status: Literal["error"] = "error"
    input: dict[str, Any] = Field(description="结构化输入")
    structured: Any = Field(description="结构化工具输出")
    content: list = Field(default_factory=list, description="工具输出内容")
    error: str = Field(description="错误信息")


ToolState = Union[ToolStatePending, ToolStateRunning, ToolStateCompleted, ToolStateError]


class AssistantToolPart(BaseModel):
    type: Literal["tool"] = "tool"
    id: str = Field(description="工具调用 ID")
    name: str = Field(description="工具名称")
    provider: Optional[dict[str, Any]] = Field(default=None, description="提供者信息")
    state: ToolState = Field(description="工具状态")
    time: MessageTime = Field(description="时间信息")


AssistantContent = Union[AssistantTextPart, AssistantReasoningPart, AssistantToolPart]


# ── Message data payloads ───────────────────────────────────────


class AssistantData(BaseModel):
    agent: str = Field(description="agent 名称")
    model: Model = Field(description="回复模型")
    content: Sequence[AssistantContent] = Field(default_factory=list, description="按时间顺序排列的消息内容数组")
    snapshot: MessageSnapshot = Field(description="快照信息")
    finish: str = Field(default="stop", description="结束原因")
    cost: int = Field(description="消耗（微美分）")
    tokens: Optional[TokenDetail] = Field(default=None, description="Token 用量")
    error: Optional[str] = Field(default=None, description="错误信息")


class SyntheticData(BaseModel):
    """由系统插入的消息，如上下文压缩后插入的总结文本"""
    sessionID: str = Field(description="源会话 ID")
    text: str = Field(description="合成消息文本")


class ShellData(BaseModel):
    callID: str = Field(description="调用 ID")
    command: str = Field(description="执行的命令")
    output: str = Field(description="命令输出")
    truncated: bool = Field(default=False, description="输出是否因过长而被截断")
    is_error: bool = Field(default=False, description="是否错误结果")
    time: MessageTime = Field(description="开始时间与结束时间")


class AgentSwitchedData(BaseModel):
    agent: str = Field(description="切换到的 agent")


class ModelSwitchedData(BaseModel):
    model: Model = Field(description="切换到的模型")


class CompactionData(BaseModel):
    reason: str = Field(description="压缩原因")
    summary: str = Field(description="压缩摘要")
    include: Optional[str] = Field(default=None, description="额外包含内容")


MessageData = Union[
    UserData,
    AssistantData,
    SyntheticData,
    ShellData,
    AgentSwitchedData,
    ModelSwitchedData,
    CompactionData,
]

MessageType = Literal[
    "user",
    "assistant",
    "synthetic",
    "shell",
    "agent-switched",
    "model-switched",
    "compaction",
]


class SessionMessage(BaseModel):
    id: str = Field(description="消息唯一标识")
    session_id: str = Field(description="所属会话 ID")
    type: MessageType = Field(description="消息类型，决定 data 结构")
    time_created: int = Field(description="创建时间戳（Unix 毫秒）")
    time_updated: int = Field(description="更新时间戳（Unix 毫秒）")
    data: MessageData = Field(description="按 type 的结构化数据")


# ── Session ─────────────────────────────────────────────────────


SessionStatus = Literal["active", "completed", "archived"]


class Session(BaseModel):
    id: str = Field(default_factory=_generate_id, description="会话唯一标识")
    status: SessionStatus = Field(default="active", description="会话状态")
    title: str = Field(default="", description="会话标题")
    cwd: str = Field(default="", description="工作目录")
    provider: ProviderID = Field(description="LLM 提供商 ID")
    model: ModelID = Field(description="LLM 模型 ID")
    agent_version: str = Field(default="", description="Agent 版本")
    turn_count: int = Field(default=0, description="对话轮次数")
    step_count: int = Field(default=0, description="循环步数")
    input_tokens: int = Field(default=0, description="累积输入 Token")
    output_tokens: int = Field(default=0, description="累积输出 Token")
    reasoning_tokens: int = Field(default=0, description="累积推理 Token")
    cache_read_tokens: int = Field(default=0, description="累积缓存读取 Token")
    cache_write_tokens: int = Field(default=0, description="累积缓存写入 Token")
    cost: int = Field(default=0, description="累积消耗（微美分）")
    parent_id: Optional[str] = Field(default=None, description="父会话 ID，用于压缩链")
    fork_id: Optional[str] = Field(default=None, description="分叉源会话 ID")
    message_count: int = Field(default=0, description="消息数")
    summary: Optional[str] = Field(default=None, description="会话摘要")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=_utcnow, description="最后更新时间")
    ended_at: Optional[datetime] = Field(default=None, description="完成/归档时间")


# ── Todo ────────────────────────────────────────────────────────


TodoStatus = Literal["pending", "in_progress", "completed", "cancelled", "blocked"]
TodoPriority = Literal["high", "medium", "low"]


class TodoItem(BaseModel):
    id: str = Field(default_factory=_generate_id, description="待办唯一标识")
    session_id: str = Field(description="所属会话 ID")
    content: str = Field(description="待办内容")
    status: TodoStatus = Field(default="pending", description="状态")
    priority: TodoPriority = Field(default="medium", description="优先级")
    depends_on: list[str] = Field(default_factory=list, description="依赖的待办 ID 列表")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=_utcnow, description="更新时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    task_tool_id: Optional[str] = Field(default=None, description="关联的任务工具 ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class TodoCreate(BaseModel):
    content: str = Field(description="待办内容")
    priority: TodoPriority = Field(default="medium", description="优先级")
    depends_on: list[str] = Field(default_factory=list, description="依赖的待办 ID 列表")
    id: Optional[str] = Field(default=None, description="自定义 ID，用于计划引用")


class TodoUpdate(BaseModel):
    content: Optional[str] = Field(default=None, description="待办内容")
    status: Optional[TodoStatus] = Field(default=None, description="状态")
    priority: Optional[TodoPriority] = Field(default=None, description="优先级")
    depends_on: Optional[list[str]] = Field(default=None, description="依赖的待办 ID 列表")
    task_tool_id: Optional[str] = Field(default=None, description="关联的任务工具 ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="扩展元数据")


# ── Title ───────────────────────────────────────────────────────


class TitleConfig(BaseModel):
    mode: Literal["off", "on_create", "on_compact", "auto"] = Field(default="auto", description="标题生成模式")
    model: Optional[ModelID] = Field(default=None, description="覆盖 LLM 模型")
    prompt: str = Field(
        default="Generate a concise title (max 8 words) for this coding conversation. "
        "Return only the title, no explanation or punctuation.",
        description="标题生成提示词",
    )
