from __future__ import annotations

import logging
import sys

import structlog


def setup_logging() -> None:
    """
    Configure application logging.
    """

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    # HTTP request URLs can contain credentials such as Telegram bot tokens.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(
                fmt="iso",
            ),
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str):
    """
    Returns structured logger.
    """

    return structlog.get_logger(name)
