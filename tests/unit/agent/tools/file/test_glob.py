import asyncio
import time
import unittest
import tempfile
from pathlib import Path
from laffyhand.core.tools.file.glob import GlobTool


class TestGlobTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "a.py").touch()
        time.sleep(0.01)
        (self.root / "b.py").touch()
        time.sleep(0.01)
        (self.root / "sub").mkdir()
        (self.root / "sub" / "c.py").touch()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_glob_top_level(self):
        tool = GlobTool()
        result = asyncio.run(tool.run({"pattern": "*.py", "path": str(self.root)}))
        self.assertIn("a.py", result)
        self.assertIn("b.py", result)

    def test_glob_recursive(self):
        tool = GlobTool()
        result = asyncio.run(tool.run({"pattern": "**/*.py", "path": str(self.root)}))
        self.assertIn("a.py", result)
        self.assertIn("c.py", result)

    def test_glob_no_match(self):
        tool = GlobTool()
        result = asyncio.run(tool.run({"pattern": "*.rs", "path": str(self.root)}))
        self.assertIn("No files found", result)

    def test_glob_sorted_by_mtime(self):
        tool = GlobTool()
        result = asyncio.run(tool.run({"pattern": "**/*.py", "path": str(self.root)}))
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 4)
        # Results sorted newest-first: c.py created last, then b.py, then a.py
        self.assertEqual(lines[1], "sub/c.py")
        self.assertEqual(lines[2], "b.py")
        self.assertEqual(lines[3], "a.py")

    def test_glob_subdir(self):
        tool = GlobTool()
        result = asyncio.run(
            tool.run({"pattern": "*.py", "path": str(self.root / "sub")})
        )
        self.assertIn("c.py", result)

    def test_glob_truncated(self):
        for i in range(150):
            (self.root / f"f{i:03d}.py").touch()
        tool = GlobTool()
        result = asyncio.run(tool.run({"pattern": "*.py", "path": str(self.root)}))
        self.assertIn("[Results limited to 100 files]", result)
        lines = [
            ln
            for ln in result.strip().split("\n")
            if ln.strip() and not ln.startswith("[") and not ln.startswith("---")
        ]
        self.assertLessEqual(len(lines), 100)

    def test_glob_pattern_no_asterisk(self):
        """Exact file name without wildcard should still find it."""
        (self.root / "unique_name.txt").write_text("data")
        tool = GlobTool()
        result = asyncio.run(
            tool.run({"pattern": "unique_name.txt", "path": str(self.root)})
        )
        self.assertIn("unique_name.txt", result)

    def test_glob_rejects_path_traversal(self):
        """Patterns that escape the search root should be blocked."""
        outer = self.root.parent / "malicious.txt"
        outer.write_text("pwned")
        try:
            tool = GlobTool()
            result = asyncio.run(
                tool.run(
                    {
                        "pattern": "../malicious.txt",
                        "path": str(self.root),
                    }
                )
            )
            self.assertIn("No files found", result)
            result2 = asyncio.run(
                tool.run(
                    {
                        "pattern": "../*/malicious.txt",
                        "path": str(self.root),
                    }
                )
            )
            self.assertIn("No files found", result2)
        finally:
            outer.unlink()
