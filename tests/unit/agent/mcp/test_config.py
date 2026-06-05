import unittest

from laffyhand.core.mcp.config import LocalMCPConfig, RemoteMCPConfig


class TestLocalMCPConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = LocalMCPConfig(command=["python", "server.py"])
        self.assertEqual(cfg.type, "local")
        self.assertEqual(cfg.command, ["python", "server.py"])
        self.assertEqual(cfg.env, {})
        self.assertEqual(cfg.timeout, 300)

    def test_with_env(self):
        cfg = LocalMCPConfig(command=["node", "index.js"], env={"KEY": "val"})
        self.assertEqual(cfg.env, {"KEY": "val"})


class TestRemoteMCPConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = RemoteMCPConfig(url="http://localhost:8080/sse")
        self.assertEqual(cfg.type, "remote")
        self.assertIsNone(cfg.transport)
        self.assertEqual(cfg.headers, {})
        self.assertEqual(cfg.timeout, 300)

    def test_explicit_transport(self):
        cfg = RemoteMCPConfig(
            url="http://localhost:8080/mcp", transport="streamable-http"
        )
        self.assertEqual(cfg.transport, "streamable-http")

    def test_with_headers(self):
        cfg = RemoteMCPConfig(
            url="http://localhost", headers={"Authorization": "Bearer token"}
        )
        self.assertEqual(cfg.headers["Authorization"], "Bearer token")
