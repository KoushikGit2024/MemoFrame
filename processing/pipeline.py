"""Orchestration: scan, process in batches (optionally in parallel), duplicates, groups.

The parent process is the only database writer. Workers return plain dicts.
Re-running continues where the last run stopped, because only ``pending``
images are fetched and each batch is committed atomically.
"""
from __future__ import annotations

import gc
import os
import signal
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
from tqdm import tqdm

from config import Settings
from core.duplicate_detector import find_duplicates
from core.face_detector import FaceDetector, create_detector
from core.image_loader import ImageLoadError, load_image
from core.image_similarity import compute_features, compute_phash
from core.metadata_extractor import extract_metadata
from core.models import ImageRecord
from core.scanner import iter_image_files
from database import DatabaseManager, ScanStats
from processing.face_processor import process_faces
from processing.image_grouper import group_images
from processing.reporter import write_group_manifest
from processing.thumbnail_generator import save_thumbnail, shard_dir
from utils.file_utils import lower_process_priority, sha256_file
from utils.logger import get_logger
from utils.model_downloader import ensure_model

log = get_logger("processing.pipeline")

_Task = tuple[int, str, int]                 # (image_id, path, mtime_ns)
_Outcome = tuple[bool, int, Any]             # (ok, image_id, result dict | error text)

# Per-process state, set by _init_worker.
_settings: Settings | None = None
_detector: FaceDetector | None = None


class PipelineError(RuntimeError):
    """A run-level failure (not a per-image failure)."""


@dataclass(frozen=True)
class ProcessSummary:
    """Outcome of :func:`process_pending`."""

    processed: int
    failed: int
    remaining: int
    interrupted: bool


# ----------------------------------------------------------------------
# Worker side
# ----------------------------------------------------------------------
def _init_worker(settings: Settings, ignore_sigint: bool) -> None:
    """Create this process's detector. Workers ignore Ctrl+C; the parent handles it."""
    global _settings, _detector
    if ignore_sigint:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    cv2.setNumThreads(settings.cv_threads)
    if settings.low_priority:
        lower_process_priority()
    _settings = settings
    _detector = create_detector(settings)


def _close_worker() -> None:
    global _settings, _detector
    if _detector is not None:
        _detector.close()
    _settings = _detector = None


def _process_one_inner(task: _Task) -> _Outcome:
    """Process one image. Never raises: failures are returned as ``(False, id, message)``."""
    image_id, path_str, mtime_ns = task
    settings, detector = _settings, _detector
    if settings is None or detector is None:
        return False, image_id, "worker was not initialised"
    path = Path(path_str)
    try:
        loaded = load_image(path, settings.max_detect_side)
        meta = extract_metadata(loaded.exif, loaded.width, loaded.height, mtime_ns)
        record = ImageRecord(
            image_id=image_id,
            path=path,
            meta=meta,
            sha256=sha256_file(path, settings.hash_chunk_bytes),
            phash=compute_phash(loaded.pil),
            features=compute_features(loaded.pil),
        )
        faces = detector.detect(loaded)
        record.faces = process_faces(image_id, path, faces, settings)
        try:
            record.thumb_path = str(save_thumbnail(
                loaded.pil, image_id, path, settings.thumbnails_dir,
                settings.thumbnail_size, settings.jpeg_quality))
        except OSError as exc:
            log.warning("Thumbnail not written for %s: %s", path.name, exc)
        return True, image_id, record.to_result()
    except ImageLoadError as exc:
        return False, image_id, str(exc)
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
        return False, image_id, f"{type(exc).__name__}: {exc}"


def _process_one(task: _Task) -> _Outcome:
    """Process one image, then optionally sleep to honour ``cpu_limit``."""
    start = time.perf_counter()
    outcome = _process_one_inner(task)
    gc.collect()
    limit = _settings.cpu_limit if _settings else 1.0
    if 0 < limit < 1.0:
        time.sleep((time.perf_counter() - start) * (1.0 / limit - 1.0))
    return outcome


# ----------------------------------------------------------------------
# Stages
# ----------------------------------------------------------------------
def scan_directory(settings: Settings, db: DatabaseManager, root: Path) -> ScanStats:
    """Discover images under ``root`` and register them (new / changed / unchanged).

    The workspace is excluded, so generated files are never scanned as photos.
    """
    log.info("Scanning %s", root)
    files = iter_image_files(root, settings.extensions, exclude=[settings.workspace])
    return db.register_files(files)


