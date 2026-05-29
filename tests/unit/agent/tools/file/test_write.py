import unittest
import tempfile
from pathlib import Path
from laffyhand.agent.tools.file.write import WriteTool


class TestWriteTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_write_file(self):
        f = self.root / "test.txt"
        tool = WriteTool()
        result = tool.run({"file_path": str(f), "content": "hello"})
        self.assertIn("File written", result)
        self.assertEqual(f.read_text(), "hello")

    def test_write_creates_parent_dirs(self):
        f = self.root / "sub" / "nested" / "test.txt"
        tool = WriteTool()
        result = tool.run({"file_path": str(f), "content": "nested"})
        self.assertIn("File written", result)
        self.assertTrue(f.exists())
        self.assertEqual(f.read_text(), "nested")
