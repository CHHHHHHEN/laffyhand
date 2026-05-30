import asyncio
import time
import unittest
import tempfile
from pathlib import Path
from laffyhand.agent.tools.file.glob import GlobTool


class TestGlobTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "a.py").touch()
        (self.root / "b.py").touch()
        (self.root / "sub").mkdir()
        (self.root / "sub" / "c.py").touch()
        time.sleep(0.01)

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
        # Should have 3 files
        self.assertEqual(len(lines), 3)

    def test_glob_subdir(self):
        tool = GlobTool()
        result = asyncio.run(tool.run({"pattern": "*.py", "path": str(self.root / "sub")}))
        self.assertIn("c.py", result)
