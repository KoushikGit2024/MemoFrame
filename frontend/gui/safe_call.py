"""Safe execution helper for GUI view slots and operations."""
from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

from PyQt6.QtWidgets import QMessageBox, QWidget

from engine.errors import EngineError

log = logging.getLogger("photo_organizer.gui")
T = TypeVar("T")


def safe_call(parent: Any, fn: Callable[..., T], *args: Any, default: T | None = None, **kwargs: Any) -> T | None:
    """Safely call an engine function within parent's lock and surface engine errors cleanly."""
    lock = getattr(parent, "lock", None) or getattr(parent, "engine_lock", None)
    try:
        if lock is not None:
            with lock:
                return fn(*args, **kwargs)
        return fn(*args, **kwargs)
    except EngineError as e:
        log.error(
            "%s(%r) -> %s", getattr(fn, "__name__", fn), args, e.to_dict(), exc_info=True
        )
        msg_box_parent = parent if isinstance(parent, QWidget) else None
        QMessageBox.warning(msg_box_parent, "Error", f"{e.message}\n{e.hint}")
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected error in %s", getattr(fn, "__name__", fn), exc_info=True)
        msg_box_parent = parent if isinstance(parent, QWidget) else None
        QMessageBox.critical(msg_box_parent, "Error", f"Unexpected error: {exc}")
    return default
