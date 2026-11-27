"""Workspace maintenance: file states, thumbnail cache, database health.

Photos are only ever READ. Everything deleted here lives in the workspace.
Errors are plain Python exceptions (the Engine translates them).
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from memoframe_engine.core.config import VIDEO_EXTENSIONS, Settings
from memoframe_engine.domains.media.loader import ImageLoadError, load_image
from memoframe_engine.domains.media.video import probe_video
from memoframe_engine.db import DatabaseManager
from memoframe_engine.domains.media.thumbnails import save_thumbnail, shard_dir
from memoframe_engine.utils.file_utils import is_within
from memoframe_engine.utils.logger import get_logger

log = get_logger("processing.maintenance")

MB = 1024 * 1024
BACKUPS_TO_KEEP = 3
_SUSPICIOUS_MIN = 10  # a source whose files are ALL missing is treated as offline
CACHE_KINDS = ("thumbnails", "face_crops", "annotated")


# ----------------------------------------------------------------------
# File states: ok / offline / missing
# ----------------------------------------------------------------------
def _root_of(path: Path, sources: list[Path]) -> Path | None:
    norm = os.path.normcase(str(path))
    for root in sources:
        prefix = os.path.normcase(str(root)).rstrip("\\/") + os.sep
        if norm.startswith(prefix):
            return root
    return None


def refresh_states(db: DatabaseManager) -> dict[str, int]:
    """Check every registered photo and update its state.

    ``ok``: file exists. ``missing``: its source folder is reachable but the file
    is gone. ``offline``: the source folder/drive is not reachable (nothing is
    treated as deleted). A reachable source in which EVERY file looks missing
    (10+ files) is also treated as offline, which catches an empty mount point.
    Returns the counts per state.
    """
    sources = [Path(s) for s in db.list_sources()]
    source_up = {s: s.is_dir() for s in sources}
    totals: dict[Path | None, int] = {}
    gone: dict[Path | None, list[tuple[int, str, Path]]] = {}
    updates: list[tuple[int, str]] = []

    for row in db.list_image_states():
        path = Path(row["path"])
        root = _root_of(path, sources)
        totals[root] = totals.get(root, 0) + 1
        if path.is_file():
            if row["state"] != "ok":
                updates.append((row["id"], "ok"))
        else:
            gone.setdefault(root, []).append((row["id"], row["state"], path))

    for root, items in gone.items():
        for image_id, old_state, path in items:
            if root is not None:
                up = source_up[root] and not (
                    len(items) == totals[root] and totals[root] >= _SUSPICIOUS_MIN
                )
            else:  # scanned before sources were recorded
                up = bool(path.anchor) and Path(path.anchor).is_dir()
            new_state = "missing" if up else "offline"
            if new_state != old_state:
                updates.append((image_id, new_state))

    db.set_states(updates)
    return db.state_counts()


def _remove_generated(settings: Settings, image_id: int) -> None:
    for base in (settings.thumbnails_dir, settings.face_crops_dir, settings.annotated_dir):
        folder = shard_dir(base, image_id)
        if folder.is_dir() and is_within(folder, settings.workspace):
            for stale in folder.glob(f"{image_id:08d}_*"):
                try:
                    stale.unlink()
                except OSError as exc:
                    log.warning("Could not remove %s: %s", stale, exc)


def forget_missing(settings: Settings, db: DatabaseManager) -> int:
    """Remove records (and workspace thumbnails/crops) of photos confirmed ``missing``.

    Run :func:`refresh_states` first. Offline photos are never forgotten.
    Duplicates and groups are rebuilt on the next process/rebuild.
    """
    ids = db.image_ids_in_state("missing")
    for image_id in ids:
        _remove_generated(settings, image_id)
    return db.delete_images(ids)


# ----------------------------------------------------------------------
# Thumbnail / crop cache
# ----------------------------------------------------------------------
def _dir_stats(folder: Path) -> dict[str, int]:
    files = size = 0
    if folder.is_dir():
        for p in folder.rglob("*"):
            if p.is_file():
                files += 1
                size += p.stat().st_size
    return {"files": files, "bytes": size}


def cache_info(settings: Settings) -> dict[str, dict[str, int]]:
    """File count and bytes of each generated-file folder."""
    return {
        "thumbnails": _dir_stats(settings.thumbnails_dir),
        "face_crops": _dir_stats(settings.face_crops_dir),
        "annotated": _dir_stats(settings.annotated_dir),
    }


def clear_cache(
    settings: Settings, db: DatabaseManager, kinds: Iterable[str] = ("thumbnails",)
) -> dict[str, int]:
    """Delete generated files of the given kinds (workspace only). Returns freed MB per kind.

    Thumbnails can be recreated on demand with :func:`get_thumbnail`.
    """
    freed: dict[str, int] = {}
    dirs = {
        "thumbnails": settings.thumbnails_dir,
        "face_crops": settings.face_crops_dir,
        "annotated": settings.annotated_dir,
    }
    for kind in kinds:
        if kind not in dirs:
            raise ValueError(f"Unknown cache kind {kind!r}. Use: {', '.join(CACHE_KINDS)}.")
        folder = dirs[kind]
        freed[kind] = _dir_stats(folder)["bytes"] // MB
        if folder.is_dir() and is_within(folder, settings.workspace):
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True, exist_ok=True)
        if kind == "thumbnails":
            db.clear_thumb_paths()
        elif kind == "face_crops":
            db.clear_crop_paths()
    return freed


def enforce_cache_cap(settings: Settings, db: DatabaseManager, max_mb: int) -> int:
    """Delete the oldest thumbnails until the folder is under ``max_mb``. Returns files removed."""
    if max_mb <= 0 or not settings.thumbnails_dir.is_dir():
        return 0
    files = [
        (p.stat().st_mtime, p.stat().st_size, p) for p in settings.thumbnails_dir.rglob("*.jpg")
    ]
    total = sum(size for _, size, _ in files)
    limit = max_mb * MB
    if total <= limit:
        return 0
    removed_ids: list[int] = []
    for _, size, path in sorted(files, key=lambda f: f[0]):
        if total <= limit:
            break
        try:
            path.unlink()
        except OSError:
            continue
        total -= size
        try:
            removed_ids.append(int(path.name[:8]))
        except ValueError:
            pass
    db.unset_thumbs(removed_ids)
    log.info("Thumbnail cache trimmed: %d file(s) removed", len(removed_ids))
    return len(removed_ids)


def get_thumbnail(settings: Settings, db: DatabaseManager, image_id: int) -> Path:
    """Return the thumbnail path, recreating it from the original (read-only) if needed.

    Raises:
        ValueError: unknown image id.
        FileNotFoundError: the original is not available (offline or missing).
    """
    row = db.get_image(image_id)
    if row is None:
        raise ValueError(f"No image with id {image_id}.")
    if row["thumb_path"] and Path(row["thumb_path"]).is_file():
        return Path(row["thumb_path"])
    source = Path(row["path"])
    if not source.is_file():
        raise FileNotFoundError(f"Original not available (drive offline or file moved): {source}")

    if source.suffix.lower() in VIDEO_EXTENSIONS:
        try:
            info = probe_video(source)
            if info.poster is not None:
                dest = save_thumbnail(
                    info.poster,
                    image_id,
                    source,
                    settings.thumbnails_dir,
                    settings.thumbnail_size,
                    settings.jpeg_quality,
                )
                db.set_thumb_path(image_id, str(dest))
                return dest
        except Exception as exc:
            raise ValueError(f"VIDEO_THUMBNAIL_FAILED: {source.name}: {exc}") from exc
        raise ValueError(f"No poster frame extractable for video: {source.name}")

    try:
        loaded = load_image(source, settings.thumbnail_size * 2)
    except ImageLoadError as exc:
        raise ValueError(str(exc)) from exc
    dest = save_thumbnail(
        loaded.pil,
        image_id,
        source,
        settings.thumbnails_dir,
        settings.thumbnail_size,
        settings.jpeg_quality,
    )
    db.set_thumb_path(image_id, str(dest))
    return dest


# ----------------------------------------------------------------------
# Database health
# ----------------------------------------------------------------------
def run_maintenance(
    settings: Settings, db: DatabaseManager, vacuum: bool = False
) -> dict[str, Any]:
    """Back up the database, check integrity, refresh statistics, trim the WAL.

    Keeps the newest ``BACKUPS_TO_KEEP`` backups in ``<workspace>/backups``.
    ``vacuum=True`` also compacts the file (slow on a large database).
    """
    folder = settings.workspace / "backups"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db.backup(folder / f"photos-{stamp}.db")
    for old in sorted(folder.glob("photos-*.db"))[:-BACKUPS_TO_KEEP]:
        try:
            old.unlink()
        except OSError:
            pass
    problems = db.integrity_check()
    db.analyze()
    if vacuum:
        db.vacuum()
    db.checkpoint()
    return {"backup": str(backup), "integrity_problems": problems, "vacuumed": vacuum}
