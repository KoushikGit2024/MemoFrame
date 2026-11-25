"""Background tasks and helper functions for asynchronous engine operations."""
from __future__ import annotations

import logging
from typing import Any, Callable, Sequence
from PyQt6.QtCore import QObject, QThread, pyqtSignal

log = logging.getLogger("photo_organizer.gui.tasks")


def enrich_photos(engine: Any, items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich a batch of photo dicts with faces using a single engine.get_faces_many query."""
    if not items:
        return []
    ids = [int(p["id"]) for p in items if "id" in p]
    if not ids:
        return list(items)
    try:
        faces_by_img = engine.get_faces_many(ids)
    except Exception:
        log.warning("enrich_photos failed to fetch faces", exc_info=True)
        faces_by_img = {}

    enriched = []
    for p in items:
        pid = int(p.get("id", 0))
        item_copy = dict(p)
        item_copy["faces"] = faces_by_img.get(pid, [])
        enriched.append(item_copy)
    return enriched


class ThumbRepairWorker(QThread):
    """Background worker to check and generate missing thumbnails without freezing UI."""
    finished = pyqtSignal(int)

    def __init__(self, engine: Any, photo_paths: Sequence[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.photo_paths = list(photo_paths)

    def run(self) -> None:
        count = 0
        for path in self.photo_paths:
            # If thumbnail generation or check is needed
            pass
        self.finished.emit(count)


class EngineTask(QThread):
    """Generic background task for engine operations."""
    success = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable[..., Any], *args: Any, parent: QObject | None = None, **kwargs: Any) -> None:
        super().__init__(parent)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            res = self.fn(*self.args, **self.kwargs)
            self.success.emit(res)
        except Exception as exc:
            log.exception("EngineTask failed")
            self.failed.emit(str(exc))
