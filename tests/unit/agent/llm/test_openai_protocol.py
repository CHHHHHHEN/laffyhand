import unittest
from laffyhand.agent.llm.specs.models import AssistantMessage, LLMRequest, SystemMessage, ToolMessage, UserMessage
from laffyhand.agent.schemas import (
    ToolCallContent,
    ToolDefinition,
    StreamText,
    StreamReasoning,
    StreamToolCall,
    StreamFinish,
)
from laffyhand.agent.llm.protocols.openai import (
    OpenAIProtocol,
    OpenAIEndpoint,
)
from laffyhand.agent.llm.protocols.deepseek import DeepseekProtocol


class TestMessageToOpenAI(unittest.TestCase):
    """OpenAIProtocol._message_to_openai must produce valid API messages even for edge cases."""

    def test_assistant_empty_content_adds_fallback(self):
        msg = AssistantMessage(content=None, tool_calls=None)
        result = OpenAIProtocol._message_to_openai(msg).model_dump()
        self.assertEqual(result["role"], "assistant")
        self.assertIn("content", result)
        self.assertEqual(result["content"], "[Empty response]")

    def test_assistant_empty_content_empty_tool_calls_adds_fallback(self):
        msg = AssistantMessage(content=None, tool_calls=[])
        result = OpenAIProtocol._message_to_openai(msg).model_dump()
        self.assertEqual(result["role"], "assistant")
        self.assertEqual(result["content"], "[Empty response]")

    def test_assistant_with_content_no_fallback(self):
        msg = AssistantMessage(content="Hello")
        result = OpenAIProtocol._message_to_openai(msg).model_dump()
        self.assertEqual(result["content"], "Hello")

    def test_assistant_with_tool_calls_no_fallback(self):
        tc = ToolCallContent(tool_call_id="c1", tool_name="test", args="{}")
        msg = AssistantMessage(content=None, tool_calls=[tc])
        result = OpenAIProtocol._message_to_openai(msg).model_dump()
        self.assertEqual(result["role"], "assistant")
        self.assertIsNone(result.get("content"))
        self.assertIn("tool_calls", result)

    def test_assistant_with_reasoning(self):
        msg = AssistantMessage(content="response", reasoning="thinking")
        result = OpenAIProtocol._message_to_openai(msg).model_dump()
        self.assertEqual(result["content"], "response")
        self.assertEqual(result["reasoning_content"], "thinking")

    def test_system_message_passthrough(self):
        msg = SystemMessage(content="system prompt")
        result = OpenAIProtocol._message_to_openai(msg).model_dump()
        self.assertEqual(result, {"role": "system", "content": "system prompt"})

    def test_user_message_passthrough(self):
        msg = UserMessage(content="user text")
        result = OpenAIProtocol._message_to_openai(msg).model_dump()
        self.assertEqual(result, {"role": "user", "content": "user text"})

    def test_tool_message_passthrough(self):
        msg = ToolMessage(tool_call_id="call_1", content="result")
        result = OpenAIProtocol._message_to_openai(msg).model_dump()
        self.assertEqual(
            result, {"role": "tool", "tool_call_id": "call_1", "content": "result"}
        )

    def test_unknown_role_returns_fallback(self):
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.role = "custom_role"
        result = OpenAIProtocol._message_to_openai(msg).model_dump()
        self.assertEqual(result, {"role": "user", "content": ""})


class TestOpenAIProtocolBuildRequest(unittest.TestCase):
    """OpenAIProtocol.build_request must always produce valid request bodies."""

    def test_strips_empty_assistant_before_sending(self):
        """build_request uses OpenAIProtocol._message_to_openai which adds fallback content."""
        protocol = OpenAIProtocol()
        messages = [
            SystemMessage(content="system"),
            UserMessage(content="hello"),
            AssistantMessage(content=None, tool_calls=None),
        ]
        tools = [ToolDefinition(name="test", description="desc", input_schema={})]
        request = LLMRequest(model="test-model", messages=messages, tools=tools)
        body = protocol.build_request(request).model_dump()
        self.assertEqual(len(body["messages"]), 3)
        self.assertEqual(body["messages"][2]["content"], "[Empty response]")

    def test_sets_stream_and_stream_options(self):
        protocol = OpenAIProtocol()
        request = LLMRequest(model="m", messages=[UserMessage(content="hi")])
        body = protocol.build_request(request).model_dump()
        self.assertTrue(body["stream"])
        self.assertEqual(body["stream_options"], {"include_usage": True})

    def test_no_tools_omits_tools_key(self):
        protocol = OpenAIProtocol()
        request = LLMRequest(model="m", messages=[UserMessage(content="hi")])
        body = protocol.build_request(request).model_dump()
        self.assertNotIn("tools", body)


