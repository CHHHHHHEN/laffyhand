from __future__ import annotations

from typing import NewType

from loguru import logger
from pydantic import BaseModel, Field

from laffyhand.core.llm.specs.models import Message, Usage

SessionID = NewType("SessionID", str)


class SessionUsage(BaseModel):
    curr_context_usage: int = Field(default=0)
    total_input: int = Field(default=0)
    total_output: int = Field(default=0)
    total_reasoning: int = Field(default=0)
    total_cache_read: int = Field(default=0)
    total_cache_write: int = Field(default=0)
    context_size: int = Field(default=0)
    cost: int = Field(default=0)

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
    messages: list[Message] = Field(description="当前会话的消息列表")
    turn_count: int = Field(default=0)
    step: int = Field(default=0)
    usage: SessionUsage = Field(default_factory=SessionUsage)
    session_id: SessionID = Field(description="当前会话 ID")
    interrupt_requested: bool = Field(default=False)
    pending_steer: str | None = Field(default=None)
    disabled_tools: set[str] = Field(default_factory=set)


__all__ = [
    "AgentState",
    "SessionID",
    "SessionUsage",
]
