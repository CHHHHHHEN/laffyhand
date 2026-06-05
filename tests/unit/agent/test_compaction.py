from __future__ import annotations

from laffyhand.core.compaction import (
    _is_summary_content,
    _summary_depth,
    build_summary_text,
    is_overflow,
    select_tail,
)
from laffyhand.core.llm.specs.models import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCallContent,
    ToolMessage,
    UserMessage,
)
from laffyhand.core.schemas import CompactionConfig


# ── is_overflow ──────────────────────────────────────────────


def test_no_overflow_when_context_zero() -> None:
    assert is_overflow(100_000, 0, 1_000) is False


def test_no_overflow_within_usable() -> None:
    assert is_overflow(10_000, 128_000, 20_000) is False


def test_overflow_exceeds_usable() -> None:
    assert is_overflow(120_000, 128_000, 20_000) is True


def test_overflow_exact_boundary() -> None:
    usable = 128_000 - 20_000
    assert is_overflow(usable, 128_000, 20_000) is True
    assert is_overflow(usable - 1, 128_000, 20_000) is False


# ── _is_summary_content ─────────────────────────────────────


def test_is_summary_content_valid() -> None:
    assert _is_summary_content("<summary>\ncontent\n</summary>") is True


def test_is_summary_content_no_tags() -> None:
    assert _is_summary_content("plain text") is False


def test_is_summary_content_missing_close() -> None:
    assert _is_summary_content("<summary>\ncontent") is False


def test_is_summary_content_extra_text_before() -> None:
    assert _is_summary_content("extra <summary>\ncontent\n</summary>") is False


# ── _summary_depth ──────────────────────────────────────────


def test_summary_depth_zero() -> None:
    msgs: list[Message] = [
        SystemMessage(content="system"),
        UserMessage(content="hello"),
    ]
    assert _summary_depth(msgs) == 0


def test_summary_depth_one() -> None:
    msgs: list[Message] = [
        SystemMessage(content="<summary>\nsummary\n</summary>"),
        UserMessage(content="hello"),
    ]
    assert _summary_depth(msgs) == 1


def test_summary_depth_multiple() -> None:
    msgs: list[Message] = [
        UserMessage(content="<summary>\nnested\n</summary>"),
        SystemMessage(content="<summary>\noriginal\n</summary>"),
    ]
    assert _summary_depth(msgs) == 2


def test_summary_depth_ignores_non_summary() -> None:
    msgs: list[Message] = [
        SystemMessage(content="normal"),
        UserMessage(content="<summary>\nsummary\n</summary>"),
        AssistantMessage(content="ok"),
    ]
    assert _summary_depth(msgs) == 1


# ── build_summary_text ──────────────────────────────────────


def test_build_summary_text_empty() -> None:
    assert build_summary_text([], tool_truncate=500) == ""


def test_build_summary_text_simple() -> None:
    msgs: list[Message] = [
        SystemMessage(content="system prompt"),
        UserMessage(content="hello"),
        AssistantMessage(content="world"),
    ]
    text = build_summary_text(msgs)
    assert "[System]: system prompt" in text
    assert "[User]: hello" in text
    assert "[Assistant]: world" in text


def test_build_summary_text_with_tool_results() -> None:
    msgs: list[Message] = [
        UserMessage(content="list files"),
        ToolMessage(tool_call_id="call_1", content="file1\nfile2"),
    ]
    text = build_summary_text(msgs)
    assert "[User]: list files" in text
    assert "[Tool Result - call_1]:" in text
    assert "file1" in text


def test_build_summary_text_truncates_tool_output() -> None:
    msgs: list[Message] = [
        ToolMessage(tool_call_id="call_1", content="x" * 1000),
    ]
    text = build_summary_text(msgs, tool_truncate=50)
    assert len(text) < 200


