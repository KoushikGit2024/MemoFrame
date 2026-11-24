"""Watch mode: poll folders (read-only) and process new or changed photos when they are stable.

Nothing is ever written next to the photos. Offline folders are skipped, and nothing is marked
missing here.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Sequence

from memoframe.config import Settings
from memoframe.core.scanner import iter_image_files
from memoframe.database import DatabaseManager
from memoframe.processing.control import ProgressEvent, RunControl
from memoframe.processing.pipeline import (
    process_pending, update_bursts, update_duplicates, update_groups,
    update_places, update_search_index,
)
from memoframe.utils.logger import get_logger
from memoframe.utils.system_info import on_battery

log = get_logger("processing.watcher")

SMALL_BATCH = 20          # fewer ready files than this are processed in-process (no worker spawn)
_STEP = 0.5               # sleep granularity, so cancel is quick


class FolderWatcher:
    def __init__(
        self, settings: Settings, db: DatabaseManager, roots: Sequence[Path], control: RunControl,
        *, interval_s: float | None = None, settle_s: float | None = None,
        pause_on_battery: bool | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
        battery: Callable[[], bool | None] = on_battery,
    ) -> None:
        self.settings, self.db, self.control = settings, db, control
        self.roots = [Path(r) for r in roots]
        self.interval_s = settings.watch_interval_s if interval_s is None else interval_s
        self.settle_s = settings.watch_settle_s if settle_s is None else settle_s
        self.pause_on_battery = (settings.watch_pause_on_battery
                                 if pause_on_battery is None else pause_on_battery)
        self._sleep, self._now, self._battery = sleep, now, battery
        self._known = {r["path"]: (r["size"], r["mtime_ns"]) for r in db.list_fingerprints()}
        self._seen: dict[str, tuple[int, int]] = {}
        self._offline_reported: set[Path] = set()

    @staticmethod
    def _readable(path: Path) -> bool:
        try:
            with path.open("rb") as fh:
                fh.read(1)
            return True
        except OSError:
            return False

    def poll_once(self) -> list[tuple[Path, int, int]]:
        """Files that are new or changed AND stable. Updates the debounce state."""
        ready: list[tuple[Path, int, int]] = []
        current: set[str] = set()
        t = self._now()
        for root in self.roots:
            if not root.is_dir():
                if root not in self._offline_reported:
                    self._offline_reported.add(root)
                    self.control.emit(ProgressEvent("watch", message=f"folder offline: {root}"))
                continue
            self._offline_reported.discard(root)
            for path, size, mtime in iter_image_files(
                    root, self.settings.extensions, exclude=[self.settings.workspace]):
                key, fp = str(path), (size, mtime)
                if self._known.get(key) == fp:
                    continue
                current.add(key)
                if (self._seen.get(key) == fp and t - mtime / 1e9 >= self.settle_s
                        and self._readable(path)):
                    ready.append((path, size, mtime))
                else:
                    self._seen[key] = fp
        for key in list(self._seen):
            if key not in current:
                del self._seen[key]
        return ready

    def _wait(self, seconds: float) -> None:
        remaining = seconds
        while remaining > 0 and not self.control.cancelled:
            step = min(_STEP, remaining)
            self._sleep(step)
            remaining -= step

    def _refresh(self) -> None:
        s, db = self.settings, self.db
        update_duplicates(s, db)
        update_places(s, db)
        update_bursts(s, db)
        update_groups(s, db)
        update_search_index(s, db)

    def run(self, max_cycles: int | None = None) -> dict[str, int]:
        """Poll until cancelled (or ``max_cycles``). Returns ``cycles, processed, failed``."""
        for root in self.roots:
            if root.is_dir():
                self.db.add_source(str(root))
        cycles = processed = failed = 0
        self.control.emit(ProgressEvent("watch", message=f"watching {len(self.roots)} folder(s)"))
        while not self.control.cancelled and (max_cycles is None or cycles < max_cycles):
            if not self.control.checkpoint():
                break
            cycles += 1
            if self.pause_on_battery and self._battery() is True:
                self.control.emit(ProgressEvent("waiting", message="on battery"))
                self._wait(self.interval_s)
                continue
            ready = self.poll_once()
            if ready:
                self.db.register_files(ready)
                for path, size, mtime in ready:
                    self._known[str(path)] = (size, mtime)
                    self._seen.pop(str(path), None)
                run_settings = (self.settings if len(ready) >= SMALL_BATCH
                                else self.settings.with_overrides(workers=1))
                summary = process_pending(run_settings, self.db, show_progress=False,
                                          control=self.control)
                processed += summary.processed
                failed += summary.failed
                if summary.interrupted:
                    self.control.cancel()
                    break
                self._refresh()
                self.control.emit(ProgressEvent(
                    "watch", done=processed, failed=failed,
                    message=f"processed {summary.processed} new photo(s)"))
            self._wait(self.interval_s)
        self.control.emit(ProgressEvent("watch", done=processed, failed=failed, message="stopped"))
        return {"cycles": cycles, "processed": processed, "failed": failed}
