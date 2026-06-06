import asyncio
import unittest

from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.registry import ToolRegistry


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


class SlowTool(BaseTool):
    """Tool with no timeout that simulates a long operation."""
    name = "slow"
    description = "Slow tool with no timeout"
    timeout = 0
    max_result_size = 100

    def _input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    async def run(self, params: dict) -> str:
        await asyncio.sleep(0.2)
        return "slow-result"


class TestToolTimeoutZero(unittest.TestCase):
    """run_tool should not wrap tools with timeout=0 in asyncio.wait_for."""

    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register_tool(SlowTool())

    def test_slow_tool_with_timeout_zero_completes(self):
        result = asyncio.run(self.registry.run_tool("slow", {}))
        self.assertEqual(result, "slow-result")


class CompoundTool(BaseTool):
    """A tool that uses an 'operation' parameter, similar to TagTool."""
    name = "compound"
    description = "A tool with sub-operations"

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "update", "delete"],
                    "description": "Operation to perform",
                },
                "item": {"type": "string"},
            },
            "required": ["operation"],
        }

    async def run(self, params: dict) -> str:
        op = params.get("operation", "")
        if op == "add":
            return f"Added: {params.get('item', '')}"
        if op == "update":
            return f"Updated: {params.get('item', '')}"
        if op == "delete":
            return f"Deleted: {params.get('item', '')}"
        return f"Unknown operation: {op}"


class TestCompoundNameFallback(unittest.TestCase):
    """run_tool should resolve compound names like 'compound add' into
    base tool 'compound' with operation='add'."""

    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register_tool(CompoundTool())

    def test_direct_name(self):
        """Direct tool name still works."""
        result = asyncio.run(
            self.registry.run_tool("compound", {"operation": "add", "item": "foo"})
        )
        self.assertEqual(result, "Added: foo")

    def test_compound_name_injects_operation(self):
        """'compound add' resolves to compound tool with operation='add'."""
        result = asyncio.run(
            self.registry.run_tool("compound add", {"item": "foo"})
        )
        self.assertEqual(result, "Added: foo")

    def test_compound_name_with_explicit_operation(self):
        """When operation is already in params, compound name still works."""
        result = asyncio.run(
            self.registry.run_tool("compound update", {"operation": "delete", "item": "bar"})
        )
        # Params' explicit operation takes precedence
        self.assertEqual(result, "Deleted: bar")

    def test_compound_name_unknown_base(self):
        """Unknown compound name still reports not registered."""
        result = asyncio.run(self.registry.run_tool("nonexistent foo", {}))
        self.assertIn("not registered", result)

    def test_compound_name_no_space(self):
        """Names without spaces should not be affected."""
        result = asyncio.run(
            self.registry.run_tool("compound", {"operation": "update", "item": "baz"})
        )
        self.assertEqual(result, "Updated: baz")