def test_build_summary_text_includes_reasoning() -> None:
    msgs: list[Message] = [
        AssistantMessage(content="answer", reasoning="deep thoughts"),
    ]
    text = build_summary_text(msgs)
    assert "[Assistant]: answer" in text
    assert "[Reasoning]: deep thoughts" in text


def test_build_summary_text_includes_tool_calls() -> None:
    msgs: list[Message] = [
        AssistantMessage(
            content="",
            tool_calls=[ToolCallContent(tool_name="read", args='{"file_path": "/x"}', tool_call_id="call_1")],
        ),
    ]
    text = build_summary_text(msgs)
    assert "[Tool Call: read]" in text


def test_build_summary_text_previous_summary() -> None:
    msgs: list[Message] = [
        SystemMessage(content="<summary>\nprev summary\n</summary>"),
        UserMessage(content="continue"),
    ]
    text = build_summary_text(msgs)
    assert "[Previous Summary]:" in text
    assert "prev summary" in text


# ── select_tail ─────────────────────────────────────────────


def _cfg(**kwargs: object) -> CompactionConfig:
    defaults: dict[str, object] = {
        "tail_turns": 2,
        "preserve_recent_tokens": 0,
        "reserved": 0,
        "summary_tool_truncate": 500,
        "mode": "chain",
    }
    return CompactionConfig(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_select_tail_all_content_when_within_budget() -> None:
    msgs: list[Message] = [_user("hi"), _assistant()]
    head, tail = select_tail(msgs, _cfg(tail_turns=2), context_size=128_000)
    assert head == []
    assert len(tail) == 2


def test_select_tail_splits_early_turns() -> None:
    msgs: list[Message] = [
        _user("turn1"),
        _assistant(),
        _user("turn2"),
        _assistant(),
        _user("turn3"),
        _assistant(),
    ]
    head, tail = select_tail(
        msgs,
        _cfg(tail_turns=1, preserve_recent_tokens=1),
        context_size=128_000,
    )
    assert len(head) > 0
    assert len(tail) > 0
    # Tail should contain at most 1 user turn
    tail_user_turns = sum(1 for m in tail if isinstance(m, UserMessage))
    assert tail_user_turns <= 1


def test_select_tail_no_content_messages() -> None:
    msgs: list[Message] = [_system("only system")]
    head, tail = select_tail(msgs, _cfg(), context_size=128_000)
    assert head == []
    assert len(tail) == 1


def test_select_tail_empty_messages() -> None:
    head, tail = select_tail([], _cfg(), context_size=128_000)
    assert head == []
    assert tail == []


def test_select_tail_system_msgs_in_head() -> None:
    msgs: list[Message] = [
        _system("sys"),
        _user("turn1"),
        _assistant(),
        _user("turn2"),
        _assistant(),
    ]
    head, tail = select_tail(
        msgs,
        _cfg(tail_turns=1, preserve_recent_tokens=1),
        context_size=128_000,
    )
    # System messages always go to head
    assert any(isinstance(m, SystemMessage) for m in head)
    assert not any(isinstance(m, SystemMessage) for m in tail)


def test_select_tail_no_split_when_tail_covers_all() -> None:
    msgs: list[Message] = [_user("only turn"), _assistant()]
    head, tail = select_tail(msgs, _cfg(tail_turns=5), context_size=128_000)
    assert head == []
    assert len(tail) == 2


def test_select_tail_respects_preserve_recent_tokens() -> None:
    msgs: list[Message] = [
        _user("a" * 10_000),
        _assistant(),
        _user("b"),
        _assistant(),
    ]
    head, tail = select_tail(
        msgs,
        _cfg(tail_turns=2, preserve_recent_tokens=5_000),
        context_size=128_000,
    )
    assert len(tail) > 0


# ── helpers ─────────────────────────────────────────────────


def _user(content: str = "hi") -> UserMessage:
    return UserMessage(content=content)


def _assistant(content: str = "ok") -> AssistantMessage:
    return AssistantMessage(content=content)


def _system(content: str = "sys") -> SystemMessage:
    return SystemMessage(content=content)