def process_pending(
    settings: Settings,
    db: DatabaseManager,
    *,
    retry_failed: bool = False,
    show_progress: bool = True,
) -> ProcessSummary:
    """Process every ``pending`` image in batches and store the results.

    Raises:
        ModelDownloadError, DetectorUnavailableError: if the detector cannot start.
        PipelineError: if a worker process crashes.
    """
    if retry_failed:
        log.info("Re-queued %d failed image(s)", db.retry_failed())
    total = db.count_pending()
    if total == 0:
        return ProcessSummary(0, 0, 0, False)

    settings.ensure_dirs()
    if settings.detector_backend.lower() == "yunet":
        ensure_model(settings.yunet_path)

    if settings.low_priority:
        lower_process_priority()

    executor: ProcessPoolExecutor | None = None
    if settings.workers > 1:
        create_detector(settings).close()        # fail fast, before spawning workers
        executor = ProcessPoolExecutor(
            max_workers=settings.workers,
            max_tasks_per_child=settings.worker_recycle_tasks,
            initializer=_init_worker,
            initargs=(settings, True),
        )
    else:
        _init_worker(settings, False)

    done = failed = 0
    interrupted = False
    crash: BrokenProcessPool | None = None
    bar = tqdm(total=total, unit="img", disable=not show_progress)
    try:
        while True:
            rows = db.fetch_pending(settings.batch_size)
            if not rows:
                break
            tasks: list[_Task] = [(r["id"], r["path"], r["mtime_ns"]) for r in rows]
            ok: list[dict[str, Any]] = []
            bad: list[tuple[int, str]] = []
            try:
                outcomes = executor.map(_process_one, tasks) if executor else map(_process_one, tasks)
                for success, image_id, payload in outcomes:
                    if success:
                        ok.append(payload)
                    else:
                        bad.append((image_id, payload))
                        log.warning("Failed: %s", payload)
                    bar.update(1)
            except KeyboardInterrupt:
                interrupted = True
            except BrokenProcessPool as exc:
                crash = exc
            db.save_results(ok)              # partial batches are kept on interrupt/crash
            db.save_failures(bad)
            done += len(ok)
            failed += len(bad)
            if interrupted or crash:
                break
    finally:
        bar.close()
        if executor is not None:
            executor.shutdown(wait=not (interrupted or crash), cancel_futures=True)
        else:
            _close_worker()

    if crash is not None:
        raise PipelineError(
            "A worker process crashed (possibly out of memory). Progress so far is saved; "
            "re-run to continue, or try a smaller --workers value."
        ) from crash
    if interrupted:
        log.warning("Interrupted. Progress is saved; re-run the same command to continue.")
    return ProcessSummary(done, failed, db.count_pending(), interrupted)


def update_duplicates(settings: Settings, db: DatabaseManager) -> int:
    """Recompute duplicate clusters from stored hashes. Returns the cluster count."""
    records = [(r["id"], r["sha256"], r["phash"]) for r in db.fetch_hash_records()]
    rows = find_duplicates(records, settings.phash_near_threshold)
    db.replace_duplicates(rows)
    return len({cluster_id for _, cluster_id, _ in rows})


def update_groups(settings: Settings, db: DatabaseManager) -> int:
    """Recompute event/visual groups and refresh the manifest. Returns the group count."""
    groups = group_images(
        db.fetch_grouping_rows(),
        event_gap_hours=settings.event_gap_hours,
        gps_split_km=settings.gps_split_km,
        visual_distance=settings.visual_cluster_distance,
        min_group_size=settings.min_group_size,
    )
    count = db.replace_groups(groups)
    try:
        write_group_manifest(settings, db)
    except OSError as exc:
        log.warning("Could not write group manifest: %s", exc)
    return count


def run_pipeline(
    settings: Settings,
    db: DatabaseManager,
    root: Path,
    *,
    retry_failed: bool = False,
    show_progress: bool = True,
) -> ProcessSummary:
    """Scan, process, then rebuild duplicates and groups (skipped if interrupted)."""
    scan_directory(settings, db, root)
    summary = process_pending(
        settings, db, retry_failed=retry_failed, show_progress=show_progress)
    if not summary.interrupted:
        update_duplicates(settings, db)
        update_groups(settings, db)
    return summary

# ----------------------------------------------------------------------
# Pruning (records of photos that no longer exist on disk)
# ----------------------------------------------------------------------
def find_missing_images(
    db: DatabaseManager, root: Path | None = None
) -> tuple[int, list[tuple[int, str]]]:
    """Return ``(checked, missing)`` where ``missing`` is ``[(image_id, path), ...]``.

    With ``root``, only records under that folder are checked. The folder must
    exist, which protects against an unmounted or disconnected drive.

    Raises:
        PipelineError: if ``root`` is not an existing directory.
    """
    prefix: str | None = None
    if root is not None:
        if not root.is_dir():
            raise PipelineError(f"Folder not found (is the drive connected?): {root}")
        prefix = os.path.normcase(str(root.resolve())).rstrip("\\/") + os.sep
    checked = 0
    missing: list[tuple[int, str]] = []
    for row in db.list_image_paths():
        path = row["path"]
        if prefix is not None and not os.path.normcase(os.path.abspath(path)).startswith(prefix):
            continue
        checked += 1
        if not Path(path).is_file():
            missing.append((int(row["id"]), path))
    return checked, missing


def _remove_generated_files(settings: Settings, image_id: int) -> None:
    """Delete thumbnail, face crops and annotated copy for one image id (workspace only)."""
    for base in (settings.thumbnails_dir, settings.face_crops_dir, settings.annotated_dir):
        folder = shard_dir(base, image_id)
        if not folder.is_dir():
            continue
        for stale in folder.glob(f"{image_id:08d}_*"):
            try:
                stale.unlink()
            except OSError as exc:
                log.warning("Could not remove %s: %s", stale, exc)


def remove_images(settings: Settings, db: DatabaseManager, image_ids: list[int]) -> int:
    """Remove records and generated files for ``image_ids``, then rebuild duplicates/groups.

    Original photographs are never touched. Returns the number of records removed.
    """
    for image_id in image_ids:
        _remove_generated_files(settings, image_id)
    removed = db.delete_images(image_ids)
    if removed:
        update_duplicates(settings, db)
        update_groups(settings, db)
    return removed