from dotenv import load_dotenv
load_dotenv()

import os
import json
import sqlite3

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import BaseRequestHandler
from typing import Callable, Any, Self, override
from loguru import logger as _logger

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
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"messages": "Server is running."}
            self.wfile.write(json.dumps(response).encode())
        elif self.path == "/api/v1/providers":
            with self.server.db_conn as db:
                cursor = db.cursor()
                cursor.execute("""SELECT * FROM llm_providers""")
                rows = cursor.fetchall()
                providers = [
                    {"id": row[0], "name": row[1], 'base_url': row[2], 'api_key': row[3]} 
                    for row in rows
                ]

            response_body = json.dumps(providers).encode()
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
        data = json.loads(body)
        if self.path == "/echo":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'Received': data}).encode())
        elif self.path == "/api/v1/providers":
            _logger.info(f"Received: {data}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            config = LLMProviderConfig.model_validate(data)
            with self.server.db_conn as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """Insert INTO llm_providers (name, base_url, api_key) VALUES (?, ?, ?)""",
                    (config.name, config.base_url, config.api_key)
                )
                _logger.info(f'Inserted {config}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        # TODO: 完成 providers 的单条修改端点
        pass

    def do_DELETE(self):
        # TODO: 完成 providers 的单条删除端点
        if self.path.startswith("/api/v1/providers/"):
            # TODO: 完成 re 匹配以及逻辑编写
            pass
        pass
            
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
    db_conn = sqlite3.connect(DB_PATH, timeout=3)

    init_db(db_conn)

    server = SimpleHTTPServer(("0.0.0.0", 8000), SimpleHTTPHandler, db_conn=db_conn)
    _logger.info("Server is running at 0.0.0.0:8000.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _logger.info("Received keyboard interrupt, exiting...")