import subprocess
from typing import Any

from laffyhand.agent.schemas import ToolResultContent
from laffyhand.agent.tools.base import BaseTool


class BashTool(BaseTool):
    name = "bash"
    description = "Execute a shell command."
    max_result_size = 50000

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the command (5-10 words)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds (default: 120000)",
                },
            },
            "required": ["command"],
        }

    def run(self, params: dict[str, Any]) -> ToolResultContent:
        command = params["command"]
        timeout = (params.get("timeout") or 120000) / 1000

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += result.stderr
            if result.returncode != 0:
                output = f"Exit code: {result.returncode}\n{output}"
            return ToolResultContent(
                tool_call_id="", tool_name=self.name,
                result=output.strip(),
            )
        except subprocess.TimeoutExpired:
            return ToolResultContent(
                tool_call_id="", tool_name=self.name,
                result=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return ToolResultContent(
                tool_call_id="", tool_name=self.name,
                result=f"Error: {e}",
            )
