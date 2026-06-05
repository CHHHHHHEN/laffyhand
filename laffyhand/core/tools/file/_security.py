import os
import re
import tempfile
from pathlib import Path


BINARY_EXTENSIONS = frozenset(
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


def looks_binary(path: Path, sample_size: int = 1000) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with path.open("rb") as f:
            sample = f.read(sample_size)
        if not sample:
            return False
        if b"\x00" in sample:
            return True
        # Check for valid UTF-8 with non-ASCII multi-byte characters
        # (e.g. Chinese, Japanese, Arabic — these are text, not binary)
        try:
            decoded = sample.decode("utf-8")
            printable_unicode = sum(
                1 for c in decoded if c.isprintable() or c in "\n\r\t"
            )
            if printable_unicode / len(decoded) >= 0.7:
                return False
        except UnicodeDecodeError:
            pass
        printable = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
        return printable / len(sample) < 0.7
    except Exception:
        return True


BLOCKED_WRITE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
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
    resolved = path.resolve()
    spath = str(resolved).replace("\\", "/")
    for pattern, msg in BLOCKED_WRITE_PATTERNS:
        if pattern.search(spath):
            return msg
    return None


def atomic_write(path: Path, content: str) -> None:
    """Write content atomically using a temporary file."""
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
