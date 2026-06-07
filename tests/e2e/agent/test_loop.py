import asyncio
import unittest

from laffyhand.core.llm.specs.models import SystemMessage, ToolMessage
from laffyhand.core.llm.specs.models import (
    Usage,
    StreamText,
    StreamToolCall,
    StreamFinish,
)
from laffyhand.core.models import (
    AgentState,
    CompactionConfig,
    SessionID,
    SessionUsage,
)

from laffyhand.core.loop import AgentTurn
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo back input"
    max_result_size = 1000

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def run(self, params: dict) -> str:
        return params.get("text", "")


class FakeLLM:
    """Simulates LLM.stream() with pre-defined event sequences."""

    def __init__(self, event_sequences: list[list]):
        self._sequences = event_sequences
        self._call_count = 0

    async def stream(self, messages, tools=None):
        if self._call_count >= len(self._sequences):
            return
        events = self._sequences[self._call_count]
        self._call_count += 1
        for event in events:
            yield event


class TestAgentLoopE2E(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register_tool(EchoTool())

    def _make_state(self, context_size=100_000) -> AgentState:
        return AgentState(
            messages=[SystemMessage(content="You are a helpful assistant.")],
            session_id=SessionID("test"),
            usage=SessionUsage(context_size=context_size),
        )

    def _collect(self, gen):
        async def _run():
            return [e async for e in gen]

        return asyncio.run(_run())

    def test_simple_text_response(self):
        """LLM responds with text and finishes -> loop exits after one turn."""
        llm = FakeLLM(
            [
                [
                    StreamText(delta="hello "),
                    StreamText(delta="world"),
                    StreamFinish(
                        finish_reason="stop",
                        usage=Usage(input_tokens=10, output_tokens=5),
                    ),
                ],
            ]
        )
        state = self._make_state()
        events = self._collect(
            AgentTurn(state, llm, self.registry, CompactionConfig(prune=False)).run()
        )
        self.assertEqual(state.step, 1)
        self.assertEqual(state.turn_count, 1)
        self.assertGreater(len(events), 0)
        self.assertIn("hello", "".join(e.text for e in events if hasattr(e, "text")))
        self.assertTrue(any(e.type == "text-delta" for e in events))

    def test_tool_call_then_finish(self):
        """LLM calls tool, tool executes, then LLM finishes -> 2 steps."""
        llm = FakeLLM(
            [
                [
                    StreamToolCall(
                        tool_call_id="call_1", tool_name="echo", args='{"text": "hi"}'
                    ),
                    StreamFinish(
                        finish_reason="tool_calls",
                        usage=Usage(input_tokens=10, output_tokens=5),
                    ),
                ],
                [
                    StreamText(delta="done"),
                    StreamFinish(
                        finish_reason="stop",
                        usage=Usage(input_tokens=15, output_tokens=3),
                    ),
                ],
            ]
        )
        state = self._make_state()
        events = self._collect(
            AgentTurn(state, llm, self.registry, CompactionConfig(prune=False)).run()
        )
        self.assertEqual(state.step, 2)
        self.assertEqual(state.turn_count, 2)
        types = [e.type for e in events]
        self.assertIn("tool-call", types)
        self.assertIn("tool-result", types)

    def test_max_steps_limits_iterations(self):
        """LLM keeps calling tools -> stops after max_steps."""
        tool_event = [
            StreamToolCall(
                tool_call_id="call_1", tool_name="echo", args='{"text": "x"}'
            ),
            StreamFinish(
                finish_reason="tool_calls",
                usage=Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        llm = FakeLLM([tool_event, tool_event, tool_event])
        state = self._make_state()
        self._collect(
            AgentTurn(
                state, llm, self.registry, CompactionConfig(prune=False), max_steps=2
            ).run()
        )
        self.assertEqual(state.step, 3)
        self.assertEqual(state.turn_count, 2)

    def test_increments_step_and_turn_count(self):
        """Step and turn_count both increment correctly."""
        llm = FakeLLM(
            [
                [
                    StreamFinish(
                        finish_reason="stop",
                        usage=Usage(input_tokens=5, output_tokens=5),
                    )
                ],
            ]
        )
        state = self._make_state()
        self.assertEqual(state.step, 0)
        self.assertEqual(state.turn_count, 0)
        self._collect(
            AgentTurn(state, llm, self.registry, CompactionConfig(prune=False)).run()
        )
        self.assertEqual(state.step, 1)
        self.assertEqual(state.turn_count, 1)

    def test_tool_execution_appends_messages(self):
        """After tool call, ToolMessage is appended to state."""
        llm = FakeLLM(
            [
                [
                    StreamToolCall(
                        tool_call_id="call_1",
                        tool_name="echo",
                        args='{"text": "hello"}',
                    ),
                    StreamFinish(
                        finish_reason="tool_calls",
                        usage=Usage(input_tokens=10, output_tokens=5),
                    ),
                ],
                [
                    StreamText(delta="done"),
                    StreamFinish(
                        finish_reason="stop",
                        usage=Usage(input_tokens=15, output_tokens=3),
                    ),
                ],
            ]
        )
        state = self._make_state()
        self._collect(
            AgentTurn(state, llm, self.registry, CompactionConfig(prune=False)).run()
        )
        tool_msgs = [m for m in state.messages if isinstance(m, ToolMessage)]
        self.assertEqual(len(tool_msgs), 1)
        self.assertEqual(tool_msgs[0].tool_call_id, "call_1")
        self.assertEqual(tool_msgs[0].content, "hello")
