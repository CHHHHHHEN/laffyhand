import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from loguru import logger

_RG_CACHE: bool | None = None


def rg_available() -> bool:
    global _RG_CACHE
    if _RG_CACHE is None:
        _RG_CACHE = shutil.which("rg") is not None
    return _RG_CACHE


def _rg_run(
    args: Sequence[str],
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str] | None:
    """Run ripgrep with a standardised set of flags.

    Returns *None* when rg is unavailable or the call failed.
    """
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode in (0, 1):
            return result
        logger.debug(f"ripgrep exited with code {result.returncode}: {result.stderr[:200]}")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"ripgrep failed: {e}")
    return None


def glob(cwd: Path, pattern: str, include_ignored: bool = False) -> list[str] | None:
    """List files matching a glob pattern using ripgrep. Returns None on failure."""
    cmd = ["rg", "--files", "--glob", pattern]
    if include_ignored:
        cmd.append("--no-ignore")
    cmd.append(".")
    result = _rg_run(cmd, cwd, timeout=30)
    if result is not None:
        return result.stdout.splitlines()
    return None


def grep(
    cwd: Path, pattern: str, include: str | None = None, context: int = 0
) -> str | None:
    """Search file contents using ripgrep. Returns raw output or None on failure."""
    cmd = [
        "rg",
        "--line-number",
        "--no-heading",
        "--color",
        "never",
        pattern,
    ]
    if include:
        cmd.extend(["--glob", include])
    if context:
        cmd.extend(["-C", str(context)])
    cmd.append(".")
    result = _rg_run(cmd, cwd)
    if result is not None:
        return result.stdout
    return None


def grep_files(cwd: Path, pattern: str, include: str | None = None) -> list[str] | None:
    """List files containing matches using ripgrep. Returns None on failure."""
    cmd = [
        "rg",
        "--files-with-matches",
        "--color",
        "never",
        pattern,
    ]
    if include:
        cmd.extend(["--glob", include])
    cmd.append(".")
    result = _rg_run(cmd, cwd)
    if result is not None:
        return result.stdout.splitlines()
    return None


def grep_count(cwd: Path, pattern: str, include: str | None = None) -> str | None:
    """Get per-file match counts using ripgrep. Returns raw output or None."""
    cmd = ["rg", "--count", "--color", "never", pattern]
    if include:
        cmd.extend(["--glob", include])
    cmd.append(".")
    result = _rg_run(cmd, cwd)
    if result is not None:
        return result.stdout
    return None
