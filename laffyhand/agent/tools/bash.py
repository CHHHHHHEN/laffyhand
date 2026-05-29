import asyncio
import re
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool

_SENSITIVE_PATTERNS = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|credential|auth[_-]?token|access[_-]?key|private[_-]?key)"
    r"(\s*[:=]\s*)\S+",
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+\S+")
_ENV_VAR_PATTERN = re.compile(
    r"(?i)^\s*export\s+(?:[A-Z_]*API[_-]?KEY|[A-Z_]*TOKEN|[A-Z_]*SECRET|[A-Z_]*PASSWORD)\s*=\s*\S+",
)


def _redact_command(command: str) -> str:
    redacted = _SENSITIVE_PATTERNS.sub(r"\1\2***", command)
    redacted = _BEARER_PATTERN.sub("Bearer ***", redacted)
    if _ENV_VAR_PATTERN.search(redacted):
        redacted = "export <redacted env var>"
    return redacted


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
                "workdir": {
                    "type": "string",
                    "description": "Working directory for the command (default: current directory)",
                },
            },
            "required": ["command"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        command = params["command"]
        timeout_ms = params.get("timeout")
        if timeout_ms is None:
            timeout_ms = 120000
        timeout = timeout_ms / 1000
        workdir = params.get("workdir")
        logger.info(f"Bash: {_redact_command(command)}")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                logger.warning(f"Bash timed out after {timeout}s: {_redact_command(command)}")
                return f"Command timed out after {timeout}s"

            output = stdout.decode(errors="replace")
            if stderr:
                output += stderr.decode(errors="replace")
            if proc.returncode != 0:
                output = f"Exit code: {proc.returncode}\n{output}"
            return output.strip()
        except Exception as e:
            logger.error(f"Bash exception on cmd={_redact_command(command)!r}, timeout={timeout}s, workdir={workdir!r}: {e}")
            return f"Error: {e}"