class TestOpenAIProtocolParseFrame(unittest.TestCase):
    """OpenAIProtocol.parse_frame must correctly parse each frame type."""

    def setUp(self):
        self.protocol = OpenAIProtocol()

    def test_no_choices_returns_empty(self):
        events = self.protocol.parse_frame({"id": "x", "choices": []})
        self.assertEqual(events, [])

    def test_content_delta(self):
        events = self.protocol.parse_frame(
            {
                "choices": [
                    {"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}
                ],
            }
        )
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], StreamText)
        self.assertEqual(events[0].delta, "Hello")

    def test_reasoning_delta(self):
        events = self.protocol.parse_frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"reasoning_content": "thinking"},
                        "finish_reason": None,
                    }
                ],
            }
        )
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], StreamReasoning)
        self.assertEqual(events[0].delta, "thinking")

    def test_content_and_reasoning_together(self):
        events = self.protocol.parse_frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "answer", "reasoning_content": "thinking"},
                        "finish_reason": None,
                    }
                ],
            }
        )
        self.assertEqual(len(events), 2)
        self.assertIsInstance(events[0], StreamText)
        self.assertIsInstance(events[1], StreamReasoning)

    def test_tool_call_accumulation(self):
        events = self.protocol.parse_frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "tc1",
                                    "function": {
                                        "name": "bash",
                                        "arguments": '{"cmd":',
                                    },
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        )
        self.assertEqual(len(events), 0)  # accumulated, not yielded yet
        finish_events = self.protocol.parse_frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": ' "ls"}'}}
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
        )
        self.assertEqual(len(finish_events), 2)
        self.assertIsInstance(finish_events[0], StreamToolCall)
        self.assertEqual(finish_events[0].tool_call_id, "tc1")
        self.assertEqual(finish_events[0].tool_name, "bash")
        self.assertEqual(finish_events[0].args, '{"cmd": "ls"}')
        self.assertIsInstance(finish_events[1], StreamFinish)
        self.assertEqual(finish_events[1].finish_reason, "tool_calls")

    def test_tool_call_single_frame(self):
        """Tool call completed in one frame (single-shot)."""
        events = self.protocol.parse_frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "tc1",
                                    "function": {
                                        "name": "bash",
                                        "arguments": '{"cmd":"ls"}',
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
        )
        self.assertEqual(len(events), 2)
        self.assertIsInstance(events[0], StreamToolCall)
        self.assertEqual(events[0].tool_name, "bash")

    def test_finish_with_usage(self):
        events = self.protocol.parse_frame(
            {
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], StreamFinish)
        self.assertEqual(events[0].finish_reason, "stop")
        self.assertIsNotNone(events[0].usage)
        self.assertEqual(events[0].usage.input_tokens, 10)
        self.assertEqual(events[0].usage.output_tokens, 5)

    def test_finish_without_usage(self):
        events = self.protocol.parse_frame(
            {
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        )
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], StreamFinish)
        self.assertIsNone(events[0].usage)

    def test_unknown_finish_reason_mapped_to_other(self):
        events = self.protocol.parse_frame(
            {
                "choices": [{"index": 0, "delta": {}, "finish_reason": "rate_limit"}],
            }
        )
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], StreamFinish)
        self.assertEqual(events[0].finish_reason, "other")

    def test_usage_with_details(self):
        events = self.protocol.parse_frame(
            {
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "prompt_tokens_details": {
                        "cached_tokens": 10,
                        "cache_write_tokens": 5,
                    },
                    "completion_tokens_details": {"reasoning_tokens": 20},
                },
            }
        )
        u = events[0].usage
        self.assertEqual(u.input_tokens, 100)
        self.assertEqual(u.output_tokens, 50)
        self.assertEqual(u.reasoning_tokens, 20)
        self.assertEqual(u.cache_read_tokens, 10)
        self.assertEqual(u.cache_write_tokens, 5)


