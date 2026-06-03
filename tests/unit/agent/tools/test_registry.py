import asyncio
import unittest

from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo back input"
    max_result_size = 100

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def run(self, params: dict) -> str:
        return params.get("text", "")


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register_tool(EchoTool())

    def test_register_and_definitions(self):
        defs = asyncio.run(self.registry.build_tool_definitions())
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0].name, "echo")
        self.assertEqual(defs[0].description, "Echo back input")
        self.assertIn("text", str(defs[0].input_schema))

    def test_run_tool(self):
        result = asyncio.run(self.registry.run_tool("echo", {"text": "hello"}))
        self.assertEqual(result, "hello")

    def test_build_tool_prompt(self):
        prompt = self.registry.build_tool_prompt()
        self.assertIn("echo", prompt)
        self.assertIn("Echo back input", prompt)

    def test_unregister(self):
        self.registry.unregister_tool("echo")
        self.assertEqual(len(asyncio.run(self.registry.build_tool_definitions())), 0)

    def test_cache_invalidated_on_register(self):
        defs1 = asyncio.run(self.registry.build_tool_definitions())
        self.registry.register_tool(EchoTool())
        defs2 = asyncio.run(self.registry.build_tool_definitions())
        self.assertIsNot(defs1, defs2)

    def test_run_unknown_tool_returns_error_message(self):
        result = asyncio.run(self.registry.run_tool("nonexistent", {}))
        self.assertIn("not registered", result)

    def test_run_unregistered_tool_after_unregister(self):
        self.registry.unregister_tool("echo")
        result = asyncio.run(self.registry.run_tool("echo", {}))
        self.assertIn("not registered", result)

    def test_build_tool_definitions_exclude(self):
        self.registry.register_tool(EchoTool())
        defs = asyncio.run(self.registry.build_tool_definitions(exclude={"echo"}))
        self.assertEqual(len(defs), 0)

    def test_build_tool_definitions_exclude_partial(self):
        class OtherTool(BaseTool):
            name = "other"
            description = "Other tool"
            def _input_schema(self) -> dict:
                return {"type": "object", "properties": {}}
            async def run(self, params: dict) -> str:
                return "ok"

        self.registry.register_tool(OtherTool())
        defs = asyncio.run(self.registry.build_tool_definitions(exclude={"echo"}))
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0].name, "other")

    def test_build_tool_definitions_exclude_none(self):
        defs = asyncio.run(self.registry.build_tool_definitions(exclude=None))
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0].name, "echo")

    def test_build_tool_prompt_exclude(self):
        prompt = self.registry.build_tool_prompt(exclude={"echo"})
        self.assertNotIn("echo", prompt)

    def test_build_tool_prompt_exclude_none(self):
        prompt = self.registry.build_tool_prompt(exclude=None)
        self.assertIn("echo", prompt)
