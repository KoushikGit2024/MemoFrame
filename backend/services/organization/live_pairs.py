"""Link Live Photo videos to their still (same folder, same name, short clip)."""
from __future__ import annotations

import os
from pathlib import Path

from database import DatabaseManager

_STILL_EXTS = frozenset({".heic", ".heif", ".jpg", ".jpeg"})
LIVE_MAX_SECONDS = 6.0


def link_live_pairs(db: DatabaseManager, max_seconds: float = LIVE_MAX_SECONDS) -> int:
    """Set ``pair_id`` on short videos that sit next to a same-named photo.

    Re-evaluated on every call, so a pair is dissolved if the photo disappears.
    Returns the number of rows changed. Database only.
    """
    rows = db.list_pair_candidates()
    stills: dict[tuple[str, str], int] = {}
    for r in rows:
        p = Path(r["path"])
        if r["kind"] == "photo" and p.suffix.lower() in _STILL_EXTS:
            stills.setdefault((os.path.normcase(str(p.parent)), p.stem.lower()), int(r["id"]))
    updates: list[tuple[int, int | None]] = []
    for r in rows:
        if r["kind"] != "video":
            continue
        want = None
        if r["duration_s"] is not None and r["duration_s"] <= max_seconds:
            p = Path(r["path"])
            want = stills.get((os.path.normcase(str(p.parent)), p.stem.lower()))
        if want != r["pair_id"]:
            updates.append((int(r["id"]), want))
    return db.set_pairs(updates)
