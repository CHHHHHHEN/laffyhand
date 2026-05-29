import asyncio
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

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_glob_top_level(self):
        tool = GlobTool()
        result = asyncio.run(tool.run({"pattern": "*.py", "path": str(self.root)}))
        self.assertIn("a.py", result)
        self.assertIn("b.py", result)
        self.assertNotIn("sub/c.py", result)

    def test_glob_recursive(self):
        tool = GlobTool()
        result = asyncio.run(tool.run({"pattern": "**/*.py", "path": str(self.root)}))
        self.assertIn("a.py", result)
        self.assertIn("sub/c.py", result)

    def test_glob_no_match(self):
        tool = GlobTool()
        result = asyncio.run(tool.run({"pattern": "*.rs", "path": str(self.root)}))
        self.assertIn("No files found", result)
