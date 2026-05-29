import unittest
from laffyhand.agent.tools.truncation import truncate_output


class TestTruncation(unittest.TestCase):
    def test_no_truncation(self):
        self.assertEqual(truncate_output("hello", 100), "hello")

    def test_truncation_applied(self):
        result = truncate_output("x" * 100, 10)
        self.assertTrue(result.startswith("x" * 10))
        self.assertIn("[Tool output truncated:", result)

    def test_empty_input(self):
        self.assertEqual(truncate_output("", 10), "")

    def test_exact_max(self):
        self.assertEqual(truncate_output("x" * 10, 10), "x" * 10)

    def test_none_input(self):
        self.assertEqual(truncate_output("", 10), "")

    def test_default_max_chars(self):
        text = "x" * 3000
        result = truncate_output(text)
        self.assertIn("[Tool output truncated:", result)
