from dotenv import load_dotenv
load_dotenv()

import os
import json
import sqlite3

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import BaseRequestHandler
from typing import Callable, Any, Self, override
from loguru import logger

from laffyhand import setup_logging
from laffyhand.agent.schemas import LLMProviderConfig

DB_PATH = os.environ['DB_PATH']

class SimpleHTTPServer(HTTPServer):
    @override
    def __init__(
        self, 
        server_address: tuple[str | bytes | bytearray, int] | tuple[str | bytes | bytearray, int, int, int], 
        RequestHandlerClass: Callable[[Any, Any, Self], BaseRequestHandler], 
        db_conn: sqlite3.Connection,
        bind_and_activate: bool = True, 
    ) -> None:
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)
        self.db_conn = db_conn

class SimpleHTTPHandler(BaseHTTPRequestHandler):
    server: SimpleHTTPServer # FIXME: 暂时找不到更好的 db 注入方法

    def do_GET(self):
        if self.path == "/health":
            logger.debug("Health check requested")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"messages": "Server is running."}
            self.wfile.write(json.dumps(response).encode())
        elif self.path == "/api/v1/providers":
            try:
                with self.server.db_conn as db:
                    cursor = db.cursor()
                    cursor.execute("""SELECT * FROM llm_providers""")
                    rows = cursor.fetchall()
            except sqlite3.Error:
                logger.error("Database query failed in GET /api/v1/providers")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Database query failed"}).encode())
                return
            try:
                providers = [
                    {"id": row[0], "name": row[1], 'base_url': row[2], 'api_key': row[3]}
                    for row in rows
                ]
                response_body = json.dumps(providers).encode()
            except (TypeError, ValueError, OverflowError):
                logger.error("Failed to serialize provider list to JSON")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Failed to serialize provider data"}).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response_body)
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in POST body")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
            return
        if self.path == "/echo":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'Received': data}).encode())
        elif self.path == "/api/v1/providers":
            logger.info(f"Received POST /api/v1/providers: name={data.get('name')}, base_url={data.get('base_url')}")

            try:
                config = LLMProviderConfig.model_validate(data)
            except Exception:
                logger.warning("Provider config validation failed")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid provider config"}).encode())
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
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Database insert failed"}).encode())
                return

            logger.info(f"Inserted provider: name={config.name}, base_url={config.base_url}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        logger.warning(f"PUT {self.path} not implemented")
        self.send_response(501)
        self.end_headers()

    def do_DELETE(self):
        if self.path.startswith("/api/v1/providers/"):
            # TODO: 完成 re 匹配以及逻辑编写
            logger.warning(f"DELETE {self.path} not implemented")
            self.send_response(501)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()
            
def init_db(db_conn: sqlite3.Connection) -> None:
    with db_conn: # with connection 能够自动完成 commit 和 rollback
        cursor = db_conn.cursor()
        cursor.execute(
    """CREATE TABLE IF NOT EXISTS llm_providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, -- LLM 提供商的唯一ID
        name TEXT NOT NULL, -- 供人类查看的 LLM 提供商名称
        base_url TEXT NOT NULL, -- 提供商的 base url, 一般为 xxx/v1
        api_key TEXT NOT NULL -- 访问提供商服务的密钥 sk-xxx
    )""")
        
if __name__ == "__main__":
    setup_logging()

    try:
        db_conn = sqlite3.connect(DB_PATH, timeout=3)
    except sqlite3.OperationalError:
        logger.critical(f"Failed to connect to database at {DB_PATH}")
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