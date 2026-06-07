import asyncio
import unittest
from collections.abc import AsyncIterator

from laffyhand.core.llm.specs.models import AssistantMessage, SystemMessage, UserMessage
from laffyhand.core.llm.specs.models import Usage
from laffyhand.core.models import (
    AgentState,
    CompactionConfig,
    RetryConfig,
    SessionID,
    SessionUsage,
)
from laffyhand.core.loop import AgentTurn, TurnContext
from laffyhand.core.llm.facade import LLM
from laffyhand.core.tools.registry import ToolRegistry
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.permission import PermissionManager


class _MockLLM(LLM):
    """Mock LLM that yields a fixed sequence of events on every stream() call."""

    def __init__(self, events: list | None = None):
        self.model = "test"
        self.route = None
        self._events = events or []

    async def stream(self, messages, tools=None) -> AsyncIterator:
        for event in self._events:
            yield event


class _SeqMockLLM(LLM):
    """Mock LLM that returns different event sequences per call index."""

    def __init__(self, *event_lists: list):
        self.model = "test"
        self.route = None
        self._event_lists = event_lists
        self._call_count = 0

    async def stream(self, messages, tools=None) -> AsyncIterator:
        events = self._event_lists[self._call_count]
        self._call_count += 1
        for event in events:
            yield event


class _NoopTool(BaseTool):
    name = "noop"
    description = "Does nothing"

    async def run(self, params: dict) -> str:
        return "ok"


_FAST_RETRY = RetryConfig(max_retries=1, base_delay=0.01)
_ZERO_RETRY = RetryConfig(max_retries=0)


