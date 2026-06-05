from __future__ import annotations

from loguru import logger
from pydantic import BaseModel, Field
from typing import NewType

from laffyhand.core.llm.specs.models import Message, Usage


SessionID = NewType("SessionID", str)


class CompactionConfig(BaseModel):
    tail_turns: int = Field(default=2, description="保留的最近对话轮次数")
    preserve_recent_tokens: int = Field(default=0, description="保留轮次的 Token 预算上限，0 表示自动")
    reserved: int = Field(default=0, description="为 LLM 输出预留的 Token 缓冲，0 表示自动")
    prune: bool = Field(default=True, description="工具调用后是否修剪历史工具输出")
    auto_continue: bool = Field(default=True, description="压缩后是否自动注入继续提示")
    summary_tool_truncate: int = Field(default=2000, description="摘要中单条工具输出截断长度（Token）")
    max_summary_depth: int = Field(default=3, description="嵌套摘要的最大深度")
    reserved_buffer: int = Field(default=20_000, description="预留 Token 缓冲上限")
    prune_protect: int = Field(default=40_000, description="修剪保护阈值（Token），低于此值跳过修剪")
    prune_minimum: int = Field(default=20_000, description="修剪后至少保留的 Token 数")
    prune_min_savings: int = Field(default=50, description="单条消息最少节省 Token 数，低于此值跳过修剪")


class SessionUsage(BaseModel):
    curr_context_usage: int = Field(default=0, description="当前单次请求已使用Token数量")
    total_input: int = Field(default=0, description="整个会话累积的输入 Token 数")
    total_output: int = Field(default=0, description="整个会话累积的输出 Token 数")
    total_reasoning: int = Field(default=0, description="整个会话累积的推理 Token 数")
    total_cache_read: int = Field(default=0, description="整个会话累积的缓存命中 Token 数")
    total_cache_write: int = Field(default=0, description="整个会话累积的缓存写入 Token 数")
    context_size: int = Field(default=0, description="模型上下文窗口大小（Token）")
    cost: int = Field(default=0, description="整个会话累积的消耗（微美分）")

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
    turn_count: int = Field(default=0, description="已完成的对话轮次数")
    step: int = Field(default=0, description="当前轮次内的步骤计数")
    usage: SessionUsage = Field(default_factory=SessionUsage, description="整个会话的Token用量统计")
    session_id: SessionID = Field(description="当前会话 ID")
    interrupt_requested: bool = Field(default=False, description="用户请求中断标志")
    pending_steer: str | None = Field(default=None, description="待注入的用户引导文本")
    disabled_tools: set[str] = Field(default_factory=set, description="当前会话禁用的工具名称集合")


class RetryConfig(BaseModel):
    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0


__all__ = [
    "SessionID",
    "CompactionConfig",
    "SessionUsage",
    "AgentState",
    "RetryConfig",
]
