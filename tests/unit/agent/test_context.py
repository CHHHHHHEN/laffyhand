from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import pytest

from laffyhand.core.llm.specs.models import AssistantMessage, SystemMessage, ToolMessage, UserMessage
from laffyhand.core.llm.specs.models import (
    StreamError,
    StreamFinish,
    StreamText,
    ToolCallContent,
)
from laffyhand.core.models import (
    AgentState,
    CompactionConfig,
    SessionID,
    SessionUsage,
)
from laffyhand.core.context.chain import (
    compact_with_chain,
    is_overflow,
    select_tail,
    _select_compaction_targets,
)
from laffyhand.core.context._summarize import build_summary_text
from laffyhand.core.context._prune import prune
from laffyhand.core.context._summarize import _is_summary_content
from laffyhand.core._utils import (
    estimate_message_tokens,
    estimate_messages_tokens,
)


PRUNE_PROTECT = CompactionConfig().prune_protect


class TestEstimateMessageTokens(unittest.TestCase):
    def test_system_message(self):
        msg = SystemMessage(content="hello world")
        self.assertEqual(estimate_message_tokens(msg), 3)

    def test_user_message(self):
        msg = UserMessage(content="test")
        self.assertEqual(estimate_message_tokens(msg), 1)

    def test_assistant_content(self):
        msg = AssistantMessage(content="response text")
        self.assertEqual(estimate_message_tokens(msg), 3)

    def test_assistant_reasoning(self):
        msg = AssistantMessage(content="short", reasoning="long reasoning text here")
        self.assertEqual(estimate_message_tokens(msg), 7)

    def test_assistant_tool_calls(self):
        tc = ToolCallContent(
            tool_call_id="c1", tool_name="test_tool", args='{"key": "val"}'
        )
        msg = AssistantMessage(content=None, tool_calls=[tc])
        self.assertGreater(estimate_message_tokens(msg), 0)

    def test_tool_message(self):
        msg = ToolMessage(tool_call_id="c1", content="result data")
        self.assertEqual(estimate_message_tokens(msg), 3)

    def test_estimate_messages_tokens(self):
        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="user msg"),
            AssistantMessage(content="asst"),
        ]
        self.assertEqual(estimate_messages_tokens(msgs), 4)


class TestIsOverflow(unittest.TestCase):
    def test_no_overflow(self):
        self.assertFalse(is_overflow(1000, 100_000, 5_000))

    def test_overflow_detected(self):
        self.assertTrue(is_overflow(96_000, 100_000, 5_000))

    def test_no_context_size(self):
        self.assertFalse(is_overflow(1000, 0, 5_000))

    def test_small_buffer(self):
        self.assertTrue(is_overflow(25_000, 30_000, 5_000))

    def test_context_smaller_than_reserved_uses_floor(self):
        self.assertTrue(is_overflow(3000, 15_000, reserved=20_000))

    def test_context_smaller_than_reserved_no_overflow(self):
        self.assertFalse(is_overflow(500, 15_000, reserved=20_000))


class TestSelectTail(unittest.TestCase):
    def test_empty_messages(self):
        head, tail = select_tail([], CompactionConfig())
        self.assertEqual(head, [])
        self.assertEqual(tail, [])

    def test_only_system_messages(self):
        msgs = [SystemMessage(content="sys")]
        head, tail = select_tail(msgs, CompactionConfig())
        self.assertEqual(head, [])
        self.assertEqual(tail, msgs)

    def test_all_fits_in_tail(self):
        msgs = [SystemMessage(content="sys"), UserMessage(content="hi")]
        head, tail = select_tail(
            msgs, CompactionConfig(tail_turns=5), context_size=1000
        )
        self.assertEqual(head, [])
        self.assertEqual(len(tail), 2)

    def test_head_tail_split(self):
        msgs = [SystemMessage(content="sys")]
        for i in range(20):
            msgs.append(UserMessage(content=f"user {i}"))
            msgs.append(AssistantMessage(content=f"asst {i}"))
        config = CompactionConfig(tail_turns=2, preserve_recent_tokens=6)
        head, tail = select_tail(msgs, config, context_size=100_000)
        self.assertTrue(len(head) > 0, "expected some messages in head")
        self.assertTrue(len(tail) > 0, "expected some messages in tail")
        tail_users = sum(1 for m in tail if isinstance(m, UserMessage))
        self.assertLessEqual(tail_users, 2, "tail should preserve at most 2 user turns")

    def test_tool_truncation_affects_tail_boundary(self):
        """Tool outputs exceeding summary_tool_truncate should be counted
        at their truncated size during tail boundary selection."""
        # 10000 chars = 2500 tokens without truncation → exceeds budget
        # With truncation to 50 chars = 13 tokens → fits in budget
        msgs = [
            SystemMessage(content="sys"),
            ToolMessage(tool_call_id="c1", content="x" * 10_000),  # very long
            UserMessage(content="recent user"),
            AssistantMessage(content="recent asst"),
        ]
        config = CompactionConfig(
            tail_turns=1,
            preserve_recent_tokens=60,
            summary_tool_truncate=50,
        )
        head, tail = select_tail(msgs, config, context_size=100_000)
        tool_in_tail = any(isinstance(m, ToolMessage) for m in tail)
        self.assertTrue(
            tool_in_tail, "long tool output should fit in tail when truncated"
        )


