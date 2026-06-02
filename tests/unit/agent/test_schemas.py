import unittest
from laffyhand.agent.llm.specs.models import AssistantMessage, SystemMessage, ToolMessage, UserMessage
from laffyhand.agent.llm.specs.models import (
    ToolCallContent,
    ToolDefinition,
    Usage,
)
from laffyhand.agent.schemas import (
    SessionID,
    SessionUsage,
    estimate_tokens,
    AgentState,
    CompactionConfig,
)


class TestEstimateTokens(unittest.TestCase):
    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens("hello"), 1)

    def test_estimate_tokens_empty(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_estimate_tokens_long(self):
        self.assertEqual(estimate_tokens("x" * 40), 10)


class TestMessages(unittest.TestCase):
    def test_system_message(self):
        msg = SystemMessage(content="system prompt")
        self.assertEqual(msg.role, "system")
        self.assertEqual(msg.content, "system prompt")

    def test_user_message(self):
        msg = UserMessage(content="hello")
        self.assertEqual(msg.role, "user")

    def test_assistant_message(self):
        msg = AssistantMessage(content="response", reasoning="thinking")
        self.assertEqual(msg.role, "assistant")
        self.assertEqual(msg.reasoning, "thinking")

    def test_tool_message(self):
        msg = ToolMessage(tool_call_id="call_1", content="result")
        self.assertEqual(msg.role, "tool")

    def test_assistant_with_tool_calls(self):
        tc = ToolCallContent(tool_call_id="c1", tool_name="test", args="{}")
        msg = AssistantMessage(content=None, tool_calls=[tc])
        self.assertEqual(len(msg.tool_calls), 1)
        self.assertEqual(msg.tool_calls[0].tool_name, "test")


class TestToolDefinition(unittest.TestCase):
    def test_tool_definition(self):
        td = ToolDefinition(name="test", description="a test tool", input_schema={})
        self.assertEqual(td.name, "test")
        self.assertEqual(td.description, "a test tool")
        self.assertEqual(td.input_schema, {})


class TestUsage(unittest.TestCase):
    def test_usage_defaults(self):
        u = Usage()
        self.assertIsNone(u.input_tokens)

    def test_session_usage_add(self):
        su = SessionUsage(context_size=100_000)
        u = Usage(input_tokens=10, output_tokens=20)
        su.add(u)
        self.assertEqual(su.total_input, 10)
        self.assertEqual(su.total_output, 20)


class TestCompactionConfig(unittest.TestCase):
    def test_defaults(self):
        c = CompactionConfig()
        self.assertEqual(c.tail_turns, 2)
        self.assertTrue(c.prune)
        self.assertTrue(c.auto_continue)

    def test_custom(self):
        c = CompactionConfig(tail_turns=5, prune=False, auto_continue=False)
        self.assertEqual(c.tail_turns, 5)
        self.assertFalse(c.prune)
        self.assertFalse(c.auto_continue)


class TestAgentState(unittest.TestCase):
    def test_defaults(self):
        state = AgentState(messages=[], session_id=SessionID("test"))
        self.assertEqual(state.turn_count, 0)
        self.assertEqual(state.step, 0)

    def test_increment_step(self):
        state = AgentState(messages=[], session_id=SessionID("test"))
        state.step += 1
        self.assertEqual(state.step, 1)
