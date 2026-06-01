import unittest
from pathlib import Path

from laffyhand.agent.skill.models import SkillInfo, SkillNotFoundError


class TestSkillInfo(unittest.TestCase):
    def test_basic_fields(self):
        info = SkillInfo(
            name="my-skill",
            base_dir=Path("/tmp/skills/my-skill"),
            filepath=Path("/tmp/skills/my-skill/SKILL.md"),
        )
        self.assertEqual(info.name, "my-skill")
        self.assertIsNone(info.description)

    def test_with_description(self):
        info = SkillInfo(
            name="test",
            description="A test skill",
            base_dir=Path("."),
            filepath=Path("./SKILL.md"),
        )
        self.assertEqual(info.description, "A test skill")

    def test_serialization(self):
        info = SkillInfo(name="s", base_dir=Path("/a"), filepath=Path("/a/SKILL.md"))
        d = info.model_dump()
        self.assertEqual(d["name"], "s")
        self.assertEqual(str(d["base_dir"]), "/a")


class TestSkillNotFoundError(unittest.TestCase):
    def test_message_with_available(self):
        err = SkillNotFoundError("missing", ["a", "b"])
        self.assertIn("missing", str(err))
        self.assertIn("a", str(err))
        self.assertIn("b", str(err))

    def test_message_no_available(self):
        err = SkillNotFoundError("missing", [])
        self.assertIn("missing", str(err))
        self.assertIn("(none)", str(err))

    def test_attributes(self):
        err = SkillNotFoundError("x", ["y", "z"])
        self.assertEqual(err.skill_name, "x")
        self.assertEqual(err.available, ["y", "z"])
