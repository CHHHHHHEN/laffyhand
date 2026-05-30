import sys
import json
import sqlite3

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import BaseRequestHandler
from typing import Callable, Any, Self, override
from loguru import logger

from laffyhand import setup_logging
from laffyhand.config import load_config
from laffyhand.agent.llm.specs import LLMProviderConfig


class SimpleHTTPServer(HTTPServer):
    @override
    def __init__(
        self,
        server_address: tuple[str | bytes | bytearray, int]
        | tuple[str | bytes | bytearray, int, int, int],
        RequestHandlerClass: Callable[[Any, Any, Self], BaseRequestHandler],
        db_conn: sqlite3.Connection,
        bind_and_activate: bool = True,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)
        self.db_conn = db_conn


class SimpleHTTPHandler(BaseHTTPRequestHandler):
    server: SimpleHTTPServer

    def _send_json(self, status: int, data: dict | list) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def _safe_log(
        self, action: str, data: dict, safe_keys: tuple[str, ...] = ("name", "base_url")
    ) -> str:
        safe = {k: v for k, v in data.items() if k in safe_keys}
        safe["action"] = action
        logger.info(f"Provider {action}: {safe}")
        return action

    def do_GET(self):
        if self.path == "/health":
            logger.debug("Health check requested")
            self._send_json(200, {"messages": "Server is running."})
        elif self.path == "/api/v1/providers":
            try:
                with self.server.db_conn as db:
                    cursor = db.cursor()
                    cursor.execute("""SELECT * FROM llm_providers""")
                    rows = cursor.fetchall()
            except sqlite3.Error:
                logger.error("Database query failed in GET /api/v1/providers")
                self._send_json(500, {"error": "Database query failed"})
                return
            try:
                providers = [
                    {"id": row[0], "name": row[1], "base_url": row[2]} for row in rows
                ]
            except (TypeError, ValueError, OverflowError):
                logger.error("Failed to serialize provider list to JSON")
                self._send_json(500, {"error": "Failed to serialize provider data"})
                return
            self._send_json(200, providers)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in POST body")
            self._send_json(400, {"error": "Invalid JSON"})
            return
        if self.path == "/echo":
            self._send_json(200, {"Received": data})
        elif self.path == "/api/v1/providers":
            self._safe_log("received", data)

            try:
                config = LLMProviderConfig.model_validate(data)
            except Exception:
                logger.warning("Provider config validation failed")
                self._send_json(400, {"error": "Invalid provider config"})
                return

            try:
                with self.server.db_conn as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """Insert INTO llm_providers (name, base_url, api_key) VALUES (?, ?, ?)""",
                        (config.name, config.base_url, config.api_key),
                    )
            except sqlite3.Error:
                logger.error("Database insert failed in POST /api/v1/providers")
                self._send_json(500, {"error": "Database insert failed"})
                return

            logger.info(
                f"Inserted provider: name={config.name}, base_url={config.base_url}"
            )
            self._send_json(200, {"status": "ok"})
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        logger.warning(f"PUT {self.path} not implemented")
        self.send_response(501)
        self.end_headers()

    def do_DELETE(self):
        if self.path.startswith("/api/v1/providers/"):
            logger.warning(f"DELETE {self.path} not implemented")
            self.send_response(501)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()


def init_db(db_conn: sqlite3.Connection) -> None:
    with db_conn:
        cursor = db_conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS llm_providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        base_url TEXT NOT NULL,
        api_key TEXT NOT NULL
    )"""
        )


if __name__ == "__main__":
    config = load_config()
    logger.warning(
        "SECURITY: API keys are stored in SQLite in plaintext. "
        "This server is intended for development/testing only."
    )
    setup_logging(
        log_dir=config.logging.dir,
        level=config.logging.level,
        retention=config.logging.retention_days,
        console=config.logging.console,
    )

    db_path = config.db.path
    try:
        db_conn = sqlite3.connect(db_path, timeout=3)
    except sqlite3.OperationalError:
        logger.critical(f"Failed to connect to database at {db_path}")
        raise

    try:
        init_db(db_conn)
    except sqlite3.Error:
        logger.critical("Failed to initialize database schema")
        raise

    server = SimpleHTTPServer(("0.0.0.0", 8000), SimpleHTTPHandler, db_conn=db_conn)
    logger.info("Server is running at 0.0.0.0:8000.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, exiting...")
    except Exception:
        logger.exception("Server crashed")
        sys.exit(1)