class TestDeepseekProtocol(unittest.TestCase):
    """DeepseekProtocol extends OpenAIProtocol with thinking extras."""

    def setUp(self):
        self.protocol = DeepseekProtocol()

    def test_build_request_adds_deepseek_extras(self):
        request = LLMRequest(
            model="deepseek-test", messages=[UserMessage(content="hi")]
        )
        body = self.protocol.build_request(request)
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertEqual(body["reasoning_effort"], "high")

    def test_parse_frame_reasoning_content(self):
        events = self.protocol.parse_frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"reasoning_content": "thinking step"},
                        "finish_reason": None,
                    }
                ],
            }
        )
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], StreamReasoning)
        self.assertEqual(events[0].delta, "thinking step")

    def test_parse_frame_reasoning_and_content(self):
        """DeepSeek emits both reasoning_content and content in separate frames."""
        reasoning_events = self.protocol.parse_frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"reasoning_content": "think..."},
                        "finish_reason": None,
                    }
                ],
            }
        )
        self.assertEqual(len(reasoning_events), 1)
        self.assertIsInstance(reasoning_events[0], StreamReasoning)

        content_events = self.protocol.parse_frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }
        )
        self.assertEqual(len(content_events), 2)
        self.assertIsInstance(content_events[0], StreamText)
        self.assertIsInstance(content_events[1], StreamFinish)

    def test_parse_frame_no_reasoning_falls_through_to_parent(self):
        """When no reasoning_content, DeepSeek falls through to standard OpenAI parsing."""
        events = self.protocol.parse_frame(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "plain answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }
        )
        self.assertEqual(len(events), 2)
        self.assertIsInstance(events[0], StreamText)
        self.assertIsInstance(events[1], StreamFinish)

    def test_tool_call_args_not_doubled(self):
        """Tool call arguments must not be doubled by DeepSeekProtocol's parse_frame."""
        start = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {"name": "bash", "arguments": ""},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        }
        chunk1 = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"arguments": '{"command":'}}
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        }
        chunk2 = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"arguments": ' "pwd"}'}}
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        }
        finish = {
            "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }

        self.protocol.parse_frame(start)
        self.protocol.parse_frame(chunk1)
        self.protocol.parse_frame(chunk2)
        events = self.protocol.parse_frame(finish)

        tool_calls = [e for e in events if isinstance(e, StreamToolCall)]
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].args, '{"command": "pwd"}')


class TestToolDefinitionsToOpenAI(unittest.TestCase):
    """OpenAIProtocol._tool_definitions_to_openai must produce valid OpenAI tool format."""

    def test_converts_single_tool(self):
        tools = [
            ToolDefinition(
                name="search",
                description="  Search the web  ",
                input_schema={"type": "object"},
            )
        ]
        result = OpenAIProtocol._tool_definitions_to_openai(tools)
        self.assertEqual(len(result), 1)
        d = result[0].model_dump()
        self.assertEqual(d["type"], "function")
        self.assertEqual(d["function"]["name"], "search")
        self.assertEqual(d["function"]["description"], "Search the web")
        self.assertEqual(d["function"]["parameters"], {"type": "object"})

    def test_converts_multiple_tools(self):
        tools = [
            ToolDefinition(name="a", description="desc a", input_schema={}),
            ToolDefinition(name="b", description="desc b", input_schema={}),
        ]
        result = OpenAIProtocol._tool_definitions_to_openai(tools)
        self.assertEqual(len(result), 2)


class TestOpenAIEndpoint(unittest.TestCase):
    """OpenAIEndpoint.build must produce correct URLs."""

    def test_build_url(self):
        endpoint = OpenAIEndpoint(base_url="https://api.openai.com")
        self.assertEqual(
            endpoint.build("gpt-4"), "https://api.openai.com/v1/chat/completions"
        )

    def test_strips_trailing_slash(self):
        endpoint = OpenAIEndpoint(base_url="https://api.openai.com/")
        self.assertEqual(
            endpoint.build("gpt-4"), "https://api.openai.com/v1/chat/completions"
        )

    def test_with_custom_base(self):
        endpoint = OpenAIEndpoint(base_url="http://localhost:8080")
        self.assertEqual(
            endpoint.build("test"), "http://localhost:8080/v1/chat/completions"
        )
