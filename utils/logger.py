"""Logging setup: console (tqdm-safe) plus rotating file log."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from tqdm import tqdm

ROOT_LOGGER_NAME = "photo_organizer"
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"


class _TqdmHandler(logging.StreamHandler):
    """Writes through ``tqdm.write`` so log lines don't break progress bars."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record), file=self.stream)
        except Exception:  # noqa: BLE001 - logging must never raise
            self.handleError(record)


def setup_logging(
    log_file: Path | None = None,
    verbose: bool = False,
    quiet: bool = False,
) -> logging.Logger:
    """Configure the package logger. Safe to call more than once.

    Args:
        log_file: Optional path for a rotating file log (always DEBUG level).
        verbose: Console shows DEBUG instead of INFO.
        quiet: Console shows only WARNING and above.
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    console_level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO
    console = _TqdmHandler(stream=sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter(_FORMAT, _DATE_FORMAT))
    logger.addHandler(console)

    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(_FORMAT))
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.warning("Could not open log file %s: %s", log_file, exc)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger, e.g. ``get_logger("core.scanner")``."""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")