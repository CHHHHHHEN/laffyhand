import shutil
import subprocess
from pathlib import Path

from loguru import logger

_RG_CACHE: bool | None = None


def rg_available() -> bool:
    global _RG_CACHE
    if _RG_CACHE is None:
        _RG_CACHE = shutil.which("rg") is not None
    return _RG_CACHE


def glob(cwd: Path, pattern: str, include_ignored: bool = False) -> list[str] | None:
    """List files matching a glob pattern using ripgrep. Returns None on failure."""
    try:
        cmd = ["rg", "--files", "--glob", pattern]
        if include_ignored:
            cmd.append("--no-ignore")
        cmd.append(".")
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"ripgrep glob failed for {pattern} in {cwd}: {e}")
    return None


def grep(
    cwd: Path, pattern: str, include: str | None = None, context: int = 0
) -> str | None:
    """Search file contents using ripgrep. Returns raw output or None on failure."""
    try:
        cmd = [
            "rg",
            "--line-number",
            "--no-heading",
            "--color",
            "never",
            "--sort",
            "modified",
            pattern,
        ]
        if include:
            cmd.extend(["--glob", include])
        if context:
            cmd.extend(["-C", str(context)])
        cmd.append(".")
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode in (0, 1):
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"ripgrep grep failed for {pattern} in {cwd}: {e}")
    return None


def grep_files(cwd: Path, pattern: str, include: str | None = None) -> list[str] | None:
    """List files containing matches using ripgrep. Returns None on failure."""
    try:
        cmd = [
            "rg",
            "--files-with-matches",
            "--color",
            "never",
            "--sort",
            "modified",
            pattern,
        ]
        if include:
            cmd.extend(["--glob", include])
        cmd.append(".")
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode in (0, 1):
            return result.stdout.splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"ripgrep grep_files failed for {pattern} in {cwd}: {e}")
    return None


def grep_count(cwd: Path, pattern: str, include: str | None = None) -> str | None:
    """Get per-file match counts using ripgrep. Returns raw output or None."""
    try:
        cmd = ["rg", "--count", "--color", "never", "--sort", "modified", pattern]
        if include:
            cmd.extend(["--glob", include])
        cmd.append(".")
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode in (0, 1):
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"ripgrep grep_count failed for {pattern} in {cwd}: {e}")
    return None
