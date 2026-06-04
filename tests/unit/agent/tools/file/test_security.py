import unittest
import tempfile
from pathlib import Path

from laffyhand.agent.tools.file._security import (
    looks_binary,
    blocked_write_path,
    atomic_write,
)
from laffyhand.agent.tools.file._text_utils import (
    detect_line_ending,
    normalize_newlines,
)


class TestLooksBinary(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_binary_by_extension(self):
        for ext in [".png", ".jpg", ".pdf", ".zip", ".pyc", ".so"]:
            f = self.root / f"test{ext}"
            f.write_text("text content")
            self.assertTrue(looks_binary(f), f"{ext} should be detected as binary")

    def test_not_binary_unknown_extension(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        self.assertFalse(looks_binary(f))

    def test_binary_by_null_byte(self):
        f = self.root / "test.bin"
        f.write_bytes(b"text\x00more")
        self.assertTrue(looks_binary(f))

    def test_binary_by_low_printable_ratio(self):
        f = self.root / "test.raw"
        f.write_bytes(b"\x01\x02\x03\x04\x05\x06\x07\x08" * 200)
        self.assertTrue(looks_binary(f))

    def test_text_file_not_binary(self):
        f = self.root / "test.txt"
        f.write_text("hello world\n" * 100)
        self.assertFalse(looks_binary(f))

    def test_empty_file_not_binary(self):
        f = self.root / "empty.txt"
        f.write_text("")
        self.assertFalse(looks_binary(f))

    def test_utf8_multibyte_text_not_binary(self):
        """UTF-8 with multi-byte chars (Chinese, Japanese, etc.) is text, not binary."""
        f = self.root / "readme.md"
        f.write_text("你好世界\n这是中文\n" * 20)
        self.assertFalse(looks_binary(f))

    def test_utf8_mixed_ascii_multibyte_not_binary(self):
        """Mixed ASCII + multi-byte UTF-8 is still text."""
        f = self.root / "mixed.txt"
        f.write_text("Hello 世界\nTest 测试\n" * 30)
        self.assertFalse(looks_binary(f))

    def test_file_not_found(self):
        f = self.root / "nonexistent.txt"
        self.assertTrue(looks_binary(f))


class TestBlockedWritePath(unittest.TestCase):
    def test_env_file_blocked(self):
        self.assertIsNotNone(blocked_write_path(Path("/workspace/.env")))
        self.assertIsNotNone(blocked_write_path(Path("/workspace/.env.local")))
        self.assertIsNotNone(blocked_write_path(Path("/workspace/.env.production")))

    def test_git_credentials_blocked(self):
        self.assertIsNotNone(blocked_write_path(Path("/workspace/.git-credentials")))

    def test_ssh_path_blocked(self):
        self.assertIsNotNone(blocked_write_path(Path("/root/.ssh/authorized_keys")))
        self.assertIsNotNone(blocked_write_path(Path("/home/user/.ssh/id_rsa")))

    def test_kube_path_blocked(self):
        self.assertIsNotNone(blocked_write_path(Path("/root/.kube/config")))

    def test_aws_path_blocked(self):
        self.assertIsNotNone(blocked_write_path(Path("/root/.aws/credentials")))

    def test_safe_path_allowed(self):
        self.assertIsNone(blocked_write_path(Path("/workspace/src/main.py")))

    def test_home_env_not_blocked(self):
        # .envvars should NOT be blocked (it's not .env / .env.xxx)
        self.assertIsNone(blocked_write_path(Path("/workspace/.envvars")))

    def test_path_traversal_blocked(self):
        self.assertIsNotNone(blocked_write_path(Path("/workspace/src/../../.env")))


class TestDetectLineEnding(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_crlf_detected(self):
        f = self.root / "crlf.txt"
        f.write_bytes(b"line1\r\nline2\r\n")
        self.assertEqual(detect_line_ending(f), "\r\n")

    def test_lf_detected(self):
        f = self.root / "lf.txt"
        f.write_bytes(b"line1\nline2\n")
        self.assertEqual(detect_line_ending(f), "\n")

    def test_mixed_prefers_crlf(self):
        f = self.root / "mixed.txt"
        f.write_bytes(b"line1\r\nline2\nline3\r\n")
        self.assertEqual(detect_line_ending(f), "\r\n")

    def test_empty_file_defaults_to_lf(self):
        f = self.root / "empty.txt"
        f.write_bytes(b"")
        self.assertEqual(detect_line_ending(f), "\n")

    def test_file_not_found_defaults_to_lf(self):
        f = self.root / "nonexistent.txt"
        self.assertEqual(detect_line_ending(f), "\n")


class TestNormalizeNewlines(unittest.TestCase):
    def test_crlf_to_lf(self):
        result = normalize_newlines("line1\r\nline2\r\n", "\n")
        self.assertEqual(result, "line1\nline2\n")

    def test_lf_to_crlf(self):
        result = normalize_newlines("line1\nline2\n", "\r\n")
        self.assertEqual(result, "line1\r\nline2\r\n")

    def test_lf_preserved(self):
        result = normalize_newlines("line1\nline2\n", "\n")
        self.assertEqual(result, "line1\nline2\n")

    def test_crlf_preserved(self):
        result = normalize_newlines("line1\r\nline2\r\n", "\r\n")
        self.assertEqual(result, "line1\r\nline2\r\n")

    def test_mixed_to_lf(self):
        result = normalize_newlines("line1\r\nline2\nline3\r\n", "\n")
        self.assertEqual(result, "line1\nline2\nline3\n")

    def test_empty_string(self):
        result = normalize_newlines("", "\n")
        self.assertEqual(result, "")


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_write_new_file(self):
        f = self.root / "test.txt"
        atomic_write(f, "hello world")
        self.assertTrue(f.exists())
        self.assertEqual(f.read_text(), "hello world")

    def test_write_empty_content(self):
        f = self.root / "empty.txt"
        atomic_write(f, "")
        self.assertTrue(f.exists())
        self.assertEqual(f.read_text(), "")

    def test_creates_parent_dirs(self):
        f = self.root / "a" / "b" / "c" / "test.txt"
        atomic_write(f, "nested")
        self.assertTrue(f.exists())
        self.assertEqual(f.read_text(), "nested")

    def test_overwrites_existing(self):
        f = self.root / "test.txt"
        atomic_write(f, "old")
        atomic_write(f, "new")
        self.assertEqual(f.read_text(), "new")

    def test_unicode_content(self):
        f = self.root / "unicode.txt"
        content = "你好世界 🎉"
        atomic_write(f, content)
        self.assertEqual(f.read_text(), content)