class TestAgentLoopAssistantMessage(unittest.TestCase):
    """AgentTurn.run() must always produce valid AssistantMessage with content or tool_calls."""

    def setUp(self):
        self.tool_registry = ToolRegistry(PermissionManager())
        self.tool_registry.register_tool(_NoopTool())

    def _run_loop(self, llm_events: list, user_text: str = "hello",
                  retry_config: RetryConfig = _FAST_RETRY,
                  max_steps: int = 1):
        """Run AgentTurn with given LLM events and return state.messages + events."""
        llm = _MockLLM(llm_events)
        state = AgentState(
            messages=[
                SystemMessage(content="You are a test assistant."),
                UserMessage(content=user_text),
            ],
            session_id=SessionID("test"),
            usage=SessionUsage(context_size=100_000),
        )

        events = []

        async def _collect():
            nonlocal events
            async for event in AgentTurn(
                state,
                llm,
                self.tool_registry,
                compaction_config=CompactionConfig(
                    tail_turns=1,
                    auto_continue=False,
                    prune=False,
                ),
                retry_config=retry_config,
                max_steps=max_steps,
            ).run():
                events.append(event)
            return state

        result = asyncio.run(_collect())

        assistant_msgs = [m for m in result.messages if isinstance(m, AssistantMessage)]
        return assistant_msgs, events

    def test_error_finish_sets_content(self):
        """When finish_reason is 'error' and no content generated, content should be set to error text."""
        from laffyhand.core.llm.specs.models import StreamError, StreamFinish

        msgs, events = self._run_loop(
            [
                StreamError(error="API connection failed"),
                StreamFinish(
                    finish_reason="error", usage=Usage(input_tokens=10, output_tokens=0)
                ),
            ]
        )
        self.assertEqual(len(msgs), 1, "expected one AssistantMessage")
        asst = msgs[0]
        self.assertIsNotNone(
            asst.content, "AssistantMessage must have content even after error"
        )
        self.assertIn("Error", asst.content)
        self.assertIsNone(asst.tool_calls)

    def test_empty_response_sets_content(self):
        """When LLM returns stop with no content, content should be set to empty placeholder."""
        from laffyhand.core.llm.specs.models import StreamFinish

        msgs, events = self._run_loop(
            [
                StreamFinish(
                    finish_reason="stop", usage=Usage(input_tokens=10, output_tokens=0)
                ),
            ]
        )
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertIsNotNone(
            asst.content, "AssistantMessage must have content even with empty response"
        )
        self.assertEqual(asst.content, "[Empty response]")

    def test_content_with_tool_calls_unchanged(self):
        """When tool_calls are present, content should be None (no fallback needed)."""
        from laffyhand.core.llm.specs.models import StreamToolCall, StreamFinish

        msgs, events = self._run_loop(
            [
                StreamToolCall(tool_call_id="c1", tool_name="noop", args="{}"),
                StreamFinish(
                    finish_reason="tool_calls",
                    usage=Usage(input_tokens=10, output_tokens=5),
                ),
            ]
        )
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertIsNone(
            asst.content, "AssistantMessage with tool_calls should have content=None"
        )
        self.assertEqual(len(asst.tool_calls), 1)
        self.assertEqual(asst.tool_calls[0].tool_name, "noop")

    def test_text_content_preserved(self):
        """Normal text response should remain unchanged."""
        from laffyhand.core.llm.specs.models import StreamText, StreamFinish

        msgs, events = self._run_loop(
            [
                StreamText(delta="Hello, I'm a test assistant."),
                StreamFinish(
                    finish_reason="stop", usage=Usage(input_tokens=10, output_tokens=5)
                ),
            ]
        )
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertEqual(asst.content, "Hello, I'm a test assistant.")

    def test_error_retry_exhausted(self):
        """After max_retries exhausted, error message is committed."""
        from laffyhand.core.llm.specs.models import StreamError, StreamFinish

        msgs, events = self._run_loop(
            [
                StreamError(error="persistent failure"),
                StreamFinish(finish_reason="error", usage=Usage(input_tokens=5, output_tokens=0)),
            ],
            retry_config=_FAST_RETRY,
        )
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertIn("Error", asst.content)
        self.assertIsNone(asst.tool_calls)

    def test_error_retry_succeeds(self):
        """If retry succeeds, use content from the successful attempt."""
        from laffyhand.core.llm.specs.models import StreamError, StreamFinish, StreamText

        llm = _SeqMockLLM(
            [StreamError(error="transient"), StreamFinish(finish_reason="error", usage=Usage(input_tokens=5, output_tokens=0))],
            [StreamText(delta="Recovered response."), StreamFinish(finish_reason="stop", usage=Usage(input_tokens=10, output_tokens=20))],
        )
        state = AgentState(
            messages=[
                SystemMessage(content="You are a test assistant."),
                UserMessage(content="hello"),
            ],
            session_id=SessionID("test"),
            usage=SessionUsage(context_size=100_000),
        )
        events = []
        async def _collect():
            nonlocal events
            async for event in AgentTurn(
                state, llm, self.tool_registry,
                compaction_config=CompactionConfig(tail_turns=1, auto_continue=False, prune=False),
                retry_config=_FAST_RETRY, max_steps=1,
            ).run():
                events.append(event)
            return state
        result = asyncio.run(_collect())
        msgs = [m for m in result.messages if isinstance(m, AssistantMessage)]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].content, "Recovered response.")

    def test_error_partial_content_no_retry(self):
        """When partial text was already streamed, do NOT retry — commit error."""
        from laffyhand.core.llm.specs.models import StreamError, StreamFinish, StreamText

        msgs, events = self._run_loop(
            [
                StreamText(delta="Partial text "),
                StreamError(error="mid-stream failure"),
                StreamFinish(finish_reason="error", usage=Usage(input_tokens=10, output_tokens=5)),
            ],
            retry_config=RetryConfig(max_retries=3, base_delay=60.0),
        )
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertEqual(asst.content, "Partial text ")
        self.assertIsNone(asst.tool_calls)

    def test_error_retry_zero_no_retry(self):
        """max_retries=0 means no retry, immediate error commit."""
        from laffyhand.core.llm.specs.models import StreamError, StreamFinish

        msgs, events = self._run_loop(
            [
                StreamError(error="no retry"),
                StreamFinish(finish_reason="error", usage=Usage(input_tokens=5, output_tokens=0)),
            ],
            retry_config=_ZERO_RETRY,
        )
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertIn("Error", asst.content)

    def test_error_with_tool_calls_no_retry(self):
        """When tool_calls were issued before error, do NOT retry — commit error."""
        from laffyhand.core.llm.specs.models import StreamError, StreamFinish, StreamToolCall

        msgs, events = self._run_loop(
            [
                StreamToolCall(tool_call_id="c1", tool_name="noop", args="{}"),
                StreamError(error="post-toolcall crash"),
                StreamFinish(finish_reason="error", usage=Usage(input_tokens=10, output_tokens=5)),
            ],
            retry_config=RetryConfig(max_retries=3, base_delay=60.0),
        )
        self.assertEqual(len(msgs), 1)
        asst = msgs[0]
        self.assertIsNone(asst.content)
        self.assertEqual(len(asst.tool_calls), 1)

    def test_non_error_no_retry(self):
        """finish_reason=stop does NOT trigger retry."""
        from laffyhand.core.llm.specs.models import StreamFinish

        msgs, events = self._run_loop(
            [StreamFinish(finish_reason="stop", usage=Usage(input_tokens=10, output_tokens=0))],
            retry_config=RetryConfig(max_retries=3, base_delay=60.0),
        )
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].content, "[Empty response]")


