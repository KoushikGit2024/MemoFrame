"""Fill Phase D values for photos processed before Phase D (no face detection, read-only)."""
from __future__ import annotations

from pathlib import Path

from config import Settings
from services.intelligence.analysis import analyze_image
from services.vision.loader import ImageLoadError, load_image
from database import DatabaseManager
from services.pipeline.control import ProgressEvent, RunControl
from utils.logger import get_logger

log = get_logger("processing.enrich")


def enrich_existing(settings: Settings, db: DatabaseManager,
                    control: RunControl | None = None, batch: int = 200) -> int:
    """Compute quality, dHash, content type and date flag for done photos lacking them.

    Files that are missing or unreadable are skipped (left unanalysed) so a later
    run can try again. Returns the number analysed.
    """
    total = db.count_unanalyzed()
    done, last_id = 0, 0
    while True:
        rows = db.fetch_unanalyzed(last_id, batch)
        if not rows:
            break
        updates = []
        for r in rows:
            last_id = int(r["id"])
            if control is not None and not control.checkpoint():
                db.save_analysis(updates)
                return done + len(updates)
            path = Path(r["path"])
            try:
                loaded = load_image(path, settings.max_detect_side)
            except ImageLoadError as exc:
                log.warning("Skipped: %s", exc)
                continue
            updates.append((last_id, analyze_image(loaded, path.name, r["exif_ts"], r["ts_source"])))
            if control is not None:
                control.emit(ProgressEvent("analyze", done + len(updates), total, current=path.name))
        db.save_analysis(updates)
        done += len(updates)
    return done
