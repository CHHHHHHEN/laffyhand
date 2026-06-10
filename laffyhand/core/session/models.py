from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from laffyhand.core._utils.time import generate_id, utcnow
from laffyhand.core.domain.messages import ModelID, ProviderID


ModelVariant = Literal["none", "low", "medium", "high", "xhigh"]


class Model(BaseModel):
    id: ModelID = Field(description="模型ID")
    provider: ProviderID = Field(description="LLM提供商ID")
    variant: Optional[ModelVariant] = None


SessionStatus = Literal["active", "archived"]


class Session(BaseModel):
    id: str = Field(default_factory=generate_id, description="会话唯一标识")
    status: SessionStatus = Field(default="active", description="会话状态")
    title: str = Field(default="", description="会话标题")
    cwd: str = Field(default="", description="工作目录")
    provider: ProviderID = Field(description="LLM 提供商 ID")
    model: ModelID = Field(description="LLM 模型 ID")
    agent_name: str = Field(default="", description="Agent 名称")
    turn_count: int = Field(default=0, description="对话轮次数")
    step_count: int = Field(default=0, description="循环步数")
    input_tokens: int = Field(default=0, description="累积输入 Token")
    output_tokens: int = Field(default=0, description="累积输出 Token")
    reasoning_tokens: int = Field(default=0, description="累积推理 Token")
    cache_read_tokens: int = Field(default=0, description="累积缓存读取 Token")
    cache_write_tokens: int = Field(default=0, description="累积缓存写入 Token")
    parent_id: Optional[str] = Field(default=None, description="父会话 ID，用于压缩链")
    message_count: int = Field(default=0, description="消息数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
    created_at: datetime = Field(default_factory=utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=utcnow, description="最后更新时间")


class TitleConfig(BaseModel):
    mode: Literal["off", "on_create", "on_compact", "auto"] = Field(
        default="auto", description="标题生成模式"
    )
    model: Optional[ModelID] = Field(default=None, description="覆盖 LLM 模型")
    prompt: str = Field(
        default="Generate a concise title (max 8 words) for this coding conversation. "
        "Return only the title, no explanation or punctuation.",
        description="标题生成提示词",
    )
