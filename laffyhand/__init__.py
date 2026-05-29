import os
import sys
from loguru import logger

_LOGGING_INITIALIZED = False


def setup_logging(
    log_dir: str = "logs",
    level: str = "INFO",
    retention: int = 10,
    console: bool = False,
) -> None:
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED:
        return
    logger.remove()
    log_dir = os.getenv("LOG_DIR", log_dir)
    level = os.getenv("LOG_LEVEL", level)
    try:
        retention = int(os.getenv("LOG_RETENTION", str(retention)))
    except (TypeError, ValueError):
        retention = 10
    console = os.getenv("LOG_CONSOLE", "false").lower() in ("1", "true", "yes")
    os.makedirs(log_dir, exist_ok=True)

    logger.add(
        os.path.join(log_dir, "laffyhand_{time:YYYY-MM-DD}.log"),
        level=level,
        retention=retention,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {module}:{function}:{line} | {message}",
        encoding="utf-8",
        enqueue=True,
    )

    if console:
        logger.add(
            sys.stderr,
            level=level,
            format="<level>{level:<7}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
        )
    _LOGGING_INITIALIZED = True
