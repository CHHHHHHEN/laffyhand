import asyncio
import tempfile
import unittest
from pathlib import Path

from laffyhand.agent.tools.bash import BashTool


class TestBashTool(unittest.TestCase):
    def setUp(self):
        self.tool = BashTool()

    def test_echo(self):
        result = asyncio.run(self.tool.run({"command": "echo hello"}))
        self.assertEqual(result, "hello")

    def test_exit_code_nonzero(self):
        result = asyncio.run(self.tool.run({"command": "false"}))
        self.assertIn("Exit code:", result)

    def test_timeout(self):
        result = asyncio.run(self.tool.run({"command": "sleep 10", "timeout": 100}))
        self.assertIn("timed out", result.lower())

    def test_stderr_included(self):
        result = asyncio.run(self.tool.run({"command": "echo out && echo err >&2"}))
        self.assertIn("out", result)
        self.assertIn("err", result)

    def test_workdir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = asyncio.run(self.tool.run({"command": "pwd", "workdir": tmpdir}))
            self.assertEqual(result.strip(), tmpdir)

    def test_workdir_affects_file_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "marker.txt").touch()
            result = asyncio.run(
                self.tool.run({"command": "ls marker.txt", "workdir": tmpdir})
            )
            self.assertIn("marker.txt", result)


class TestInlinePythonSecurity(unittest.TestCase):
    """Test the inline Python script security scanner."""

    def setUp(self):
        self.tool = BashTool()

    # ── _extract_inline_code tests ──────────────────────────────

    def test_extract_code_double_quotes(self):
        from laffyhand.agent.tools.bash import _extract_inline_code
        code = _extract_inline_code('python3 -c "print(1+1)"')
        self.assertEqual(code, "print(1+1)")

    def test_extract_code_single_quotes(self):
        from laffyhand.agent.tools.bash import _extract_inline_code
        code = _extract_inline_code("python3 -c 'repr(line)'")
        self.assertEqual(code, "repr(line)")

    def test_extract_code_no_inline(self):
        from laffyhand.agent.tools.bash import _extract_inline_code
        code = _extract_inline_code("python3 my_script.py")
        self.assertIsNone(code)

    def test_extract_code_python2(self):
        from laffyhand.agent.tools.bash import _extract_inline_code
        code = _extract_inline_code('python -c "import sys; print(sys.version)"')
        self.assertEqual(code, "import sys; print(sys.version)")

    def test_extract_code_no_quotes(self):
        from laffyhand.agent.tools.bash import _extract_inline_code
        code = _extract_inline_code("python3 -c")
        self.assertIsNone(code)

    # ── _check_inline_python tests ──────────────────────────────

    def test_repr_is_safe(self):
        """repr() should be allowed — pure read, no side effects."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c \"print(repr('hello'))\""})
        )
        self.assertNotIn("Blocked", result)

    def test_print_is_safe(self):
        """print() should be allowed."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c 'print(42)'"})
        )
        self.assertNotIn("Blocked", result)

    def test_len_is_safe(self):
        """len() should be allowed."""
        result = asyncio.run(
            self.tool.run({"command": 'python3 -c "print(len([1,2,3]))"'})
        )
        self.assertNotIn("Blocked", result)

    def test_type_is_safe(self):
        """type() and basic introspection should be allowed."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c \"print(type('abc'))\""})
        )
        self.assertNotIn("Blocked", result)

    def test_eval_is_blocked(self):
        """eval() in inline Python should be blocked."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c \"eval('1+1')\""})
        )
        self.assertIn("Blocked", result)
        self.assertIn("eval", result)

    def test_exec_is_blocked(self):
        """exec() in inline Python should be blocked."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c \"exec('x=1')\""})
        )
        self.assertIn("Blocked", result)
        self.assertIn("exec", result)

    def test_os_system_is_blocked(self):
        """os.system() in inline Python should be blocked."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c \"import os; os.system('ls')\""})
        )
        self.assertIn("Blocked", result)
        self.assertIn("os.system", result)

    def test_open_write_is_blocked(self):
        """open() with write mode in inline Python should be blocked."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c \"open('/tmp/x', 'w')\""})
        )
        self.assertIn("Blocked", result)
        self.assertIn("write mode", result)

    def test_open_read_is_safe(self):
        """open() with read mode in inline Python should be allowed."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c \"print(open('/dev/null', 'r').read())\""})
        )
        self.assertNotIn("Blocked", result)

    def test_subprocess_is_blocked(self):
        """subprocess.* in inline Python should be blocked."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c \"import subprocess; subprocess.run(['ls'])\""})
        )
        self.assertIn("Blocked", result)
        self.assertIn("subprocess", result)

    def test_socket_is_blocked(self):
        """socket.* in inline Python should be blocked (network egress)."""
        result = asyncio.run(
            self.tool.run({"command": "python3 -c \"import socket; socket.connect(('evil.com', 80))\""})
        )
        self.assertIn("Blocked", result)
        self.assertIn("socket", result)

    def test_base64_decode_is_blocked(self):
        """base64 decode in inline Python should be blocked (encoded payload)."""
        result = asyncio.run(
            self.tool.run({"command": 'python3 -c "import base64; base64.b64decode(\'aGVsbG8=\')"'})
        )
        self.assertIn("Blocked", result)
        self.assertIn("base64", result)

    def test_no_inline_python_is_unaffected(self):
        """Non-inline-python commands should work as before."""
        result = asyncio.run(
            self.tool.run({"command": "echo hello"})
        )
        self.assertEqual(result, "hello")

    def test_perl_e_still_blocked(self):
        """perl -e should remain blocked."""
        result = asyncio.run(
            self.tool.run({"command": "perl -e 'print 42'"})
        )
        self.assertIn("Blocked", result)
        self.assertIn("perl", result)

    def test_node_e_still_blocked(self):
        """node -e should remain blocked."""
        result = asyncio.run(
            self.tool.run({"command": "node -e 'console.log(\"hi\")'"})
        )
        self.assertIn("Blocked", result)
        self.assertIn("node", result)