class TestAgentTurn(unittest.TestCase):
    """AgentTurn class can be used directly as a drop-in for agent_loop()."""

    def setUp(self):
        self.tool_registry = ToolRegistry(PermissionManager())
        self.tool_registry.register_tool(_NoopTool())

    def _run_turn(self, llm_events: list, user_text: str = "hello",
                  retry_config: RetryConfig = _FAST_RETRY,
                  max_steps: int = 1):
        llm = _MockLLM(llm_events)
        state = AgentState(
            messages=[
                SystemMessage(content="You are a test assistant."),
                UserMessage(content=user_text),
            ],
            session_id=SessionID("test"),
            usage=SessionUsage(context_size=100_000),
        )
        events = []

        async def _collect():
            nonlocal events
            turn = AgentTurn(
                state,
                llm,
                self.tool_registry,
                compaction_config=CompactionConfig(
                    tail_turns=1,
                    auto_continue=False,
                    prune=False,
                ),
                retry_config=retry_config,
                max_steps=max_steps,
            )
            async for event in turn.run():
                events.append(event)
            return state

        result = asyncio.run(_collect())
        assistant_msgs = [m for m in result.messages if isinstance(m, AssistantMessage)]
        return assistant_msgs, events

    def test_agent_turn_text_response(self):
        from laffyhand.core.llm.specs.models import StreamText, StreamFinish

        msgs, events = self._run_turn([
            StreamText(delta="Hello from AgentTurn."),
            StreamFinish(finish_reason="stop", usage=Usage(input_tokens=10, output_tokens=5)),
        ])
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].content, "Hello from AgentTurn.")
        self.assertIn("StepStart", [type(e).__name__ for e in events])

    def test_agent_turn_tool_calls(self):
        from laffyhand.core.llm.specs.models import StreamToolCall, StreamFinish

        msgs, events = self._run_turn([
            StreamToolCall(tool_call_id="c1", tool_name="noop", args="{}"),
            StreamFinish(finish_reason="tool_calls", usage=Usage(input_tokens=10, output_tokens=5)),
        ])
        self.assertEqual(len(msgs), 1)
        self.assertIsNone(msgs[0].content)
        self.assertEqual(len(msgs[0].tool_calls), 1)
        self.assertEqual(msgs[0].tool_calls[0].tool_name, "noop")

    def test_agent_turn_error_finish(self):
        from laffyhand.core.llm.specs.models import StreamError, StreamFinish

        msgs, events = self._run_turn([
            StreamError(error="API failure"),
            StreamFinish(finish_reason="error", usage=Usage(input_tokens=10, output_tokens=0)),
        ])
        self.assertEqual(len(msgs), 1)
        self.assertIn("Error", msgs[0].content)

    def test_agent_turn_turn_context_direct_usage(self):
        ctx = TurnContext(
            content_buf=["hello"],
            reasoning_buf=["thinking"],
            finish_reason="stop",
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        self.assertEqual("".join(ctx.content_buf), "hello")
        self.assertEqual(ctx.finish_reason, "stop")
        self.assertIsNotNone(ctx.usage)

    def test_agent_turn_empty_fields(self):
        ctx = TurnContext()
        self.assertEqual(ctx.content_buf, [])
        self.assertEqual(ctx.reasoning_buf, [])
        self.assertEqual(ctx.tool_calls, [])
        self.assertIsNone(ctx.finish_reason)
        self.assertIsNone(ctx.usage)
