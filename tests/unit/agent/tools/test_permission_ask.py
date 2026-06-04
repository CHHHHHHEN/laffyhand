import asyncio
import unittest
from unittest.mock import patch

from laffyhand.agent.tools.permission import PermissionManager


class TestPermissionAsk(unittest.TestCase):
    def setUp(self):
        self.pm = PermissionManager()

    def test_ask_denied_by_rule(self):
        self.pm.deny("skill:test")
        allowed, reason = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertFalse(allowed)
        self.assertIsNone(reason)

    def test_ask_allowed_by_rule(self):
        self.pm.allow("skill:test")
        allowed, reason = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_ask_multiple_patterns_one_denied(self):
        self.pm.deny("skill:bad")
        with patch("asyncio.to_thread", return_value="y"):
            allowed, _ = asyncio.run(self.pm.ask("skill", ["good", "bad"]))
        self.assertFalse(allowed)

    def test_ask_all_allowed_through_allow_rule(self):
        self.pm.allow("skill:good")
        self.pm.allow("skill:bad")
        allowed, _ = asyncio.run(self.pm.ask("skill", ["good", "bad"]))
        self.assertTrue(allowed)

    def test_ask_mixed_deny_then_allow(self):
        self.pm.deny("skill:first")
        allowed, _ = asyncio.run(self.pm.ask("skill", ["first", "second"]))
        self.assertFalse(allowed)

    def test_ask_interactive_yes(self):
        with patch("asyncio.to_thread", return_value="y"):
            allowed, _ = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertTrue(allowed)

    def test_ask_interactive_no(self):
        with patch("asyncio.to_thread", return_value="n"):
            allowed, _ = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertFalse(allowed)

    def test_ask_interactive_always(self):
        with patch("asyncio.to_thread", return_value="a"):
            allowed, _ = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertTrue(allowed)
        # Future calls should be auto-allowed
        self.assertTrue(asyncio.run(self.pm.ask("skill", ["test"]))[0])

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


class TestPermissionAskCallback(unittest.TestCase):
    def setUp(self):
        self.pm = PermissionManager()

    def test_callback_called_when_no_rule(self):
        async def callback(permission, pattern):
            self.assertEqual(permission, "skill")
            self.assertEqual(pattern, "test")
            return (True, None)

        self.pm.request_callback = callback
        allowed, _ = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertTrue(allowed)

    def test_callback_denied_without_reason(self):
        async def callback(permission, pattern):
            return (False, None)

        self.pm.request_callback = callback
        allowed, reason = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertFalse(allowed)
        self.assertIsNone(reason)

    def test_callback_denied_with_reason(self):
        async def callback(permission, pattern):
            return (False, "not needed right now")

        self.pm.request_callback = callback
        allowed, reason = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertFalse(allowed)
        self.assertEqual(reason, "not needed right now")

    def test_callback_not_called_when_rule_exists(self):
        self.pm.allow("skill:test")
        self.pm.request_callback = lambda p, pat: (_ for _ in ()).throw(
            AssertionError("should not be called")
        )
        allowed, _ = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertTrue(allowed)

    def test_callback_not_called_when_blanket_deny(self):
        self.pm.deny("skill")
        call_count = 0

        async def callback(permission, pattern):
            nonlocal call_count
            call_count += 1
            return (True, None)

        self.pm.request_callback = callback
        allowed, reason = asyncio.run(self.pm.ask("skill", ["test"]))
        self.assertFalse(allowed)
        self.assertIsNone(reason)
        self.assertEqual(call_count, 0)

    def test_callback_multiple_patterns_first_fails(self):
        results = iter([(False, None)])

        async def callback(permission, pattern):
            return next(results)

        self.pm.request_callback = callback
        allowed, _ = asyncio.run(self.pm.ask("skill", ["first", "second"]))
        self.assertFalse(allowed)

    def test_callback_multiple_patterns_all_pass(self):
        results = iter([(True, None), (True, None)])

        async def callback(permission, pattern):
            return next(results)

        self.pm.request_callback = callback
        allowed, _ = asyncio.run(self.pm.ask("skill", ["first", "second"]))
        self.assertTrue(allowed)