class TestBuildSummaryText(unittest.TestCase):
    def test_includes_all_types(self):
        msgs = [
            UserMessage(content="user hello"),
            AssistantMessage(
                content="asst hello",
                tool_calls=[
                    ToolCallContent(tool_call_id="c1", tool_name="my_tool", args="{}")
                ],
            ),
            ToolMessage(tool_call_id="c1", content="tool result"),
        ]
        text = build_summary_text(msgs)
        self.assertIn("user hello", text)
        self.assertIn("asst hello", text)
        self.assertIn("my_tool", text)
        self.assertIn("tool result", text)

    def test_empty_messages(self):
        text = build_summary_text([])
        self.assertEqual(text, "")

    def test_tool_truncation_in_summary(self):
        long_result = "x" * 1000
        msgs = [ToolMessage(tool_call_id="c1", content=long_result)]
        text = build_summary_text(msgs, tool_truncate=10)
        self.assertIn("[Tool output truncated:", text)


class TestPrune(unittest.TestCase):
    def test_no_prune_under_threshold(self):
        msgs = [ToolMessage(tool_call_id="c1", content="small")]
        result = prune(msgs)
        self.assertEqual(result[0].content, "small")
        self.assertEqual(msgs[0].content, "small", "should not mutate original")

    def test_prune_large_tool_output(self):
        content = "x" * (PRUNE_PROTECT * 4 + 5)
        msgs = [ToolMessage(tool_call_id="c1", content=content)]
        result = prune(msgs)
        self.assertTrue(
            result[0].content.startswith("[Old tool result content cleared:")
        )
        self.assertEqual(msgs[0].content, content, "should not mutate original")

    def test_prune_multiple_messages_oldest_first(self):
        small = ToolMessage(tool_call_id="c1", content="small")
        large = ToolMessage(tool_call_id="c2", content="x" * (PRUNE_PROTECT * 4 + 5))
        msgs = [small, large]
        result = prune(msgs)
        self.assertEqual(result[0].content, "small", "should not prune tiny messages")
        self.assertTrue(
            result[1].content.startswith("[Old tool result content cleared:")
        )
        self.assertEqual(msgs[1].content, large.content, "should not mutate original")

    def test_prune_no_tool_messages(self):
        msgs = [SystemMessage(content="sys"), UserMessage(content="hi")]
        result = prune(msgs)
        self.assertIs(result, msgs, "no tool messages -> return same list")

    def test_prune_skips_small_savings(self):
        large = ToolMessage(tool_call_id="c1", content="x" * (PRUNE_PROTECT * 4 + 5))
        tiny = ToolMessage(tool_call_id="c2", content="tiny")
        msgs = [tiny, large]
        result = prune(msgs)
        self.assertEqual(
            result[0].content, "tiny", "tiny messages should not be pruned"
        )
        self.assertTrue(
            result[1].content.startswith("[Old tool result content cleared:")
        )

    def test_prune_partial_some_kept(self):
        content1 = "x" * (PRUNE_PROTECT * 4 + 5)
        content2 = "y" * (PRUNE_PROTECT * 4 + 5)
        msgs = [
            ToolMessage(tool_call_id="c1", content=content1),
            ToolMessage(tool_call_id="c2", content=content2),
        ]
        result = prune(msgs)
        pruned_count = sum(
            1
            for m in result
            if m.content.startswith("[Old tool result content cleared:")
        )
        self.assertGreater(pruned_count, 0)
        # Only 2 tool messages in the input, so at most 2 can be pruned
        self.assertLessEqual(pruned_count, 2)


