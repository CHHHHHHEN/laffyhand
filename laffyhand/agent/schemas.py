from __future__ import annotations

from loguru import logger
from pydantic import BaseModel
from typing import Optional, List

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


class AgentState(BaseModel):
    messages: List[Message]
    turn_count: int = 0
    step: int = 0
    usage: SessionUsage = SessionUsage()
    session_id: Optional[str] = None
    interrupt_requested: bool = False
    pending_steer: Optional[str] = None
