import unittest
from pathlib import Path

from laffyhand.core.tools.file._path_boundary import is_within


class TestIsWithin(unittest.TestCase):
    def test_within_same_dir(self):
        self.assertTrue(is_within("/workspace/foo.py", "/workspace"))

    def test_within_subdir(self):
        self.assertTrue(is_within("/workspace/sub/foo.py", "/workspace"))

    def test_workspace_is_none(self):
        self.assertTrue(is_within("/any/path", None))

    def test_outside_above(self):
        self.assertFalse(is_within("/workspace", "/workspace/sub"))

    def test_outside_traversal(self):
        self.assertFalse(is_within("/etc/passwd", "/workspace"))

    def test_symlink_outside(self):
        import tempfile
        root = Path(tempfile.mkdtemp())
        outside = Path(tempfile.mkdtemp())
        link = root / "secret"
        link.symlink_to(outside)
        self.assertFalse(is_within(link / "file.txt", root))
