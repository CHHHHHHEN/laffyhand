import os
import sys
from loguru import logger

_LOGGING_INITIALIZED = False

_COUNTER_FILENAME = ".laffyhand_counter"


def _next_launch_number(log_dir: str) -> int:
    counter_path = os.path.join(log_dir, _COUNTER_FILENAME)
    n = 1
    if os.path.isfile(counter_path):
        try:
            with open(counter_path) as f:
                n = int(f.read().strip()) + 1
        except (ValueError, OSError):
            n = 1
    with open(counter_path, "w") as f:
        f.write(str(n))
    return n


def setup_logging(
    log_dir: str = "logs",
    level: str = "INFO",
    retention: int = 10,
    console: bool = True,
) -> None:
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED:
        return
    logger.remove()
    os.makedirs(log_dir, exist_ok=True)

    launch_no = _next_launch_number(log_dir)

    logger.add(
        os.path.join(log_dir, f"laffyhand_{launch_no:04d}.log"),
        level=level,
        retention=retention,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {module}:{function}:{line} | {message}\n{exception}",
        encoding="utf-8",
        enqueue=False,
    )

    if console:
        logger.add(
            sys.stderr,
            level=level,
            format="<level>{level:<7}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
        )
    _LOGGING_INITIALIZED = True
