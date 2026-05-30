import os
import re
import tempfile
from pathlib import Path


BINARY_EXTENSIONS = frozenset({
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico',
    '.pdf', '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.exe', '.dll', '.so', '.dylib', '.wasm', '.o', '.a', '.lib',
    '.pyc', '.pyd', '.whl', '.egg',
    '.class', '.jar', '.war',
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm',
    '.ttf', '.otf', '.woff', '.woff2', '.eot',
    '.db', '.sqlite', '.sqlite3',
})


def looks_binary(path: Path, sample_size: int = 1000) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with path.open('rb') as f:
            sample = f.read(sample_size)
        if not sample:
            return False
        if b'\x00' in sample:
            return True
        printable = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
        return printable / len(sample) < 0.7
    except Exception:
        return False


BLOCKED_WRITE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'(^|/)\.env(\.|$)'), 'writing to .env files is blocked for security'),
    (re.compile(r'\.git-credentials$'), 'writing to git credentials is blocked'),
    (re.compile(r'[/\\]\.ssh[/\\]'), 'writing to SSH key paths is blocked'),
    (re.compile(r'[/\\]\.kube[/\\]'), 'writing to kubeconfig paths is blocked'),
    (re.compile(r'[/\\]\.aws[/\\]'), 'writing to AWS config paths is blocked'),
]


def blocked_write_path(path: Path) -> str | None:
    spath = str(path)
    for pattern, msg in BLOCKED_WRITE_PATTERNS:
        if pattern.search(spath):
            return msg
    return None


def detect_line_ending(path: Path, sample_size: int = 4096) -> str:
    """Detect whether a file uses \\r\\n or \\n line endings."""
    try:
        with path.open("rb") as f:
            sample = f.read(sample_size)
        crlf = sample.count(b"\r\n")
        lf = sample.count(b"\n") - crlf
        return "\r\n" if crlf > lf else "\n"
    except Exception:
        return "\n"


def normalize_newlines(text: str, line_ending: str) -> str:
    """Normalize internal newlines to the target line ending."""
    if line_ending == "\n":
        return text.replace("\r\n", "\n")
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def atomic_write(path: Path, content: str) -> None:
    """Write content atomically using a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp).replace(path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
