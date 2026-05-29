import unittest
from laffyhand.agent.tools.permission import PermissionManager


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
        pm.allow("bash")
        self.assertTrue(pm.check("bash"))

    def test_deny_one_not_others(self):
        pm = PermissionManager()
        pm.deny("bash")
        self.assertTrue(pm.check("read"))
