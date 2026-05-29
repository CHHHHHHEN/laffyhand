import os
from loguru import logger


def setup_logging(
    log_dir: str = "logs",
    level: str = "INFO",
    retention: int = 10,
) -> None:
    logger.remove()
    log_dir = os.getenv("LOG_DIR", log_dir)
    level = os.getenv("LOG_LEVEL", level)
    os.makedirs(log_dir, exist_ok=True)

    logger.add(
        os.path.join(log_dir, "laffyhand_{time:YYYY-MM-DD_HH-mm-ss}.log"),
        level=level,
        retention=f"{retention} files",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {module}:{function}:{line} | {message}",
        encoding="utf-8",
        enqueue=True,
    )
