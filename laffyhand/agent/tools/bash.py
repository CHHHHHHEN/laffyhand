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

_DANGEROUS_COMMANDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(-rf?|--recursive)\s+/\s*(\s|$)"), "rm -rf / is blocked"),
    (re.compile(r"\brm\s+(-rf?|--recursive)\s+/\S"), "rm -rf on / paths is blocked"),
    (re.compile(r"\bmkfs\b"), "mkfs is blocked"),
    (re.compile(r"\bdd\s+if="), "dd with if= is blocked"),
    (re.compile(r"\bchmod\b"), "chmod is blocked"),
    (re.compile(r"\bchown\s+"), "chown is blocked (use chmod instead)"),
    (
        re.compile(r"(?<!\S)>\s*/"),
        "direct file redirect (>) is blocked; use the file tools",
    ),
    (
        re.compile(r"(?<!\S)>>\s*/"),
        "direct file append (>>) is blocked; use the file tools",
    ),
    (re.compile(r"\bmv\s+/\s+"), "moving / is blocked"),
    (
        re.compile(r"\b(curl|wget|fetch)\b"),
        "network download tool is blocked (data exfiltration risk)",
    ),
    (
        re.compile(r"\bperl\s+-e\b"),
        "inline perl execution is blocked",
    ),
    (
        re.compile(r"\bruby\s+-e\b"),
        "inline ruby execution is blocked",
    ),
    (
        re.compile(r"\bnode\s+-e\b"),
        "inline node execution is blocked",
    ),
    (re.compile(r"\bdeno\s+eval\b"), "deno eval is blocked (arbitrary code execution)"),
    (re.compile(r"\bsudo\b"), "sudo is blocked (privilege escalation)"),
    (
        re.compile(r"\b(ssh|scp|sftp|rsync)\b"),
        "network transfer tool is blocked (network egress)",
    ),
    (re.compile(r"\b(nc|ncat)\b"), "netcat is blocked (network connection)"),
    (re.compile(r"\btelnet\b"), "telnet is blocked (network connection)"),
    (
        re.compile(r"\bbase64\s+-(d|-decode)\b"),
        "base64 decode is blocked (encoded payload)",
    ),
    (re.compile(r"\bpasswd\b"), "passwd is blocked (password changes)"),
    (re.compile(r"\bsu\b"), "su is blocked (switch user)"),
    (re.compile(r"\|\s*(sh|bash|zsh)\b"), "pipe to shell is blocked"),
]

# Regex to detect inline Python execution (python -c or python3 -c)
_INLINE_PYTHON_RE = re.compile(r"\bpython[23]?\s+-c\b")

# Dangerous Python operations to scan for in inline scripts
# Matches write operations, code execution, subprocess, and network access
_DANGEROUS_PYTHON_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\beval\s*\("), "eval() in inline Python is blocked"),
    (re.compile(r"\bexec\s*\("), "exec() in inline Python is blocked"),
    (re.compile(r"\bcompile\s*\("), "compile() in inline Python is blocked"),
    (re.compile(r"\bos\.system\s*\("), "os.system() in inline Python is blocked"),
    (re.compile(r"\bos\.popen\s*\("), "os.popen() in inline Python is blocked"),
    (re.compile(r"\bsubprocess\.\w+\s*\("), "subprocess.*() in inline Python is blocked"),
    (re.compile(r"\bshutil\.\w+\s*\("), "shutil.*() in inline Python is blocked"),
    (re.compile(r"\bopen\s*\([^)]*['\"][waxb+]"), "file write mode in inline Python is blocked; use the file tools"),
    (re.compile(r"\bPath\s*\([^)]*\)\s*\.\s*(write_text|write_bytes|unlink|rmdir|mkdir)\s*\("), "Path write operations in inline Python are blocked; use the file tools"),
    (re.compile(r"\bsocket\.\w+\s*\("), "socket operations in inline Python are blocked (network egress)"),
    (re.compile(r"\b__import__\s*\("), "dynamic imports in inline Python are blocked"),
    (re.compile(r"\bimportlib\."), "importlib in inline Python is blocked"),
    (re.compile(r"\bbase64\s*\.\s*(b64decode|decode)\s*\("), "base64 decode in inline Python is blocked (encoded payload)"),
]


def _extract_inline_code(command: str) -> str | None:
    """Extract the Python code from a `python[3] -c "..."` command.

    Returns the code string if found, or None if this isn't an inline Python command.
    """
    m = _INLINE_PYTHON_RE.search(command)
    if not m:
        return None
    # Find the quoted string after -c
    rest = command[m.end():].lstrip()
    if not rest:
        return None
    # Handle single or double quotes
    quote_char = rest[0]
    if quote_char not in ('"', "'"):
        return None
    # Find the closing quote
    end = rest.find(quote_char, 1)
    if end == -1:
        return None
    return rest[1:end]


def _check_inline_python(command: str) -> str | None:
    """Check inline Python code for dangerous patterns.

    Returns None if safe, or an error message if blocked.
    """
    code = _extract_inline_code(command)
    if code is None:
        return None
    for pattern, msg in _DANGEROUS_PYTHON_PATTERNS:
        if pattern.search(code):
            return f"Blocked: {msg}"
    return None


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

    def _input_schema(self) -> dict[str, Any]:
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

        # Check for dangerous patterns in inline Python scripts
        python_blocked = _check_inline_python(command)
        if python_blocked is not None:
            logger.warning(f"Bash blocked: {python_blocked}: {_redact_command(command)}")
            return python_blocked

        for pattern, msg in _DANGEROUS_COMMANDS:
            if pattern.search(command):
                logger.warning(f"Bash blocked: {msg}: {_redact_command(command)}")
                return f"Blocked: {msg}"

        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=2)
                except asyncio.TimeoutError:
                    pass
                logger.warning(
                    f"Bash timed out after {timeout}s: {_redact_command(command)}"
                )
                return f"Command timed out after {timeout}s"

            output = stdout.decode(errors="replace")
            if stderr:
                output += stderr.decode(errors="replace")
            if proc.returncode != 0:
                output = f"Exit code: {proc.returncode}\n{output}"
            return output.strip()
        except Exception as e:
            logger.error(
                f"Bash exception on cmd={_redact_command(command)!r}, timeout={timeout}s, workdir={workdir!r}: {e}"
            )
            return "Error: command execution failed"
        finally:
            if proc is not None and proc.returncode is None:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=2)
                except (asyncio.TimeoutError, ProcessLookupError):
                    pass
