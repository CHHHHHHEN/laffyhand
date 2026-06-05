"""Thin async wrappers around ripgrep subprocess calls.

Provides ``glob``, ``grep``, ``grep_files`` and ``grep_count`` with a
shared runner (``_rg_run``) that handles timeouts, error logging, and
return-code interpretation consistently.
"""

import asyncio
import shutil
from collections.abc import Sequence
from pathlib import Path

from loguru import logger


# --- Availability check -------------------------------------------------------


_RG_CACHE: bool | None = None


def rg_available() -> bool:
    global _RG_CACHE
    if _RG_CACHE is None:
        _RG_CACHE = shutil.which("rg") is not None
    return _RG_CACHE


async def _rg_run(
    args: Sequence[str],
    cwd: Path,
    timeout: int = 60,
) -> str | None:
    """Run ripgrep with a standardised set of flags.

    Returns stdout on success (including zero matches, exit code 0 or 1),
    or *None* when rg is unavailable or the call failed.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        if proc.returncode in (0, 1):
            return stdout.decode()
        logger.debug(f"ripgrep exited with code {proc.returncode}: {stderr.decode()[:200]}")
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
        logger.debug(f"ripgrep failed: {e}")
    return None


# --- Command helpers ----------------------------------------------------------


def _rg_cmd(*parts: str, include: str | None = None, exclude: str | None = None) -> list[str]:
    """Build an ``rg`` command array with common flags."""
    cmd = ["rg", *parts]
    if include:
        cmd.extend(["--glob", include])
    if exclude:
        cmd.extend(["--glob", f"!{exclude}"])
    cmd.append(".")
    return cmd


# --- Commands -----------------------------------------------------------------


async def glob(cwd: Path, pattern: str, include_ignored: bool = False) -> list[str] | None:
    """List files matching a glob pattern using ripgrep. Returns None on failure."""
    parts = ["--files", "--glob", pattern]
    if include_ignored:
        parts.append("--no-ignore")
    result = await _rg_run(_rg_cmd(*parts), cwd, timeout=30)
    if result is not None:
        return result.splitlines()
    return None


async def grep(
    cwd: Path, pattern: str, include: str | None = None, context: int = 0,
    include_ignored: bool = False, exclude: str | None = None,
) -> str | None:
    """Search file contents using ripgrep. Returns raw output or None on failure."""
    parts = ["--line-number", "--no-heading", "--color", "never", pattern]
    if context:
        parts.extend(["-C", str(context)])
    if include_ignored:
        parts.append("--no-ignore")
    result = await _rg_run(_rg_cmd(*parts, include=include, exclude=exclude), cwd)
    if result is not None:
        return result
    return None


async def grep_files(
    cwd: Path, pattern: str, include: str | None = None,
    include_ignored: bool = False, exclude: str | None = None,
) -> list[str] | None:
    """List files containing matches using ripgrep. Returns None on failure."""
    parts = ["--files-with-matches", "--color", "never", pattern]
    if include_ignored:
        parts.append("--no-ignore")
    result = await _rg_run(_rg_cmd(*parts, include=include, exclude=exclude), cwd)
    if result is not None:
        return result.splitlines()
    return None


async def grep_count(
    cwd: Path, pattern: str, include: str | None = None,
    include_ignored: bool = False, exclude: str | None = None,
) -> str | None:
    """Get per-file match counts using ripgrep. Returns raw output or None."""
    parts = ["--count", "--color", "never", pattern]
    if include_ignored:
        parts.append("--no-ignore")
    result = await _rg_run(_rg_cmd(*parts, include=include, exclude=exclude), cwd)
    if result is not None:
        return result
    return None
