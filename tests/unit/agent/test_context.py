import unittest
from laffyhand.agent.schemas import (
    SystemMessage, UserMessage, AssistantMessage, ToolMessage,
    ToolCallContent, CompactionConfig,
)
from laffyhand.agent.context import (
    estimate_message_tokens, estimate_messages_tokens,
    is_overflow, select_tail, build_summary_text, prune,
    PRUNE_PROTECT,
)


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
        tc = ToolCallContent(tool_call_id="c1", tool_name="test_tool", args='{"key": "val"}')
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
        self.assertFalse(is_overflow(1000, 100_000))

    def test_overflow_detected(self):
        self.assertTrue(is_overflow(90_000, 100_000))

    def test_no_context_size(self):
        self.assertFalse(is_overflow(1000, 0))

    def test_small_buffer(self):
        self.assertTrue(is_overflow(25_000, 30_000, reserved=5_000))


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
        head, tail = select_tail(msgs, CompactionConfig(tail_turns=5), context_size=1000)
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


class TestBuildSummaryText(unittest.TestCase):
    def test_includes_all_types(self):
        msgs = [
            UserMessage(content="user hello"),
            AssistantMessage(
                content="asst hello",
                tool_calls=[ToolCallContent(tool_call_id="c1", tool_name="my_tool", args="{}")],
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
        self.assertEqual(result, 0)
        self.assertEqual(msgs[0].content, "small")

    def test_prune_large_tool_output(self):
        content = "x" * (PRUNE_PROTECT * 4 + 5)
        msgs = [ToolMessage(tool_call_id="c1", content=content)]
        result = prune(msgs)
        self.assertGreater(result, 0)
        self.assertTrue(msgs[0].content.startswith("[Tool output pruned:"))

    def test_prune_multiple_messages_oldest_first(self):
        small = ToolMessage(tool_call_id="c1", content="small")
        large = ToolMessage(tool_call_id="c2", content="x" * (PRUNE_PROTECT * 4 + 5))
        msgs = [small, large]
        result = prune(msgs)
        self.assertGreater(result, 0)
        self.assertEqual(msgs[0].content, "small", "should not prune tiny messages")
        self.assertTrue(msgs[1].content.startswith("[Tool output pruned:"))

    def test_prune_no_tool_messages(self):
        msgs = [SystemMessage(content="sys"), UserMessage(content="hi")]
        result = prune(msgs)
        self.assertEqual(result, 0)
