"""Todo domain models — only domain-specific models live here."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from laffyhand.core.db.models import TodoPriority, TodoStatus


class TodoCreate(BaseModel):
    content: str = Field(description="待办内容")
    priority: TodoPriority = Field(default="medium", description="优先级")
    depends_on: list[str] = Field(
        default_factory=list, description="依赖的待办 ID 列表"
    )
    id: Optional[str] = Field(default=None, description="自定义 ID，用于计划引用")


class TodoUpdate(BaseModel):
    content: Optional[str] = Field(default=None, description="待办内容")
    status: Optional[TodoStatus] = Field(default=None, description="状态")
    priority: Optional[TodoPriority] = Field(default=None, description="优先级")
    depends_on: Optional[list[str]] = Field(
        default=None, description="依赖的待办 ID 列表"
    )
    task_tool_id: Optional[str] = Field(default=None, description="关联的任务工具 ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="扩展元数据")
