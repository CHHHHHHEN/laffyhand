import asyncio
import os
import re
import tempfile
from pathlib import Path

"""Security validations for file read/write operations.

Provides binary file detection (by extension or content heuristic),
blocked-path validation for sensitive system files, and atomic file
writing with crash-safe semantics.
"""


# --- Binary detection -----------------------------------------------------------


_BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".wasm",
        ".o",
        ".a",
        ".lib",
        ".pyc",
        ".pyd",
        ".whl",
        ".egg",
        ".class",
        ".jar",
        ".war",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".eot",
        ".db",
        ".sqlite",
        ".sqlite3",
    }
)

_PRINTABLE_RATIO_THRESHOLD = 0.7


def _printable_ratio(sample: bytes) -> float:
    """Ratio of printable characters in a byte sample.

    Tries UTF-8 decoding first — Unicode printable chars (incl. CJK,
    Arabic, etc.) count as text. Falls back to ASCII byte-range check
    on decode failure.
    """
    try:
        decoded = sample.decode("utf-8")
        printable = sum(1 for c in decoded if c.isprintable() or c in "\n\r\t")
        return printable / len(decoded)
    except UnicodeDecodeError:
        printable = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
        return printable / len(sample)


def looks_binary(path: Path, sample_size: int = 1000) -> bool:
    """Check whether *path* points to a binary file.

    Relies first on common binary extensions, then on content heuristics
    (null bytes, printable-character ratio).
    """
    if path.suffix.lower() in _BINARY_EXTENSIONS:
        return True
    try:
        with path.open("rb") as f:
            sample = f.read(sample_size)
        if not sample:
            return False
        if b"\x00" in sample:
            return True
        return _printable_ratio(sample) < _PRINTABLE_RATIO_THRESHOLD
    except Exception:
        return True


# --- Path security -------------------------------------------------------------


_blocked_write_patterns: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(^|/)[.]env(?:$|[.][a-zA-Z0-9][a-zA-Z0-9._-]*$)"),
        "writing to .env files is blocked for security",
    ),
    (
        re.compile(r"[.]git-credentials(?:[.]|$)"),
        "writing to git credentials is blocked",
    ),
    (re.compile(r"[/\\][.]ssh(?:[/\\]|$)"), "writing to SSH key paths is blocked"),
    (re.compile(r"[/\\][.]kube(?:[/\\]|$)"), "writing to kubeconfig paths is blocked"),
    (re.compile(r"[/\\][.]aws(?:[/\\]|$)"), "writing to AWS config paths is blocked"),
]


def blocked_write_path(path: Path) -> str | None:
    """Return an error message if *path* matches a blocked pattern.

    Prevents writing to sensitive locations such as .env files,
    git credentials, SSH keys, kubeconfig, and AWS config.
    """
    resolved = path.resolve()
    spath = resolved.as_posix()
    for pattern, msg in _blocked_write_patterns:
        if pattern.search(spath):
            return msg
    return None


# --- Atomic write --------------------------------------------------------------

_locks: dict[Path, asyncio.Lock] = {}
_lock_for_lock = asyncio.Lock()


async def _acquire_lock(path: Path) -> asyncio.Lock:
    async with _lock_for_lock:
        if path not in _locks:
            _locks[path] = asyncio.Lock()
        return _locks[path]


def _do_write(path: Path, content: str) -> None:
    """Synchronous write helper — runs in a thread via asyncio.to_thread."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content.encode("utf-8"))
            os.fsync(fd)
        Path(tmp).replace(path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


async def atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* with atomic semantics.

    Writes to a temporary sibling file first, then replaces the
    target — so partial writes never leave a corrupted file.
    Missing parent directories are created automatically.

    Uses a per-path asyncio.Lock so concurrent writes to the same
    path are serialised; writes to different paths run in parallel.
    """
    lock = await _acquire_lock(path)
    async with lock:
        await asyncio.to_thread(_do_write, path, content)
