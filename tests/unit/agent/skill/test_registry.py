import unittest
from pathlib import Path

from laffyhand.agent.skill.models import SkillInfo, SkillNotFoundError
from laffyhand.agent.skill.registry import SkillRegistry


class TestSkillRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = SkillRegistry()
        self.info_a = SkillInfo(name="skill-a", description="First", base_dir=Path("/a"), filepath=Path("/a/SKILL.md"))
        self.info_b = SkillInfo(name="skill-b", description="Second", base_dir=Path("/b"), filepath=Path("/b/SKILL.md"))

    def test_empty_initially(self):
        self.assertEqual(len(self.registry.all()), 0)

    def test_discover_adds_skills(self):
        self.registry.discover([self.info_a.base_dir])
        # No real files, but discover should handle directories without SKILL.md
        self.assertEqual(len(self.registry.all()), 0)

    def test_get_returns_none_for_missing(self):
        self.assertIsNone(self.registry.get("nonexistent"))

    def test_get_returns_skill(self):
        self.registry._skills["skill-a"] = self.info_a
        result = self.registry.get("skill-a")
        self.assertIs(result, self.info_a)

    def test_require_found(self):
        # Force-populate the internal dict
        self.registry._skills["skill-a"] = self.info_a
        result = self.registry.require("skill-a")
        self.assertIs(result, self.info_a)

    def test_require_not_found_raises(self):
        with self.assertRaises(SkillNotFoundError) as ctx:
            self.registry.require("missing")
        self.assertIn("Available skills", str(ctx.exception))

    def test_require_error_lists_available(self):
        self.registry._skills["a"] = self.info_a
        self.registry._skills["b"] = self.info_b
        with self.assertRaises(SkillNotFoundError) as ctx:
            self.registry.require("missing")
        self.assertIn("a", str(ctx.exception))
        self.assertIn("b", str(ctx.exception))

    def test_all_returns_copy(self):
        self.registry._skills["a"] = self.info_a
        skills = self.registry.all()
        self.assertEqual(len(skills), 1)
        # Modifying returned list shouldn't affect registry
        skills.clear()
        self.assertEqual(len(self.registry.all()), 1)

    def test_build_skills_summary_with_skills(self):
        self.registry._skills["a"] = self.info_a
        self.registry._skills["b"] = self.info_b
        summary = self.registry.build_skills_summary()
        self.assertIn("skill-a", summary)
        self.assertIn("skill-b", summary)
        self.assertIn("Available skills", summary)

    def test_build_skills_summary_empty(self):
        self.assertEqual(self.registry.build_skills_summary(), "")

    def test_build_skills_summary_no_description(self):
        info = SkillInfo(name="desc", base_dir=Path("/x"), filepath=Path("/x/SKILL.md"))
        self.registry._skills["desc"] = info
        summary = self.registry.build_skills_summary()
        self.assertIn("desc", summary)
        self.assertIn("no description", summary)
