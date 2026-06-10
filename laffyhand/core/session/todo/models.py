from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from laffyhand.core._utils.time import generate_id, utcnow


TodoStatus = Literal["pending", "in_progress", "completed", "blocked"]


class TodoItem(BaseModel):
    id: str = Field(default_factory=generate_id, description="待办唯一标识")
    session_id: str = Field(description="所属会话 ID")
    content: str = Field(description="待办内容")
    status: TodoStatus = Field(default="pending", description="状态")
    depends_on: list[str] = Field(
        default_factory=list, description="依赖的待办 ID 列表"
    )
    created_at: datetime = Field(default_factory=utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=utcnow, description="更新时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    task_tool_id: Optional[str] = Field(default=None, description="关联的任务工具 ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class TodoCreate(BaseModel):
    content: str = Field(description="待办内容")
    depends_on: list[str] = Field(
        default_factory=list, description="依赖的待办 ID 列表"
    )
    id: Optional[str] = Field(default=None, description="自定义 ID，用于计划引用")


class TodoUpdate(BaseModel):
    content: Optional[str] = Field(default=None, description="待办内容")
    status: Optional[TodoStatus] = Field(default=None, description="状态")
    depends_on: Optional[list[str]] = Field(
        default=None, description="依赖的待办 ID 列表"
    )
    task_tool_id: Optional[str] = Field(default=None, description="关联的任务工具 ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="扩展元数据")
