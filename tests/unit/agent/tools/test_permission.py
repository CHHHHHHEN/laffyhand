import asyncio
import unittest
from unittest.mock import patch

from laffyhand.core.tools.permission import PermissionManager, SubagentPermissions


class TestPermission(unittest.TestCase):
    def test_default_allow(self):
        pm = PermissionManager()
        self.assertTrue(pm.check("any_tool"))

    def test_deny(self):
        pm = PermissionManager()
        pm.deny("bash")
        self.assertFalse(pm.check("bash"))

    def test_allow_override(self):
        pm = PermissionManager()
        pm.deny("bash")
        pm.add_rule("bash", "allow")
        self.assertTrue(pm.check("bash"))

    def test_deny_one_not_others(self):
        pm = PermissionManager()
        pm.deny("bash")
        self.assertTrue(pm.check("read"))


class TestRequirePath(unittest.TestCase):
    def setUp(self):
        self.pm = PermissionManager()

    def test_within_workspace(self):
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/home/user/project/src/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_no_rules_no_tty(self):
        with patch("asyncio.to_thread", side_effect=EOFError):
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    self.pm.require_path("read", "/outside/file.py", "/home/user/project")
                )

    def test_outside_allowed_exact_path(self):
        self.pm.add_rule("outside_workspace:/outside/file.py", "allow")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_denied_exact_path(self):
        self.pm.deny("outside_workspace:/outside/file.py")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/file.py", "/home/user/project")
        )
        self.assertFalse(allowed)

    def test_outside_subdir_allowed_by_parent_dir(self):
        self.pm.add_rule("outside_workspace:/outside/dir", "allow")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/sub/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_subdir_allowed_by_grandparent_dir(self):
        self.pm.add_rule("outside_workspace:/outside", "allow")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/a/b/c/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_subdir_denied_by_parent_dir(self):
        self.pm.deny("outside_workspace:/outside/dir")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/sub/file.py", "/home/user/project")
        )
        self.assertFalse(allowed)

    def test_outside_sibling_not_allowed(self):
        self.pm.add_rule("outside_workspace:/outside/dir_a", "allow")
        with patch("asyncio.to_thread", side_effect=EOFError):
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    self.pm.require_path("read", "/outside/dir_b/file.py", "/home/user/project")
                )

    def test_outside_allowed_file_not_confused_with_dir(self):
        self.pm.add_rule("outside_workspace:/outside/file.py", "allow")
        with patch("asyncio.to_thread", side_effect=EOFError):
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    self.pm.require_path("read", "/outside/other.py", "/home/user/project")
                )

    def test_always_allow_file_covers_sibling(self):
        """When user always-allows a file, sibling files in same dir are also allowed."""
        with patch("asyncio.to_thread", return_value="a"):
            allowed, _ = asyncio.run(
                self.pm.require_path("read", "/outside/dir/file.py", "/home/user/project")
            )
        self.assertTrue(allowed)
        # Sibling file should be auto-allowed via propagated parent rule
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/other.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_always_allow_file_covers_subdir(self):
        """When user always-allows a file, files in subdirectories under it are also allowed."""
        with patch("asyncio.to_thread", return_value="a"):
            allowed, _ = asyncio.run(
                self.pm.require_path("read", "/outside/dir/file.py", "/home/user/project")
            )
        self.assertTrue(allowed)
        # File in subdirectory should be auto-allowed
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/sub/other.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_unified_namespace_covers_different_tool(self):
        """An 'always allow' for one tool (e.g. read) also covers other tools (e.g. list_dir)."""
        with patch("asyncio.to_thread", return_value="a"):
            allowed, _ = asyncio.run(
                self.pm.require_path("read", "/outside/dir", "/home/user/project")
            )
        self.assertTrue(allowed)
        # Different tool on a subdirectory should also be allowed
        allowed, _ = asyncio.run(
            self.pm.require_path("list_dir", "/outside/dir/sub", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_check_parent_rules_checks_path_itself(self):
        """_check_parent_rules should find a rule for the exact path, not just parents."""
        self.pm.add_rule("outside_workspace:/outside/dir", "allow")
        # Access the directory itself — previously required ask(),
        # now handled by _check_parent_rules
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir", "/home/user/project")
        )
        self.assertTrue(allowed)


class TestPermissionParentDelegation(unittest.TestCase):
    def setUp(self):
        self.parent = PermissionManager()
        self.parent.add_rule("read", "allow")
        self.parent.add_rule("write", "allow")
        self.parent.add_rule("outside_workspace:/allowed_dir", "allow")
        self.child = PermissionManager(parent=self.parent)

    def test_child_sees_parent_allow_rules(self):
        """Child's check() returns True for tools allowed by parent."""
        self.assertTrue(self.child.check("read"))
        self.assertTrue(self.child.check("write"))

    def test_child_sees_parent_deny_rules(self):
        """Child's check() returns False for tools denied by parent."""
        self.parent.deny("bash")
        self.assertFalse(self.child.check("bash"))

    def test_child_override_deny(self):
        """Child's deny rule overrides parent's allow."""
        self.child.deny("write")
        self.assertFalse(self.child.check("write"))

    def test_child_override_allow(self):
        """Child's allow rule overrides parent's deny."""
        self.parent.deny("bash")
        self.child.add_rule("bash", "allow")
        self.assertTrue(self.child.check("bash"))

    def test_child_no_rules_default_allow(self):
        """Child with no rules at all defaults to allow."""
        child2 = PermissionManager(parent=self.parent)
        self.assertTrue(child2.check("any_unknown_tool"))

    def test_child_sees_parent_rules_added_after_creation(self):
        """Child sees rules added to parent after child was created.
        This is the core fix: "always allow" on parent must be visible to child immediately."""
        # Parent adds a new rule after child is created
        self.parent.add_rule("list_dir", "allow")
        self.assertTrue(self.child.check("list_dir"))

    def test_child_sees_parent_pattern_rules_added_after_creation(self):
        """Child sees pattern rules (like outside_workspace paths) added to parent after creation."""
        # Simulate user responding "always" — rule added to parent
        self.parent.add_rule("outside_workspace:/some/path", "allow")
        rule_key = "outside_workspace:/some/path"
        self.assertEqual(self.child._get_rule(rule_key), "allow")

    def test_get_rules_merges_parent(self):
        """get_rules() returns merged parent + child rules, with child taking precedence."""
        self.parent.deny("bash")
        self.parent.add_rule("outside_workspace:/etc", "allow")
        self.child.deny("write")
        merged = self.child.get_rules()
        self.assertEqual(merged.get("bash"), "deny")
        self.assertEqual(merged.get("outside_workspace:/etc"), "allow")
        self.assertEqual(merged.get("write"), "deny")
        # Parent rules should also be included
        self.assertEqual(merged.get("read"), "allow")

    def test_child_get_rules_does_not_mutate_parent(self):
        """Modifying the merged dict from get_rules() should not affect parent or child."""
        merged = self.child.get_rules()
        merged["read"] = "deny"
        self.assertTrue(self.parent.check("read"))
        self.assertTrue(self.child.check("read"))

    def test_ask_honors_parent_blanket_rule(self):
        """Child's ask() checks parent's blanket rules before calling callback."""
        self.parent.deny("skill")
        call_count = 0

        async def callback(permission, pattern):
            nonlocal call_count
            call_count += 1
            return (True, None)

        self.child.request_callback = callback
        allowed, _ = asyncio.run(self.child.ask("skill", ["test"]))
        self.assertFalse(allowed)
        self.assertEqual(call_count, 0)

    def test_ask_honors_parent_pattern_rule(self):
        """Child's ask() checks parent's pattern rules before calling callback."""
        self.parent.add_rule("skill:test", "allow")
        call_count = 0

        async def callback(permission, pattern):
            nonlocal call_count
            call_count += 1
            return (True, None)

        self.child.request_callback = callback
        allowed, _ = asyncio.run(self.child.ask("skill", ["test"]))
        self.assertTrue(allowed)
        self.assertEqual(call_count, 0)

    def test_require_path_uses_parent_rules(self):
        """require_path on child finds rules from parent's PermissionManager."""
        self.parent.add_rule("outside_workspace:/outside/dir", "allow")
        allowed, _ = asyncio.run(
            self.child.require_path("read", "/outside/dir/sub/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_require_path_sees_parent_rules_added_via_callback(self):
        """require_path on child sees rules the parent added via "always" callback response.
        This simulates the exact bug scenario: user says "always" for a path,
        rule goes to parent, and child's next access finds it immediately."""
        # First call: no rule exists, so one is added to parent via callback
        call_state = {"count": 0}

        async def callback(permission, pattern):
            call_state["count"] += 1
            # Simulate handle_permission_respond adding rule to parent
            self.parent.add_rule(f"{permission}:{pattern}", "allow")
            return (True, None)

        self.child.request_callback = callback
        allowed, _ = asyncio.run(
            self.child.require_path("read", "/outside/new_path/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)
        self.assertEqual(call_state["count"], 1)
        # Second call: same path — should find parent's rule, no callback
        allowed, _ = asyncio.run(
            self.child.require_path("read", "/outside/new_path/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)
        self.assertEqual(call_state["count"], 1)

    def test_require_path_auto_propagation_with_parent_rule(self):
        """When child's require_path gets an "always" that's stored in parent,
        auto-propagation of parent directory rule should still work."""
        call_state = {"count": 0}

        async def callback(permission, pattern):
            call_state["count"] += 1
            self.parent.add_rule(f"{permission}:{pattern}", "allow")
            return (True, None)

        self.child.request_callback = callback
        # First access triggers callback, rule added to parent, auto-propagation runs
        allowed, _ = asyncio.run(
            self.child.require_path("read", "/outside/dir_a/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)
        # Sibling file in same dir should be auto-allowed via propagated parent rule
        allowed, _ = asyncio.run(
            self.child.require_path("read", "/outside/dir_a/other.py", "/home/user/project")
        )
        self.assertTrue(allowed)
        self.assertEqual(call_state["count"], 1)


class TestSubagentPermissionsCompose(unittest.TestCase):
    def setUp(self):
        self.parent_pm = PermissionManager()
        self.parent_pm.add_rule("read", "allow")
        self.parent_pm.add_rule("write", "allow")

    def test_compose_no_agent_deny(self):
        """Compose with no agent deny rules creates child that delegates to parent."""
        child = SubagentPermissions.compose(self.parent_pm, {})
        self.assertTrue(child.check("read"))
        self.assertTrue(child.check("write"))

    def test_compose_with_agent_deny(self):
        """Compose applies agent-level deny rules on top of parent delegation."""
        child = SubagentPermissions.compose(self.parent_pm, {"deny": ["write"]})
        self.assertTrue(child.check("read"))
        self.assertFalse(child.check("write"))

    def test_compose_child_sees_parent_updates(self):
        """Child created via compose sees rules added to parent after creation."""
        child = SubagentPermissions.compose(self.parent_pm, {})
        self.parent_pm.add_rule("list_dir", "allow")
        self.assertTrue(child.check("list_dir"))

    def test_compose_with_parent_session_permission(self):
        """Compose with parent_session_permission applies session-level denies."""
        session_pm = PermissionManager()
        session_pm.deny("bash")
        child = SubagentPermissions.compose(self.parent_pm, {}, parent_session_permission=session_pm)
        self.assertTrue(child.check("read"))
        self.assertFalse(child.check("bash"))
