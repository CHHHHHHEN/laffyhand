import unittest
from pathlib import Path

from laffyhand.core.tools.file._diff import DiffConfig, DiffResult, format_diff


class TestDiffConfig(unittest.TestCase):
    def test_default_max_lines(self):
        config = DiffConfig()
        self.assertEqual(config.max_lines, 50)

    def test_custom_max_lines(self):
        config = DiffConfig(max_lines=10)
        self.assertEqual(config.max_lines, 10)


class TestFormatDiff(unittest.TestCase):
    def setUp(self):
        self.path = Path("/tmp/test.py")

    def test_additions(self):
        result = format_diff(self.path, "a\nb\n", "a\nb\nc\n")
        self.assertIn("+c", result.display)
        self.assertFalse(result.truncated)
        self.assertEqual(result.total_lines, 6)

    def test_deletions(self):
        result = format_diff(self.path, "a\nb\nc\n", "a\nb\n")
        self.assertIn("-c", result.display)
        self.assertFalse(result.truncated)
        self.assertEqual(result.total_lines, 6)

    def test_empty_old_content(self):
        result = format_diff(self.path, "", "hello\nworld\n")
        self.assertIn("+hello", result.display)
        self.assertIn("+world", result.display)
        self.assertFalse(result.truncated)
        self.assertEqual(result.total_lines, 5)

    def test_identical_content(self):
        result = format_diff(self.path, "same\n", "same\n")
        self.assertEqual(result.display, "")
        self.assertEqual(result.total_lines, 0)
        self.assertFalse(result.truncated)

    def test_truncated(self):
        old = "\n".join(f"line{i}" for i in range(100))
        new = "\n".join(f"line{i}" for i in range(100))
        new += "\nextra"
        config = DiffConfig(max_lines=5)
        result = format_diff(self.path, old, new, config)
        self.assertTrue(result.truncated)
        self.assertEqual(result.total_lines, 8)
        self.assertIn("diff truncated", result.display)

    def test_custom_config_no_truncation(self):
        result = format_diff(self.path, "a\n", "b\n", DiffConfig(max_lines=10))
        self.assertFalse(result.truncated)
        self.assertIn("-a", result.display)
        self.assertIn("+b", result.display)

    def test_path_in_header(self):
        result = format_diff(self.path, "a\n", "b\n")
        self.assertIn(str(self.path), result.display)

    def test_diff_result_fields(self):
        config = DiffConfig(max_lines=1)
        result = format_diff(self.path, "a\nb\n", "a\nc\n", config)
        self.assertIsInstance(result, DiffResult)
        self.assertIsInstance(result.display, str)
        self.assertIsInstance(result.total_lines, int)
        self.assertIsInstance(result.truncated, bool)
