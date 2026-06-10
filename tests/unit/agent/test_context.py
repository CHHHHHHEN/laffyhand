from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import pytest
from laffyhand.core.context import ContextManager
from laffyhand.core.context._prune import prune
from laffyhand.core.context._summarize import (
    _is_summary_content,
    build_summary_text,
)
from laffyhand.core.context.chain import (
    _select_compaction_targets,
    compact_with_chain,
    is_overflow,
    select_tail,
)
from laffyhand.core.llm.specs.models import (
    AssistantMessage,
    StreamError,
    StreamFinish,
    StreamText,
    SystemMessage,
    ToolCallContent,
    ToolMessage,
    UserMessage,
)
from laffyhand.core.models import (
    AgentState,
    CompactionConfig,
    SessionID,
    SessionUsage,
)
from laffyhand.core._utils import (
    estimate_message_tokens,
    estimate_messages_tokens,
)


PRUNE_PROTECT = CompactionConfig().prune_protect


def _apply_compact_result(state: AgentState, result: tuple) -> bool:
    original_system, summary_messages, tail = result
    state.messages = original_system + summary_messages + tail
    return True


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
        msgs = [
            SystemMessage(content="sys"),
            ToolMessage(tool_call_id="c1", content="x" * 10_000),
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

    def test_handles_assistant_summary_content(self):
        msgs = [
            AssistantMessage(content="<summary>\nGoal: test\n</summary>"),
            UserMessage(content="New message"),
        ]
        text = build_summary_text(msgs)
        self.assertIn("[Previous Summary]", text)
        self.assertIn("Goal: test", text)


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
        self.assertLessEqual(pruned_count, 2)

    def test_prune_distance_based_protects_recent(self):
        window_chars = PRUNE_PROTECT * 4  # chars to fill the 40K token window
        near = ToolMessage(tool_call_id="c_near", content="x" * 100)
        middle = ToolMessage(tool_call_id="c_mid", content="y" * (window_chars // 2))
        far = ToolMessage(tool_call_id="c_far", content="z" * (window_chars // 2))
        msgs = [far, middle, near]
        result = prune(msgs)
        self.assertTrue(
            result[0].content.startswith("[Old tool result content cleared:"),
            "far tool outside 40K window should be pruned",
        )
        self.assertEqual(
            result[2].content, "x" * 100,
            "recent tool inside 40K window should be kept",
        )


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
        _apply_compact_result(state, result)
        self.assertLess(len(state.messages), len(msgs))
        summary_msgs = [
            m
            for m in state.messages
            if isinstance(m, (AssistantMessage, UserMessage))
            and m.content
            and _is_summary_content(m.content)
        ]
        self.assertEqual(
            len(summary_msgs), 1, "should have exactly one summary message"
        )
        self._check_compaction_format(state)

    def _check_compaction_format(self, state: AgentState) -> None:
        has_compaction_user = False
        has_summary_assistant = False
        for m in state.messages:
            if isinstance(m, UserMessage) and "What did we do" in (m.content or ""):
                has_compaction_user = True
            if isinstance(m, AssistantMessage) and m.content and _is_summary_content(m.content):
                has_summary_assistant = True
        self.assertTrue(has_compaction_user, "should have compaction-user message")
        self.assertTrue(has_summary_assistant, "should have summary assistant message")


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
        original_system, summary_messages, tail = result
        self.assertIsInstance(summary_messages, list)
        self.assertEqual(len(summary_messages), 2)
        self.assertIsInstance(summary_messages[0], UserMessage)
        self.assertIn("What did we do", summary_messages[0].content or "")
        self.assertIsInstance(summary_messages[1], AssistantMessage)
        summary_content = summary_messages[1].content or ""
        self.assertTrue(
            _is_summary_content(summary_content), "summary should be wrapped in <summary> tags"
        )
        self.assertIsInstance(original_system, list)
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
            SystemMessage(content="You are a bot."),
            SystemMessage(
                content="<summary>\nGoal: fix\n</summary>"
            ),
            UserMessage(content="user1"),
            AssistantMessage(content="asst1"),
            UserMessage(content="user2"),
            AssistantMessage(content="asst2"),
        ]
        config = CompactionConfig(tail_turns=1, preserve_recent_tokens=2)
        result = _select_compaction_targets(msgs, config, context_size=100_000)
        self.assertIsNotNone(result)
        head_to_summarize, original_system, tail = result
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
            _apply_compact_result(state, result)
            return True

        result1 = await _apply_compact(state)
        self.assertTrue(result1)

        for i in range(10, 15):
            state.messages.append(UserMessage(content=f"user {i}"))
            state.messages.append(AssistantMessage(content=f"asst {i}"))

        result2 = await _apply_compact(state)
        self.assertTrue(result2)

        self.assertGreaterEqual(call_count, 2, "should have called LLM at least twice")
        second_call_input = captured_inputs[1] if len(captured_inputs) > 1 else ""
        self.assertIn(
            "first pass",
            second_call_input,
            "second compaction should include previous summary content",
        )


class TestWrapSteer(unittest.TestCase):
    def test_no_wrap_when_step_one(self):
        msgs = [UserMessage(content="hello")]
        result = ContextManager._wrap_steer(msgs, step=1)
        self.assertEqual(result[0].content, "hello")

    def test_no_wrap_when_no_assistant(self):
        msgs = [UserMessage(content="hello"), UserMessage(content="world")]
        result = ContextManager._wrap_steer(msgs, step=2)
        self.assertEqual(result, msgs)

    def test_wraps_user_messages_after_last_assistant(self):
        msgs = [
            UserMessage(content="first"),
            AssistantMessage(content="response"),
            UserMessage(content="second"),
            UserMessage(content="third"),
        ]
        result = ContextManager._wrap_steer(msgs, step=2)
        self.assertEqual(result[0].content, "first")
        self.assertEqual(result[1].content, "response")
        self.assertIn("<system-reminder>", result[2].content)
        self.assertIn("second", result[2].content)
        self.assertIn("</system-reminder>", result[2].content)
        self.assertIn("<system-reminder>", result[3].content)
        self.assertIn("third", result[3].content)

    def test_preserves_tool_messages(self):
        msgs = [
            AssistantMessage(content="response"),
            ToolMessage(tool_call_id="c1", content="tool result"),
            UserMessage(content="follow-up"),
        ]
        result = ContextManager._wrap_steer(msgs, step=2)
        self.assertIsInstance(result[1], ToolMessage)
        self.assertEqual(result[1].content, "tool result")
        self.assertIn("<system-reminder>", result[2].content)

    def test_identity_when_no_modifications(self):
        msgs = [UserMessage(content="hello")]
        result = ContextManager._wrap_steer(msgs, step=2)
        self.assertIs(result, msgs, "no changes -> return same list")


class TestContextManagerPrepareSteer(unittest.TestCase):
    @pytest.mark.anyio
    async def test_prepare_applies_steer_wrapping(self):
        llm = MagicMock()
        cm = ContextManager(llm=llm, config=CompactionConfig())
        msgs = [
            UserMessage(content="initial"),
            AssistantMessage(content="ok"),
            UserMessage(content="steer me"),
        ]
        state = AgentState(
            messages=msgs,
            session_id=SessionID("sess-1"),
            usage=SessionUsage(context_size=100_000, curr_context_usage=10_000),
        )
        state.step = 2
        ctx = await cm.prepare(state)
        self.assertIn("<system-reminder>", ctx.messages[2].content)

    @pytest.mark.anyio
    async def test_prepare_skips_steer_on_step_one(self):
        llm = MagicMock()
        cm = ContextManager(llm=llm, config=CompactionConfig())
        msgs = [
            UserMessage(content="initial"),
            AssistantMessage(content="ok"),
            UserMessage(content="steer me"),
        ]
        state = AgentState(
            messages=msgs,
            session_id=SessionID("sess-1"),
            usage=SessionUsage(context_size=100_000, curr_context_usage=10_000),
        )
        state.step = 1
        ctx = await cm.prepare(state)
        self.assertNotIn("<system-reminder>", ctx.messages[2].content)
