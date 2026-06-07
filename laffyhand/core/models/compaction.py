from __future__ import annotations

from pydantic import BaseModel, Field


class CompactionConfig(BaseModel):
    tail_turns: int = Field(default=2)
    preserve_recent_tokens: int = Field(default=0)
    reserved: int = Field(default=0)
    prune: bool = Field(default=True)
    auto_continue: bool = Field(default=True)
    summary_tool_truncate: int = Field(default=2000)
    max_summary_depth: int = Field(default=3)
    reserved_buffer: int = Field(default=20_000)
    prune_protect: int = Field(default=40_000)
    prune_minimum: int = Field(default=20_000)
    prune_min_savings: int = Field(default=50)


class RetryConfig(BaseModel):
    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0


__all__ = [
    "CompactionConfig",
    "RetryConfig",
]
