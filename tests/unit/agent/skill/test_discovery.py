import tempfile
import unittest
from pathlib import Path

from laffyhand.agent.skill.discovery import discover_skills


class TestDiscoverSkills(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree, self.tmpdir)

    def _rmtree(self, path: Path) -> None:
        import shutil
        shutil.rmtree(path, ignore_errors=True)

    def _write_skill(self, base: Path, name: str, description: str = "") -> None:
        skill_dir = base / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = f"---\nname: {name}\n"
        if description:
            content += f"description: {description}\n"
        content += "---\nBody\n"
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    def test_discover_single_dir(self):
        self._write_skill(self.tmpdir, "test-skill", "A test")
        skills = discover_skills([self.tmpdir])
        self.assertIn("test-skill", skills)
        self.assertEqual(skills["test-skill"].description, "A test")

    def test_discover_multiple_skills(self):
        self._write_skill(self.tmpdir, "alpha", "First")
        self._write_skill(self.tmpdir, "beta", "Second")
        skills = discover_skills([self.tmpdir])
        self.assertEqual(len(skills), 2)
        self.assertIn("alpha", skills)
        self.assertIn("beta", skills)

    def test_discover_nested_dirs(self):
        sub = self.tmpdir / "sub" / "nested"
        self._write_skill(sub, "nested-skill")
        skills = discover_skills([self.tmpdir])
        self.assertIn("nested-skill", skills)

    def test_nonexistent_dir(self):
        skills = discover_skills([Path("/nonexistent/path")])
        self.assertEqual(len(skills), 0)

    def test_invalid_skill_skipped(self):
        (self.tmpdir / "bad").mkdir()
        (self.tmpdir / "bad" / "SKILL.md").write_text("No frontmatter", encoding="utf-8")
        self._write_skill(self.tmpdir, "good", "Valid")
        skills = discover_skills([self.tmpdir])
        self.assertIn("good", skills)
        self.assertNotIn("bad", skills)
