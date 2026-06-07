from __future__ import annotations

from laffyhand.core.llm.specs.models import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from laffyhand.core.compaction import prune
from laffyhand.core.models import CompactionConfig


PRUNE_PROTECT = CompactionConfig().prune_protect
PRUNE_MINIMUM = CompactionConfig().prune_minimum
PRUNE_MIN_SAVINGS = CompactionConfig().prune_min_savings


def _tool(content: str, tool_call_id: str = "call_1") -> ToolMessage:
    return ToolMessage(tool_call_id=tool_call_id, content=content)


def _assistant() -> AssistantMessage:
    return AssistantMessage(content="ok")


def _user(content: str = "hello") -> UserMessage:
    return UserMessage(content=content)


def _system(content: str = "system") -> SystemMessage:
    return SystemMessage(content=content)


def test_skip_when_context_well_within_limit() -> None:
    """Early exit when curr_context_usage < 70% of context_size."""
    msgs = [_tool("x" * 1000)]
    result = prune(msgs, curr_context_usage=10_000, context_size=100_000)
    assert result is msgs


def test_skip_when_context_size_is_zero() -> None:
    """When context_size is 0, prune should still run based on token estimation."""
    msgs = [_tool("x" * 100)]
    result = prune(msgs, curr_context_usage=0, context_size=0)
    assert result is msgs


def test_no_prune_when_total_under_protect() -> None:
    """When total tool tokens <= PRUNE_PROTECT, no pruning."""
    msgs = [_tool("x" * PRUNE_PROTECT)]
    result = prune(msgs, curr_context_usage=100_000, context_size=128_000)
    assert result is msgs


# estimate_tokens uses round(len(text) / 4), so 200K bytes ≈ 50K tokens (> PRUNE_PROTECT 40K)
_BIG = "x" * 200_000


def test_prunes_largest_tool_first() -> None:
    """With context near limit, large tool messages get pruned."""
    big = _tool(_BIG)
    small = _tool("short", tool_call_id="call_2")
    msgs: list[Message] = [big, small, _assistant()]
    result = prune(msgs, curr_context_usage=100_000, context_size=128_000)
    assert "[Old tool result content cleared" in result[0].content
    # small tool message should be preserved (too small to prune individually)
    assert result[1].content == "short"


def test_preserves_non_tool_messages() -> None:
    """User and Assistant messages are never pruned."""
    sys_msg = _system()
    user_msg = _user("hello")
    asst_msg = _assistant()
    tool_msg = _tool(_BIG)
    msgs: list[Message] = [sys_msg, user_msg, asst_msg, tool_msg]
    result = prune(msgs, curr_context_usage=100_000, context_size=128_000)
    assert isinstance(result[0], SystemMessage)
    assert isinstance(result[1], UserMessage)
    assert isinstance(result[2], AssistantMessage)
    assert "[Old tool result content cleared" in result[3].content


def test_small_tools_below_min_savings_skipped() -> None:
    """Tool messages under _PRUNE_MIN_SAVINGS (50) tokens are not pruned."""
    small_tool = _tool("short", tool_call_id="call_1")
    msgs = [_tool(_BIG, tool_call_id="call_0"), small_tool, _assistant()]
    result = prune(msgs, curr_context_usage=100_000, context_size=128_000)
    # small tool message should keep its content
    assert result[1].content == "short"


def test_multiple_large_tools_all_pruned() -> None:
    """When multiple tools exceed target, multiple get pruned."""
    t1 = _tool(_BIG, tool_call_id="call_1")
    t2 = _tool(_BIG, tool_call_id="call_2")
    msgs: list[Message] = [t1, t2, _assistant()]
    result = prune(msgs, curr_context_usage=100_000, context_size=128_000)
    assert "[Old tool result content cleared" in result[0].content
    assert "[Old tool result content cleared" in result[1].content


def test_preserves_tool_call_id_after_prune() -> None:
    """Tool call IDs are preserved in pruned messages."""
    msgs = [_tool("x" * PRUNE_PROTECT * 2, tool_call_id="call_xyz")]
    result = prune(msgs, curr_context_usage=100_000, context_size=128_000)
    assert isinstance(result[0], ToolMessage)
    assert result[0].tool_call_id == "call_xyz"


def test_prune_minimum_respected() -> None:
    """Pruning should stop when remaining tokens drop below PRUNE_MINIMUM."""
    _MODERATE = "x" * 60_000  # ~15K tokens each
    many_msgs = [_tool(_MODERATE, tool_call_id=f"call_{i}") for i in range(10)]
    result = prune(many_msgs, curr_context_usage=100_000, context_size=128_000)
    # At least some should remain unpruned (we stop at PRUNE_MINIMUM or when target is hit)
    pruned_count = sum(
        1 for m in result if "[Old tool result content cleared" in m.content
    )
    assert 0 < pruned_count < 10
