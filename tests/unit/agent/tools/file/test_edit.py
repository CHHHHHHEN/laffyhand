import unittest
import tempfile
from pathlib import Path
from laffyhand.agent.tools.file.edit import EditTool


class TestEditTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_edit_single_occurrence(self):
        f = self.root / "test.txt"
        f.write_text("foo\nbar\nbaz")
        tool = EditTool()
        result = tool.run({"file_path": str(f), "old_string": "bar", "new_string": "qux"})
        self.assertIn("Edited", result)
        self.assertEqual(f.read_text(), "foo\nqux\nbaz")

    def test_edit_file_not_found(self):
        tool = EditTool()
        result = tool.run({
            "file_path": str(self.root / "nope.txt"),
            "old_string": "a",
            "new_string": "b",
        })
        self.assertIn("not found", result.lower())

    def test_edit_string_not_found(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        tool = EditTool()
        result = tool.run({"file_path": str(f), "old_string": "zzz", "new_string": "xxx"})
        self.assertIn("not found", result)

    def test_edit_multiple_matches(self):
        f = self.root / "test.txt"
        f.write_text("foo\nfoo\nfoo")
        tool = EditTool()
        result = tool.run({"file_path": str(f), "old_string": "foo", "new_string": "bar"})
        self.assertIn("3 matches", result.lower())
