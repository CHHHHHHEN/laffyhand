import asyncio
import unittest
from pathlib import Path

from laffyhand.agent.skill.models import SkillInfo
from laffyhand.agent.skill.registry import SkillRegistry
from laffyhand.agent.tools import ToolRegistry, SkillTool


class TestSkillToolInRegistry(unittest.TestCase):
    def setUp(self):
        self.tool_registry = ToolRegistry()
        self.skill_registry = SkillRegistry()
        self.skill_tool = SkillTool(self.skill_registry, self.tool_registry.permission)
        self.tool_registry.register_tool(self.skill_tool)

    def test_tool_definitions_includes_skill(self):
        defs = asyncio.run(self.tool_registry.build_tool_definitions())
        names = [d.name for d in defs]
        self.assertIn("skill", names)

    def test_tool_prompt_includes_skill(self):
        prompt = self.tool_registry.build_tool_prompt()
        self.assertIn("skill", prompt)

    def test_on_build_defs_updates_description(self):
        self.skill_registry._skills["test"] = SkillInfo(
            name="test",
            description="A test",
            base_dir=Path("."),
            filepath=Path("./SKILL.md"),
        )
        callback_called = False

        def _update():
            nonlocal callback_called
            callback_called = True
            summary = self.skill_registry.build_skills_summary()
            self.skill_tool.description = (
                f"Load skill.\n\n{summary}" if summary else "Load skill."
            )

        self.tool_registry.on_build_defs(_update)
        asyncio.run(self.tool_registry.build_tool_definitions())
        self.assertTrue(callback_called)
        self.assertIn("<skills>", self.skill_tool.description)
