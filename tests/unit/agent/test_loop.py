import unittest
from collections.abc import AsyncIterator

from laffyhand.agent.schemas import (
    AgentState, AssistantMessage, CompactionConfig, SessionUsage, SystemMessage, UserMessage,
    Usage,
)
from laffyhand.agent.loop import agent_loop
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.tools.registry import ToolRegistry
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.permission import PermissionManager


class _MockLLM(LLM):
    """A mock LLM that yields a fixed sequence of events."""

    def __init__(self, events: list | None = None):
        self.model = "test"
        self.route = None  # type: ignore[assignment]
        self._events = events or []

    async def stream(self, messages, tools=None) -> AsyncIterator:
        for event in self._events:
            yield event


class _NoopTool(BaseTool):
    name = "noop"
    description = "Does nothing"

    async def run(self, params: dict) -> str:
        return "ok"


class TestAgentLoopAssistantMessage(unittest.TestCase):
    """agent_loop must always produce valid AssistantMessage with content or tool_calls."""

    def setUp(self):
        self.tool_registry = ToolRegistry(PermissionManager())
        self.tool_registry.register_tool(_NoopTool())

    def _run_loop(self, llm_events: list, user_text: str = "hello"):
        """Run agent_loop with given LLM events and return the final state.messages."""
        llm = _MockLLM(llm_events)
        state = AgentState(
            messages=[
                SystemMessage(content="You are a test assistant."),
                UserMessage(content=user_text),
            ],
            usage=SessionUsage(context_size=100_000),
        )

        events = []

        async def _collect():
            nonlocal events
            async for event in agent_loop(
                state, llm, self.tool_registry,
                compaction_config=CompactionConfig(
                    tail_turns=1, auto_continue=False, prune=False,
                ),
                max_steps=1,
            ):
                events.append(event)
            return state

        import asyncio
        result = asyncio.run(_collect())

        # Find the assistant message
        assistant_msgs = [m for m in result.messages if isinstance(m, AssistantMessage)]
        return assistant_msgs, events

    def test_error_finish_sets_content(self):
        """When finish_reason is 'error' and no content generated, content should be set to error text."""
        from laffyhand.agent.schemas import StreamError, StreamFinish
        msgs, events = self._run_loop([
            StreamError(error="API connection failed"),
            StreamFinish(finish_reason="error", usage=Usage(input_tokens=10, output_tokens=0)),
        ])
        self.assertEqual(len(msgs), 1, "expected one AssistantMessage")
        asst = msgs[0]
        self.assertIsNotNone(asst.content, "AssistantMessage must have content even after error")
        self.assertIn("Error", asst.content)
        self.assertIsNone(asst.tool_calls)

    def test_empty_response_sets_content(self):
        """When LLM returns stop with no content, content should be set to empty placeholder."""
        from laffyhand.agent.schemas import StreamFinish
        msgs, events = self._run_loop([
            StreamFinish(finish_reason="stop", usage=Usage(input_tokens=10, output_tokens=0)),
        ])
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertIsNotNone(asst.content, "AssistantMessage must have content even with empty response")
        # The placeholder for empty response when there's no reasoning
        self.assertEqual(asst.content, "[Empty response]")

    def test_content_with_tool_calls_unchanged(self):
        """When tool_calls are present, content should be None (no fallback needed)."""
        from laffyhand.agent.schemas import StreamToolCall, StreamFinish
        msgs, events = self._run_loop([
            StreamToolCall(tool_call_id="c1", tool_name="noop", args="{}"),
            StreamFinish(finish_reason="tool_calls", usage=Usage(input_tokens=10, output_tokens=5)),
        ])
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertIsNone(asst.content, "AssistantMessage with tool_calls should have content=None")
        self.assertEqual(len(asst.tool_calls), 1)
        self.assertEqual(asst.tool_calls[0].tool_name, "noop")

    def test_text_content_preserved(self):
        """Normal text response should remain unchanged."""
        from laffyhand.agent.schemas import StreamText, StreamFinish
        msgs, events = self._run_loop([
            StreamText(delta="Hello, I'm a test assistant."),
            StreamFinish(finish_reason="stop", usage=Usage(input_tokens=10, output_tokens=5)),
        ])
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertEqual(asst.content, "Hello, I'm a test assistant.")