class TestPruneBehavior(unittest.TestCase):
    def test_no_prune_when_disabled(self):
        config = CompactionConfig(prune=False)
        msgs = [
            SystemMessage(content="sys"),
            ToolMessage(tool_call_id="c1", content="test"),
        ]
        result = prune(msgs, curr_context_usage=0, context_size=128_000, config=config)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1].content, "test")

    def test_prune_applied_to_context_view(self):
        config = CompactionConfig(prune=True)
        original = "x" * (PRUNE_PROTECT * 4 + 5)
        msgs = [
            SystemMessage(content="sys"),
            ToolMessage(tool_call_id="c1", content=original),
        ]
        result = prune(
            list(msgs),
            curr_context_usage=128_000,
            context_size=128_000,
            config=config,
        )
        self.assertTrue(
            result[1].content.startswith("[Old tool result content cleared:"),
            "context view should have pruned tool output",
        )
        self.assertEqual(
            msgs[1].content,
            original,
            "original messages must not be mutated by prune",
        )


class TestCompactWithChainStateMutation(unittest.TestCase):
    @pytest.mark.anyio
    async def test_compact_with_chain_and_apply_state(self):
        msgs = [SystemMessage(content="sys")]
        for i in range(20):
            msgs.append(UserMessage(content=f"user {i}"))
            msgs.append(AssistantMessage(content=f"asst {i}"))
        state = AgentState(
            messages=msgs,
            session_id=SessionID("test"),
            usage=SessionUsage(context_size=100_000),
        )
        config = CompactionConfig(tail_turns=2, preserve_recent_tokens=6)

        async def mock_stream(*args, **kwargs):
            yield StreamText(delta="Summary of conversation.")
            yield StreamFinish(finish_reason="stop")

        llm = MagicMock()
        llm.stream = mock_stream

        result = await compact_with_chain(state, llm, config)
        self.assertIsNotNone(result)
        summary, original_system, tail = result
        summary_msg = SystemMessage(content=summary)
        state.messages = original_system + [summary_msg] + tail
        self.assertLess(len(state.messages), len(msgs))
        summary_msgs = [
            m
            for m in state.messages
            if isinstance(m, SystemMessage) and _is_summary_content(m.content)
        ]
        self.assertEqual(
            len(summary_msgs), 1, "should have exactly one summary message"
        )


class TestCompactWithChain(unittest.TestCase):
    @pytest.mark.anyio
    async def test_compact_with_chain_no_head_returns_none(self):
        state = AgentState(
            messages=[SystemMessage(content="sys"), UserMessage(content="hi")],
            session_id=SessionID("test"),
            usage=SessionUsage(context_size=0),
        )
        config = CompactionConfig(tail_turns=5)
        llm = MagicMock()
        result = await compact_with_chain(state, llm, config)
        self.assertIsNone(result)

    @pytest.mark.anyio
    async def test_compact_with_chain_generates_summary(self):
        msgs = [SystemMessage(content="sys")]
        for i in range(20):
            msgs.append(UserMessage(content=f"user {i}"))
            msgs.append(AssistantMessage(content=f"asst {i}"))
        state = AgentState(
            messages=msgs,
            session_id=SessionID("test"),
            usage=SessionUsage(context_size=100_000),
        )
        config = CompactionConfig(tail_turns=2, preserve_recent_tokens=6)

        async def mock_stream(*args, **kwargs):
            yield StreamText(delta="Chain summary.")
            yield StreamFinish(finish_reason="stop")

        llm = MagicMock()
        llm.stream = mock_stream

        result = await compact_with_chain(state, llm, config)
        self.assertIsNotNone(result)
        summary, system_msgs, tail = result
        self.assertIsInstance(summary, str)
        self.assertGreater(len(summary), 0)
        self.assertTrue(
            _is_summary_content(summary), "summary should be wrapped in <summary> tags"
        )
        self.assertIsInstance(system_msgs, list)
        self.assertIsInstance(tail, list)
        self.assertGreater(len(tail), 0)

    @pytest.mark.anyio
    async def test_compact_with_chain_stream_error_returns_none(self):
        msgs = [SystemMessage(content="sys")]
        for i in range(20):
            msgs.append(UserMessage(content=f"user {i}"))
            msgs.append(AssistantMessage(content=f"asst {i}"))
        state = AgentState(
            messages=msgs,
            session_id=SessionID("test"),
            usage=SessionUsage(context_size=100_000),
        )
        config = CompactionConfig(tail_turns=2, preserve_recent_tokens=6)

        async def mock_stream(*args, **kwargs):
            yield StreamError(error="LLM failed")

        llm = MagicMock()
        llm.stream = mock_stream

        result = await compact_with_chain(state, llm, config)
        self.assertIsNone(result)


