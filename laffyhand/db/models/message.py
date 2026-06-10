from __future__ import annotations

from typing import Any, List, Literal, Optional, Sequence, Union

from pydantic import BaseModel, Field

from laffyhand.core.domain.messages import FilePart


class UserData(BaseModel):
    text: str = Field(description="用户消息文本")
    files: List[FilePart] = Field(
        default_factory=list, description="通过 @ 指定文件的对应内容"
    )
    agents: List[str] = Field(default_factory=list, description="通过 @ 指定的 Agent")
    references: List[str] = Field(
        default_factory=list, description="通过 @ 指定的文件路径"
    )


class MessageTime(BaseModel):
    created: int = Field(description="创建时间（Unix 时间戳）")
    completed: Optional[int] = Field(
        default=None, description="完成时间（Unix 时间戳）"
    )


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


ToolState = Union[
    ToolStatePending, ToolStateRunning, ToolStateCompleted, ToolStateError
]


class AssistantToolPart(BaseModel):
    type: Literal["tool"] = "tool"
    id: str = Field(description="工具调用 ID")
    name: str = Field(description="工具名称")
    provider: Optional[dict[str, Any]] = Field(default=None, description="提供者信息")
    state: ToolState = Field(description="工具状态")
    time: MessageTime = Field(description="时间信息")


AssistantContent = Union[AssistantTextPart, AssistantReasoningPart, AssistantToolPart]


class AssistantData(BaseModel):
    agent: str = Field(description="agent 名称")
    model: dict[str, Any] = Field(default_factory=dict, description="回复模型")
    content: Sequence[AssistantContent] = Field(
        default_factory=list, description="按时间顺序排列的消息内容数组"
    )
    snapshot: MessageSnapshot = Field(description="快照信息")
    finish: str = Field(default="stop", description="结束原因")
    cost: int = Field(description="消耗（微美分）")
    tokens: Optional[TokenDetail] = Field(default=None, description="Token 用量")
    error: Optional[str] = Field(default=None, description="错误信息")


class SyntheticData(BaseModel):
    session_id: str = Field(description="源会话 ID")
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
    model: dict[str, Any] = Field(default_factory=dict, description="切换到的模型")


class CompactionData(BaseModel):
    reason: str = Field(description="压缩原因")
    summary: str = Field(description="压缩摘要")
    include: Optional[str] = Field(default=None, description="额外包含内容")
    child_session_id: Optional[str] = Field(default=None, description="压缩后的子会话 ID")


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
