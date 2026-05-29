"""简单的 MCP 测试服务器 - 提供 echo 和 time 工具"""
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import TextContent
import mcp.server.stdio
import asyncio


async def main():
    server = Server("test-mcp-server")

    @server.list_tools()
    async def handle_list_tools():
        from mcp.types import Tool
        return [
            Tool(
                name="echo",
                description="回显输入消息",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "要回显的消息"}
                    },
                    "required": ["message"],
                },
            ),
            Tool(
                name="get_time",
                description="获取当前时间",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": "时间格式",
                            "enum": ["iso", "unix", "readable"],
                        }
                    },
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        if name == "echo":
            msg = arguments.get("message", "")
            return [TextContent(type="text", text=f"Echo: {msg}")]
        elif name == "get_time":
            import time
            fmt = arguments.get("format", "iso")
            if fmt == "unix":
                text = str(time.time())
            elif fmt == "readable":
                text = time.strftime("%Y-%m-%d %H:%M:%S")
            else:
                text = time.strftime("%Y-%m-%dT%H:%M:%S")
            return [TextContent(type="text", text=text)]
        raise ValueError(f"Unknown tool: {name}")

    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read, write,
            InitializationOptions(
                server_name="test-mcp-server",
                server_version="0.1.0",
                capabilities={},
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
