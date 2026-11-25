"""Backfill tags for photos processed before tagging was enabled (read-only, no face detection)."""

from __future__ import annotations

from pathlib import Path

from config import Settings
from services.vision.loader import ImageLoadError, load_image
from services.intelligence.tagger import TaggerUnavailableError, create_tagger
from database import DatabaseManager
from services.pipeline.control import ProgressEvent, RunControl
from utils.logger import get_logger

log = get_logger("processing.tagging")


def tag_existing(
    settings: Settings, db: DatabaseManager, control: RunControl | None = None, batch: int = 100
) -> int:
    """Tag every processed photo not yet tagged with the current model. Returns the count.

    Unreadable or missing files are skipped (left untagged) so a later run can retry.
    """
    tagger = create_tagger(settings)
    if tagger is None:
        raise TaggerUnavailableError("Tagging is switched off (tagging_enabled = false).")
    sig = tagger.signature
    total = db.count_untagged(sig)
    done = last_id = 0
    while True:
        rows = db.fetch_untagged(sig, last_id, batch)
        if not rows:
            return done
        updates = []
        for r in rows:
            last_id = int(r["id"])
            if control is not None and not control.checkpoint():
                db.save_tags(updates)
                return done + len(updates)
            path = Path(r["path"])
            try:
                loaded = load_image(path, 640)
                tags, vec = tagger.tag(loaded.pil)
            except (ImageLoadError, ValueError) as exc:
                log.warning("Not tagged: %s", exc)
                continue
            item = {"tags": tags, "tag_model": sig}
            if settings.store_embeddings:
                item["embedding"] = vec
            updates.append((last_id, item))
            if control is not None:
                control.emit(ProgressEvent("tag", done + len(updates), total, current=path.name))
        db.save_tags(updates)
        done += len(updates)
