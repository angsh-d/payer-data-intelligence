"""Logging configuration using structlog. All logs go to ./tmp/ directory."""
import logging
import sys
from pathlib import Path
from typing import Optional

import structlog


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None
) -> None:
    """
    Configure structured logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log filename (will be created in ./tmp/)
    """
    # Ensure tmp directory exists
    tmp_dir = Path("./tmp")
    tmp_dir.mkdir(exist_ok=True)

    # Configure standard logging
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_path = tmp_dir / log_file
        handlers.append(logging.FileHandler(log_path))

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
        handlers=handlers,
        force=True
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if log_file is None else structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
