"""
Logging Configuration
=====================
Configures loguru for structured, rotating log files and rich console output.
All modules should import `logger` from this module rather than using loguru directly.
"""

import sys
from pathlib import Path

from loguru import logger
from rich.console import Console

# Rich console for structured output
console = Console()


def setup_logging(log_dir: str | Path = "logs", level: str = "INFO") -> None:
    """
    Configure loguru with:
    - Rich-formatted console output (colored, readable)
    - Rotating daily log file for INFO+ messages
    - Separate error log for WARNING+ messages

    Call this once at application startup from main.py.

    Args:
        log_dir: Directory where log files will be written.
        level: Minimum log level for console output.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    # Remove default loguru handler
    logger.remove()

    # Console handler — pretty output via loguru's built-in colorizer
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        enqueue=True,  # Thread-safe
    )

    # Main log file — daily rotation, 30-day retention
    logger.add(
        log_path / "scraper_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",      # Rotate at midnight
        retention="30 days",   # Keep 30 days of logs
        compression="zip",     # Compress old files
        enqueue=True,
    )

    # Error-only log file — never rotated, kept permanently
    logger.add(
        log_path / "errors.log",
        level="WARNING",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}\n{exception}",
        retention="90 days",
        enqueue=True,
    )

    logger.info("Logging initialized. Log directory: {}", log_dir)


# Export the configured logger for import by all modules
__all__ = ["logger", "console", "setup_logging"]
