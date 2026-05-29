import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from laffyhand.agent.skill.models import SkillInfo
from laffyhand.agent.skill.registry import SkillRegistry
from laffyhand.agent.skill.discovery import discover_skills
from laffyhand.agent.tools.skill_tool import SkillTool
from laffyhand.agent.tools.permission import PermissionManager


class TestSkillLifecycle(unittest.TestCase):
    """Integration test: real files → discovery → registry → skill tool → permission."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmpdir, ignore_errors=True))

    def _write_skill(self, name: str, description: str = "", extra_file: str | None = None) -> None:
        skill_dir = self.tmpdir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = f"---\nname: {name}\n"
        if description:
            content += f"description: {description}\n"
        content += "---\n# Skill Body\nDetails about the skill.\n"
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        if extra_file:
            (skill_dir / extra_file).write_text("extra content", encoding="utf-8")

    def test_full_flow_with_permission_always(self):
        self._write_skill("code-review", "Review code changes")
        self._write_skill("deploy", "Deploy to production", extra_file="config.yaml")

        # Discovery
        skills = discover_skills([self.tmpdir])
        self.assertEqual(len(skills), 2)

        # Registry
        registry = SkillRegistry()
        registry.discover([self.tmpdir])
        self.assertEqual(len(registry.all()), 2)

        # Skill tool with permission always allowed
        pm = PermissionManager()
        pm.allow("skill:code-review")
        pm.allow("skill:deploy")
        tool = SkillTool(registry, pm)

        # Load skill (permission pre-approved)
        result = asyncio.run(tool.run({"name": "code-review"}))
        self.assertIn("Skill Body", result)
        self.assertIn("code-review", result)
        self.assertIn("skill_content", result)

        # Load second skill
        result2 = asyncio.run(tool.run({"name": "deploy"}))
        self.assertIn("Deploy", result2)
        self.assertIn("config.yaml", result2)

    def test_skill_not_found_error(self):
        registry = SkillRegistry()
        tool = SkillTool(registry, PermissionManager())
        result = asyncio.run(tool.run({"name": "nonexistent"}))
        self.assertIn("not found", result.lower())

    def test_summary_includes_all_skills(self):
        self._write_skill("s1", "Skill one")
        self._write_skill("s2", "Skill two")
        registry = SkillRegistry()
        registry.discover([self.tmpdir])
        summary = registry.build_skills_summary()
        self.assertIn("s1", summary)
        self.assertIn("s2", summary)
        self.assertIn("Available skills", summary)

    def test_require_throws_with_available_list(self):
        self._write_skill("existing", "I exist")
        registry = SkillRegistry()
        registry.discover([self.tmpdir])
        from laffyhand.agent.skill.models import SkillNotFoundError
        with self.assertRaises(SkillNotFoundError) as ctx:
            registry.require("missing")
        self.assertIn("existing", str(ctx.exception))
