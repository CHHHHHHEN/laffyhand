"""Line-ending detection and normalisation.

Provides ``detect_line_ending()`` to auto-detect CRLF vs LF for a file,
and ``normalize_newlines()`` to convert between the two.
"""

from pathlib import Path


def detect_line_ending(path: Path, sample_size: int = 4096) -> str:
    try:
        with path.open("rb") as f:
            sample = f.read(sample_size)
        crlf = sample.count(b"\r\n")
        lf = sample.count(b"\n") - crlf
        return "\r\n" if crlf > lf else "\n"
    except Exception:
        return "\n"


def normalize_newlines(text: str, line_ending: str) -> str:
    if line_ending == "\n":
        return text.replace("\r\n", "\n")
    return text.replace("\r\n", "\n").replace("\n", "\r\n")
