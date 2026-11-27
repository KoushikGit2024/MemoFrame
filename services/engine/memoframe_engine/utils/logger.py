"""Logging setup: console (tqdm-safe) plus rotating file log."""

from __future__ import annotations

from datetime import datetime
import faulthandler
import logging
import sys
import threading
import traceback
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
    if sys.stderr is not None:
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


_crash_fh = None


def install_crash_logging(workspace: Path) -> None:
    """Send uncaught exceptions (main + threads) and native crashes (segfault in
    OpenCV/ONNX/Qt) to the workspace logs. Call once, as early as possible."""
    global _crash_fh
    log = get_logger("crash")

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical(
            "Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb))
        )

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        _crash_fh = open(workspace / "native_crash.log", "a", encoding="utf-8")
        _crash_fh.write(f"\n--- session start {datetime.now().isoformat(timespec='seconds')} ---\n")
        _crash_fh.flush()
        faulthandler.enable(file=_crash_fh, all_threads=True)  # keep the handle open
    except OSError as exc:
        log.warning("Native crash log unavailable: %s", exc)


def setup_worker_logging(workspace: Path) -> None:
    """Worker processes (spawn) start with no logging config. Give each one a plain
    append-mode file: rotation from several processes breaks on Windows."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    if any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        return
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        h = logging.FileHandler(workspace / "photo_organizer.workers.log", encoding="utf-8")
        h.setFormatter(logging.Formatter(_FORMAT + " | pid=%(process)d"))
        logger.addHandler(h)
    except OSError:
        pass
