from loguru import logger
from pydantic import BaseModel
from typing import Optional, Literal, List, Union


CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(0, round(len(text) / CHARS_PER_TOKEN))


# ─── Tool Definition (provider-agnostic) ────────────────────────

class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict


class ToolCallContent(BaseModel):
    type: Literal['tool-call'] = 'tool-call'
    tool_call_id: str
    tool_name: str
    args: str


# ─── Prompt Messages ────────────────────────────────────────────────

class SystemMessage(BaseModel):
    role: Literal['system'] = 'system'
    content: str


class UserMessage(BaseModel):
    role: Literal['user'] = 'user'
    content: str


class AssistantMessage(BaseModel):
    role: Literal['assistant'] = 'assistant'
    content: Optional[str] = None
    reasoning: Optional[str] = None
    tool_calls: Optional[List[ToolCallContent]] = None
    tokens: Optional['Usage'] = None


class ToolMessage(BaseModel):
    role: Literal['tool'] = 'tool'
    tool_call_id: str
    content: str


class CompactionConfig(BaseModel):
    tail_turns: int = 2
    """Number of recent user turns to preserve verbatim during compaction."""
    preserve_recent_tokens: Optional[int] = None
    """Maximum tokens to reserve for preserved turns. If None, computed dynamically (25% of usable)."""
    reserved: Optional[int] = None
    """Token buffer for compaction LLM call. If None, uses min(20k, maxOutputTokens)."""
    prune: bool = True
    """Whether to prune old tool outputs to free context."""
    auto_continue: bool = True
    """Whether to auto-continue conversation after compaction."""
    summary_tool_truncate: int = 500
    """Max characters of tool output to include in compaction summary text."""


Message = Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]


# ─── LLM Request ─────────────────────────────────────────────────────

class LLMRequest(BaseModel):
    model: str
    messages: list[Message]
    tools: Optional[list[ToolDefinition]] = None


# ─── Usage ──────────────────────────────────────────────────────────

class Usage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None


def _k(n: int) -> str:
    s = f"{n / 1000:.1f}".rstrip("0").rstrip(".")
    return f"{s}k"


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
        logger.debug(f"Usage added: +{usage.input_tokens or 0} in, +{usage.output_tokens or 0} out")

    def display(self, usage: Usage) -> str:
        inp = usage.input_tokens or 0
        out = usage.output_tokens or 0
        cache = usage.cache_read_tokens or 0
        reasoning = usage.reasoning_tokens or 0
        sess_total = self.total_input + self.total_output
        if self.context_size:
            pct = f" ({sess_total / self.context_size * 100:.2f}%)"
            limit = _k(self.context_size)
        else:
            pct = ""
            limit = _k(sess_total)
        parts = [f"⬆{_k(inp)}", f"⬇{_k(out)}"]
        if reasoning:
            parts.append(f"🧠{_k(reasoning)}")
        if cache:
            parts.append(f"📦{_k(cache)}")
        if self.total_reasoning:
            parts.append(f"🧠Σ{_k(self.total_reasoning)}")
        if self.total_cache_read:
            parts.append(f"📦Σ{_k(self.total_cache_read)}")
        return f"[{' / '.join(parts)} | {_k(sess_total)}/{limit}{pct}]"


# ─── Stream Events ──────────────────────────────────────────────────

class StreamText(BaseModel):
    type: Literal['text'] = 'text'
    delta: str


class StreamReasoning(BaseModel):
    type: Literal['reasoning'] = 'reasoning'
    delta: str


class StreamToolCall(BaseModel):
    type: Literal['tool-call'] = 'tool-call'
    tool_call_id: str
    tool_name: str
    args: str


FinishReason = Literal['stop', 'length', 'content_filter', 'tool_calls', 'error', 'other']

class StreamFinish(BaseModel):
    type: Literal['finish'] = 'finish'
    finish_reason: FinishReason
    usage: Optional[Usage] = None


class StreamError(BaseModel):
    type: Literal['error'] = 'error'
    error: str


class AgentState(BaseModel):
    messages: List[Message]
    turn_count: int = 0
    step: int = 0
    usage: SessionUsage = SessionUsage()


StreamEvent = Union[StreamText, StreamReasoning, StreamToolCall, StreamFinish, StreamError]
