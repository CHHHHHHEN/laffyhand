import unittest

from laffyhand.core.tools.file._fuzzy import (
    count_diff,
    exact_match,
    whitespace_normalized_match,
    trimmed_boundary_match,
    line_trimmed_match,
    escape_normalized_match,
    block_anchor_match,
    find_all_fuzzy,
    STRATEGIES,
)


class TestCountDiff(unittest.TestCase):
    def test_count_diff_additions(self):
        additions, deletions = count_diff("foo\nbar\n", "foo\nbar\nbaz\n")
        self.assertEqual(additions, 1)
        self.assertEqual(deletions, 0)

    def test_count_diff_deletions(self):
        additions, deletions = count_diff("foo\nbar\nbaz\n", "foo\nbar\n")
        self.assertEqual(additions, 0)
        self.assertEqual(deletions, 1)

    def test_count_diff_both(self):
        additions, deletions = count_diff("foo\nbar\n", "foo\nqux\n")
        self.assertEqual(additions, 1)
        self.assertEqual(deletions, 1)

    def test_count_diff_no_change(self):
        additions, deletions = count_diff("foo\nbar\n", "foo\nbar\n")
        self.assertEqual(additions, 0)
        self.assertEqual(deletions, 0)

    def test_count_diff_empty_old(self):
        additions, deletions = count_diff("", "hello\nworld\n")
        self.assertEqual(additions, 2)
        self.assertEqual(deletions, 0)


class TestExactMatch(unittest.TestCase):
    def test_exact_match_found(self):
        result = exact_match("hello world", "world")
        self.assertEqual(result, (6, 11))

    def test_exact_match_not_found(self):
        result = exact_match("hello world", "xyz")
        self.assertIsNone(result)

    def test_exact_match_at_start(self):
        result = exact_match("hello world", "hello")
        self.assertEqual(result, (0, 5))

    def test_exact_match_multibyte(self):
        result = exact_match("你好世界", "世界")
        self.assertEqual(result, (2, 4))

    def test_exact_match_empty_old(self):
        result = exact_match("content", "")
        self.assertEqual(result, (0, 0))


class TestWhitespaceNormalizedMatch(unittest.TestCase):
    def test_whitespace_difference(self):
        result = whitespace_normalized_match(
            "def foo():\n    print('x')", "def foo():\n    print('x')"
        )
        self.assertIsNotNone(result)

    def test_whitespace_varying_amounts(self):
        result = whitespace_normalized_match("x     y", "x y")
        self.assertIsNotNone(result)

    def test_whitespace_no_match(self):
        result = whitespace_normalized_match("hello world", "zzz")
        self.assertIsNone(result)

    def test_whitespace_tabs_vs_spaces(self):
        result = whitespace_normalized_match("x\ty", "x     y")
        self.assertIsNotNone(result)


class TestTrimmedBoundaryMatch(unittest.TestCase):
    def test_leading_whitespace(self):
        result = trimmed_boundary_match("hello world", "  hello world")
        self.assertIsNotNone(result)

    def test_trailing_whitespace(self):
        result = trimmed_boundary_match("hello world", "hello world  ")
        self.assertIsNotNone(result)

    def test_no_trim_needed(self):
        result = trimmed_boundary_match("hello world", "hello world")
        self.assertIsNone(result)

    def test_only_whitespace(self):
        result = trimmed_boundary_match("content", "   ")
        self.assertIsNone(result)


class TestLineTrimmedMatch(unittest.TestCase):
    def test_single_line_with_trim(self):
        result = line_trimmed_match("hello world", "  hello world  ")
        self.assertIsNotNone(result)

    def test_no_trim_needed(self):
        result = line_trimmed_match("line1\nline2\n", "line1\nline2\n")
        self.assertIsNone(result)

    def test_multi_line_concatenated(self):
        result = line_trimmed_match("hello-world", "hello \n -world")
        self.assertIsNotNone(result)


class TestEscapeNormalizedMatch(unittest.TestCase):
    def test_escaped_newline(self):
        result = escape_normalized_match("hello\nworld", "hello\\nworld")
        self.assertIsNotNone(result)

    def test_escaped_tab(self):
        result = escape_normalized_match("hello\tworld", "hello\\tworld")
        self.assertIsNotNone(result)

    def test_escaped_carriage_return(self):
        result = escape_normalized_match("hello\rworld", "hello\\rworld")
        self.assertIsNotNone(result)

    def test_no_escape_needed(self):
        result = escape_normalized_match("hello world", "hello world")
        self.assertIsNone(result)

    def test_escaped_mixed(self):
        result = escape_normalized_match("hello\n\tworld", "hello\\n\\tworld")
        self.assertIsNotNone(result)


class TestBlockAnchorMatch(unittest.TestCase):
    def test_requires_three_lines(self):
        result = block_anchor_match("line1\nline2", "line1\nline2")
        self.assertIsNone(result)

    def test_exact_three_line_block(self):
        content = "a\nb\nc\nd\ne"
        result = block_anchor_match(content, "b\nc\nd")
        self.assertIsNotNone(result)
        self.assertEqual(content[result[0]:result[1]], "b\nc\nd")

    def test_whitespace_difference_in_middle_lines(self):
        content = "a\n  hello\n  world\n  foo\nb"
        result = block_anchor_match(content, "a\nhello\nworld\nfoo\nb")
        self.assertIsNotNone(result)
        self.assertEqual(content[result[0]:result[1]], "a\n  hello\n  world\n  foo\nb")

    def test_no_match(self):
        content = "x\ny\nz"
        result = block_anchor_match(content, "a\nb\nc")
        self.assertIsNone(result)

    def test_similar_but_not_exact_middle_lines(self):
        content = "a\nhello_world\nfoo_bar\nb"
        result = block_anchor_match(content, "a\nhelloWorld\nfooBar\nb")
        self.assertIsNotNone(result)

    def test_multiple_candidates_pick_best(self):
        content = "a\nxxx\nyyy\nb\na\nppp\nqqq\nb"
        result = block_anchor_match(content, "a\nppp\nqqq\nb")
        self.assertIsNotNone(result)
        matched = content[result[0]:result[1]]
        self.assertEqual(matched, "a\nppp\nqqq\nb")


class TestStrategiesOrder(unittest.TestCase):
    def test_exact_match_first_in_strategies(self):
        self.assertEqual(STRATEGIES[0][0], "exact")

    def test_all_strategies_present(self):
        names = [name for name, _ in STRATEGIES]
        expected = [
            "exact",
            "whitespace normalized",
            "line trimmed",
            "block anchor",
            "trimmed boundary",
            "escape normalized",
        ]
        self.assertEqual(names, expected)

    def test_exact_matched_before_fallback(self):
        content = "hello world"
        for name, match_fn in STRATEGIES:
            result = match_fn(content, "world")
            if name == "exact":
                self.assertIsNotNone(result)
            break


class TestFindAllFuzzy(unittest.TestCase):
    def test_find_all_exact_matches(self):
        results = find_all_fuzzy("foo bar foo bar foo", "foo")
        self.assertEqual(len(results), 3)

    def test_find_all_fuzzy_whitespace(self):
        results = find_all_fuzzy("x y x    y", "x y")
        self.assertEqual(len(results), 2)

    def test_find_all_no_match(self):
        results = find_all_fuzzy("hello world", "zzz")
        self.assertEqual(results, [])
