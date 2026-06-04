import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from laffyhand.agent.skill.models import SkillInfo, SkillNotFoundError
from laffyhand.agent.skill.registry import SkillRegistry
from laffyhand.agent.tools.skill_tool import SkillTool


class TestSkillTool(unittest.TestCase):
    def setUp(self):
        self.registry = MagicMock(spec=SkillRegistry)
        self.tool = SkillTool(self.registry)

    def test_tool_name(self):
        self.assertEqual(self.tool.name, "skill")

    def test_input_schema_has_name(self):
        schema = self.tool._input_schema()
        self.assertIn("name", schema.get("properties", {}))
        self.assertIn("name", schema.get("required", []))

    def test_require_called_with_name(self):
        self.registry.require.side_effect = SkillNotFoundError("x", [])
        result = asyncio.run(self.tool.run({"name": "x"}))
        self.registry.require.assert_called_once_with("x")
        self.assertIn("not found", result.lower())

    def test_permission_denied(self):
        info = SkillInfo(
            name="test", base_dir=Path("/tmp"), filepath=Path("/tmp/SKILL.md")
        )
        self.registry.require.return_value = info
        # Mock the permission manager to deny
        self.tool._permission.ask = AsyncMock(return_value=(False, None))  # type: ignore[method-assign]
        result = asyncio.run(self.tool.run({"name": "test"}))
        self.assertIn("denied", result.lower())

    def test_skill_content_returned(self):
        tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmpdir, ignore_errors=True))
        skill_file = tmpdir / "SKILL.md"
        skill_file.write_text("---\nname: my\n---\n# Skill Body\n", encoding="utf-8")
        info = SkillInfo(name="my", base_dir=tmpdir, filepath=skill_file)
        self.registry.require.return_value = info
        self.tool._permission.ask = AsyncMock(return_value=(True, None))  # type: ignore[method-assign]
        result = asyncio.run(self.tool.run({"name": "my"}))
        self.assertIn("Skill Body", result)
        self.assertIn("skill_content", result)
        self.assertIn("my", result)

    def test_sibling_files_included(self):
        tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmpdir, ignore_errors=True))
        (tmpdir / "SKILL.md").write_text("---\nname: s\n---\nBody", encoding="utf-8")
        (tmpdir / "ref.txt").write_text("ref", encoding="utf-8")
        (tmpdir / "sub").mkdir()
        info = SkillInfo(name="s", base_dir=tmpdir, filepath=tmpdir / "SKILL.md")
        self.registry.require.return_value = info
        self.tool._permission.ask = AsyncMock(return_value=(True, None))  # type: ignore[method-assign]
        result = asyncio.run(self.tool.run({"name": "s"}))
        self.assertIn("skill_files", result)
        self.assertIn("ref.txt", result)

    def test_skipped_skill_md_in_siblings(self):
        tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmpdir, ignore_errors=True))
        (tmpdir / "SKILL.md").write_text("---\nname: s\n---\nBody", encoding="utf-8")
        (tmpdir / "other.md").write_text("other", encoding="utf-8")
        info = SkillInfo(name="s", base_dir=tmpdir, filepath=tmpdir / "SKILL.md")
        self.registry.require.return_value = info
        self.tool._permission.ask = AsyncMock(return_value=(True, None))  # type: ignore[method-assign]
        result = asyncio.run(self.tool.run({"name": "s"}))
        self.assertNotIn(
            "SKILL.md",
            result.split("skill_files")[1] if "skill_files" in result else "",
        )
