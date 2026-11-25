"""Progress events, pause/cancel and the memory guard for a pipeline run."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from utils.logger import get_logger
from utils.system_info import available_memory_mb

log = get_logger("processing.control")


@dataclass(frozen=True)
class ProgressEvent:
    """One progress update. ``stage``: scan | process | duplicates | groups | waiting | done."""

    stage: str
    done: int = 0
    total: int = 0
    failed: int = 0
    current: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProgressCallback = Callable[[ProgressEvent], None]


class RunControl:
    """Thread-safe handle shared by the pipeline and the caller (e.g. the app)."""

    def __init__(
        self, on_progress: ProgressCallback | None = None, min_free_mem_mb: int = 0
    ) -> None:
        self._on_progress = on_progress
        self.min_free_mem_mb = min_free_mem_mb
        self._cancel = threading.Event()
        self._running = threading.Event()
        self._running.set()
        self._waiting: str | None = None

    def reset(self) -> None:
        """Clear cancel/pause state before a new run."""
        self._cancel.clear()
        self._running.set()
        self._waiting = None

    def set_callback(self, callback: ProgressCallback | None) -> None:
        """Replace the progress callback (safe to call between runs)."""
        self._on_progress = callback

    def cancel(self) -> None:
        self._cancel.set()

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    def emit(self, event: ProgressEvent) -> None:
        """Deliver an event. A failing callback never breaks processing."""
        if self._on_progress is None:
            return
        try:
            self._on_progress(event)
        except Exception:  # noqa: BLE001
            log.exception("progress callback failed")

    def _note(self, reason: str | None) -> None:
        if reason == self._waiting:
            return
        previous, self._waiting = self._waiting, reason
        if reason:
            self.emit(ProgressEvent("waiting", message=reason))
        elif previous:
            self.emit(ProgressEvent("waiting", message="resumed"))

    def checkpoint(self) -> bool:
        """Block while paused or memory is low. Returns False if cancelled."""
        while True:
            if self._cancel.is_set():
                return False
            if not self._running.is_set():
                self._note("paused")
                time.sleep(0.2)
                continue
            if self.min_free_mem_mb:
                free = available_memory_mb()
                if free is not None and free < self.min_free_mem_mb:
                    self._note("low memory")
                    time.sleep(1.0)
                    continue
            self._note(None)
            return True
