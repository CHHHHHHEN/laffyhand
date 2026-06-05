import tempfile
import unittest
from pathlib import Path

from laffyhand.core.skill.parser import parse_skill_md


class TestParseSkillMd(unittest.TestCase):
    def _write_skill(self, content: str) -> Path:
        f = Path(tempfile.mktemp(suffix=".md"))
        f.write_text(content, encoding="utf-8")
        self.addCleanup(f.unlink, missing_ok=True)
        return f

    def test_valid_skill(self):
        f = self._write_skill("""---
name: my-skill
description: A test skill
---
# My Skill
Some content here
""")
        info = parse_skill_md(f)
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "my-skill")
        self.assertEqual(info.description, "A test skill")
        self.assertEqual(info.filepath, f)
        self.assertEqual(info.base_dir, f.parent)

    def test_name_only(self):
        f = self._write_skill("""---
name: minimal
---
Just content
""")
        info = parse_skill_md(f)
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "minimal")
        self.assertIsNone(info.description)

    def test_no_frontmatter(self):
        f = self._write_skill("Just content without frontmatter")
        info = parse_skill_md(f)
        self.assertIsNone(info)

    def test_no_name_field(self):
        f = self._write_skill("""---
description: no name here
---
Content
""")
        info = parse_skill_md(f)
        self.assertIsNone(info)

    def test_empty_frontmatter(self):
        f = self._write_skill("""---
---
Content""")
        info = parse_skill_md(f)
        self.assertIsNone(info)

    def test_file_not_found(self):
        info = parse_skill_md(Path("/nonexistent/path/SKILL.md"))
        self.assertIsNone(info)

    def test_extra_fields_ignored(self):
        f = self._write_skill("""---
name: extra
description: Has extras
version: 1.0
author: test
---
Body
""")
        info = parse_skill_md(f)
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "extra")
