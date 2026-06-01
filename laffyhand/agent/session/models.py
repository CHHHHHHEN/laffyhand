from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _from_ts(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts is not None else None


def _generate_session_id() -> str:
    from uuid import uuid4

    now = _utcnow()
    return now.strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]


SessionStatus = Literal["active", "completed", "archived"]


class Session(BaseModel):
    id: str = ""
    status: SessionStatus = "active"
    title: str = ""
    cwd: str = ""
    provider: str = ""
    model: str = ""
    agent_version: str = ""
    turn_count: int = 0
    step_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    parent_id: Optional[str] = None
    fork_id: Optional[str] = None
    message_count: int = 0
    summary: Optional[str] = None
    metadata: dict[str, Any] = {}
    created_at: datetime = _utcnow()
    updated_at: datetime = _utcnow()
    ended_at: Optional[datetime] = None

    def model_post_init(self, _context: Any) -> None:
        if not self.id:
            self.id = _generate_session_id()


class MessageRecord(BaseModel):
    id: int = 0
    session_id: str = ""
    role: str = ""
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[str] = None
    reasoning: Optional[str] = None
    token_count: Optional[int] = None
    timestamp: datetime = _utcnow()
    turn_index: int = 0


TodoStatus = Literal["pending", "in_progress", "completed", "cancelled", "blocked"]
TodoPriority = Literal["high", "medium", "low"]


class TodoItem(BaseModel):
    id: str = ""
    session_id: str = ""
    content: str = ""
    status: TodoStatus = "pending"
    priority: TodoPriority = "medium"
    depends_on: list[str] = []
    created_at: datetime = _utcnow()
    updated_at: datetime = _utcnow()
    completed_at: Optional[datetime] = None
    task_tool_id: Optional[str] = None
    metadata: dict[str, Any] = {}

    def model_post_init(self, _context: Any) -> None:
        if not self.id:
            self.id = _generate_session_id()


class TodoCreate(BaseModel):
    content: str
    priority: TodoPriority = "medium"
    depends_on: list[str] = []
    id: Optional[str] = None  # custom ID for plan references


class TodoUpdate(BaseModel):
    content: Optional[str] = None
    status: Optional[TodoStatus] = None
    priority: Optional[TodoPriority] = None
    depends_on: Optional[list[str]] = None
    task_tool_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class TitleConfig(BaseModel):
    mode: Literal["off", "on_create", "on_compact", "auto"] = "auto"
    model: Optional[str] = None
    prompt: str = (
        "Generate a concise title (max 8 words) for this coding conversation. "
        "Return only the title, no explanation or punctuation."
    )
