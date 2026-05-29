import unittest
from laffyhand.agent.schemas import (
    AssistantMessage, SystemMessage, UserMessage, ToolMessage,
    ToolCallContent, LLMRequest, ToolDefinition,
)
from laffyhand.agent.llm.protocols.openai import (
    OpenAIProtocol, _message_to_openai,
)


class TestMessageToOpenAI(unittest.TestCase):
    """_message_to_openai must produce valid API messages even for edge cases."""

    def test_assistant_empty_content_adds_fallback(self):
        """An AssistantMessage with no content and no tool_calls gets a fallback."""
        msg = AssistantMessage(content=None, tool_calls=None)
        result = _message_to_openai(msg)
        self.assertEqual(result["role"], "assistant")
        self.assertIn("content", result)
        self.assertEqual(result["content"], "[Empty response]")

    def test_assistant_with_content_no_fallback(self):
        """An AssistantMessage with content uses it directly."""
        msg = AssistantMessage(content="Hello")
        result = _message_to_openai(msg)
        self.assertEqual(result["content"], "Hello")

    def test_assistant_with_tool_calls_no_fallback(self):
        """An AssistantMessage with tool_calls does not need a fallback."""
        tc = ToolCallContent(tool_call_id="c1", tool_name="test", args="{}")
        msg = AssistantMessage(content=None, tool_calls=[tc])
        result = _message_to_openai(msg)
        self.assertEqual(result["role"], "assistant")
        self.assertNotIn("content", result)
        self.assertIn("tool_calls", result)

    def test_assistant_with_reasoning(self):
        """reasoning_content is included in the output."""
        msg = AssistantMessage(content="response", reasoning="thinking")
        result = _message_to_openai(msg)
        self.assertEqual(result["content"], "response")
        self.assertEqual(result["reasoning_content"], "thinking")

    def test_system_message_passthrough(self):
        msg = SystemMessage(content="system prompt")
        result = _message_to_openai(msg)
        self.assertEqual(result, {"role": "system", "content": "system prompt"})

    def test_user_message_passthrough(self):
        msg = UserMessage(content="user text")
        result = _message_to_openai(msg)
        self.assertEqual(result, {"role": "user", "content": "user text"})

    def test_tool_message_passthrough(self):
        msg = ToolMessage(tool_call_id="call_1", content="result")
        result = _message_to_openai(msg)
        self.assertEqual(result, {"role": "tool", "tool_call_id": "call_1", "content": "result"})


class TestOpenAIProtocolBuildRequest(unittest.TestCase):
    """OpenAIProtocol.build_request must always produce valid request bodies."""

    def test_strips_empty_assistant_before_sending(self):
        """build_request uses _message_to_openai which adds fallback content."""
        protocol = OpenAIProtocol()
        messages = [
            SystemMessage(content="system"),
            UserMessage(content="hello"),
            AssistantMessage(content=None, tool_calls=None),
        ]
        tools = [ToolDefinition(name="test", description="desc", input_schema={})]
        request = LLMRequest(model="test-model", messages=messages, tools=tools)
        body = protocol.build_request(request)
        self.assertEqual(len(body["messages"]), 3)
        self.assertEqual(body["messages"][2]["content"], "[Empty response]")
