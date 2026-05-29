from loguru import logger


def truncate_output(text: str, max_chars: int = 2000) -> str:
    if not text or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    logger.debug(f"Truncated output: {len(text)} → {max_chars} (omitted {omitted})")
    return f"{text[:max_chars]}\n[Tool output truncated: omitted {omitted} chars]"