class TestSummaryChain(unittest.TestCase):
    def test_is_summary_content_detects_tag(self):
        self.assertTrue(_is_summary_content("<summary>\nGoal: test\n</summary>"))
        self.assertFalse(_is_summary_content("Goal: test"))
        self.assertFalse(_is_summary_content(""))

    def test_build_summary_text_handles_previous_summary(self):
        msgs = [
            SystemMessage(
                content="<summary>\nGoal: fix bug\nProgress: done\n</summary>"
            ),
            UserMessage(content="New message"),
        ]
        text = build_summary_text(msgs)
        self.assertIn("[Previous Summary]", text)
        self.assertIn("Goal: fix bug", text)
        self.assertIn("[User]: New message", text)

    def test_build_summary_text_handles_previous_summary_as_usermessage(self):
        msgs = [
            UserMessage(content="<summary>\nGoal: refactor\n</summary>"),
            AssistantMessage(content="OK"),
        ]
        text = build_summary_text(msgs)
        self.assertIn("[Previous Summary]", text)
        self.assertIn("Goal: refactor", text)
        self.assertNotIn("<summary>", text.split("[Previous Summary]")[1])

    def test_build_summary_text_regular_system_not_summary(self):
        msgs = [SystemMessage(content="You are a helpful assistant.")]
        text = build_summary_text(msgs)
        self.assertNotIn("[Previous Summary]", text)

    def test_select_compaction_targets_moves_summary_to_head(self):
        msgs = [
            SystemMessage(content="You are a bot."),  # original system
            SystemMessage(
                content="<summary>\nGoal: fix\n</summary>"
            ),  # previous summary
            UserMessage(content="user1"),
            AssistantMessage(content="asst1"),
            UserMessage(content="user2"),  # last user turn, part of tail
            AssistantMessage(content="asst2"),
        ]
        config = CompactionConfig(tail_turns=1, preserve_recent_tokens=2)
        result = _select_compaction_targets(msgs, config, context_size=100_000)
        self.assertIsNotNone(result)
        head_to_summarize, original_system, tail = result
        # Previous summary should be in head_to_summarize, not in original_system
        summary_in_head = any(_is_summary_content(m.content) for m in head_to_summarize)
        self.assertTrue(
            summary_in_head, "previous summary should be in head_to_summarize"
        )
        summary_in_system = any(_is_summary_content(m.content) for m in original_system)
        self.assertFalse(
            summary_in_system, "previous summary should NOT be in original_system"
        )

    @pytest.mark.anyio
    async def test_second_compaction_passes_previous_summary(self):
        """Compact twice via compact_with_chain; verify that the second
        compaction's input includes the first summary as [Previous Summary]."""
        msgs = [SystemMessage(content="sys")]
        for i in range(10):
            msgs.append(UserMessage(content=f"user {i}"))
            msgs.append(AssistantMessage(content=f"asst {i}"))
        state = AgentState(
            messages=msgs,
            session_id=SessionID("test"),
            usage=SessionUsage(context_size=100_000),
        )
        config = CompactionConfig(tail_turns=1, preserve_recent_tokens=4)

        first_summary = "Goal: first pass\nProgress: initial work"
        call_count = 0
        captured_inputs: list[str] = []

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if args:
                for a in args:
                    if isinstance(a, list):
                        for msg in a:
                            if isinstance(msg, UserMessage):
                                captured_inputs.append(msg.content)
            if call_count == 1:
                yield StreamText(delta=first_summary)
            else:
                yield StreamText(delta="Goal: second pass\nProgress: more work")
            yield StreamFinish(finish_reason="stop")

        llm = MagicMock()
        llm.stream = mock_stream

        async def _apply_compact(state: AgentState) -> bool:
            result = await compact_with_chain(state, llm, config)
            if result is None:
                return False
            summary, original_system, tail = result
            summary_msg = SystemMessage(content=summary)
            state.messages = original_system + [summary_msg] + tail
            return True

        # First compaction
        result1 = await _apply_compact(state)
        self.assertTrue(result1)

        # Add more messages to trigger second compaction
        for i in range(10, 15):
            state.messages.append(UserMessage(content=f"user {i}"))
            state.messages.append(AssistantMessage(content=f"asst {i}"))

        # Second compaction
        result2 = await _apply_compact(state)
        self.assertTrue(result2)

        # Verify that the first summary was passed to the second compaction
        self.assertGreaterEqual(call_count, 2, "should have called LLM at least twice")
        second_call_input = captured_inputs[1] if len(captured_inputs) > 1 else ""
        self.assertIn(
            "first pass",
            second_call_input,
            "second compaction should include previous summary content",
        )
