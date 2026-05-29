import asyncio
import unittest
from unittest.mock import patch

from laffyhand.agent.tools.permission import PermissionManager


class TestPermissionAsk(unittest.TestCase):
    def setUp(self):
        self.pm = PermissionManager()

    def test_ask_denied_by_rule(self):
        self.pm.deny("skill:test")
        result = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertFalse(result)

    def test_ask_allowed_by_rule(self):
        self.pm.allow("skill:test")
        result = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertTrue(result)

    def test_ask_multiple_patterns_one_denied(self):
        self.pm.deny("skill:bad")
        with patch("asyncio.to_thread", return_value="y"):
            result = asyncio.run(self.pm.ask("skill", ["good", "bad"]))
        self.assertFalse(result)

    def test_ask_all_allowed_through_allow_rule(self):
        self.pm.allow("skill:good")
        self.pm.allow("skill:bad")
        result = asyncio.run(self.pm.ask("skill", ["good", "bad"]))
        self.assertTrue(result)

    def test_ask_mixed_deny_then_allow(self):
        self.pm.deny("skill:first")  # first denied -> returns False
        result = asyncio.run(self.pm.ask("skill", ["first", "second"]))
        self.assertFalse(result)

    def test_ask_interactive_yes(self):
        with patch("asyncio.to_thread", return_value="y"):
            result = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertTrue(result)

    def test_ask_interactive_no(self):
        with patch("asyncio.to_thread", return_value="n"):
            result = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertFalse(result)

    def test_ask_interactive_always(self):
        with patch("asyncio.to_thread", return_value="a"):
            result = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertTrue(result)
        # Future calls should be auto-allowed
        self.assertTrue(asyncio.run(self.pm.ask("skill", ["test"])))

    def test_ask_interactive_always_persists_rule(self):
        with patch("asyncio.to_thread", return_value="a"):
            asyncio.run(self.pm.ask("skill", ["test"]))
        # The rule should be stored
        self.assertTrue(self.pm.check("skill:test"))

    def test_ask_no_tty_raises(self):
        with patch("asyncio.to_thread", side_effect=EOFError):
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertIn("no interactive terminal", str(ctx.exception).lower())

    def test_ask_no_tty_oserror_raises(self):
        with patch("asyncio.to_thread", side_effect=OSError):
            with self.assertRaises(RuntimeError):
                asyncio.run(self.pm.ask("skill", ["test"]))
