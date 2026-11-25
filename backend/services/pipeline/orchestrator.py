"""Orchestration: scan, process in batches (optionally in parallel), duplicates, groups.

The parent process is the only database writer. Workers return plain dicts.
Re-running continues where the last run stopped, because only ``pending``
images are fetched and each batch is committed atomically.
"""
from __future__ import annotations

import gc
import hashlib
import os
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np
from tqdm import tqdm

from config import SFACE_SHA256, SFACE_URL, VIDEO_EXTENSIONS, Settings
from services.intelligence.analysis import analyze_image
from services.organization.duplicates import find_duplicates
from services.face.clusterer import (
    DEFAULT_COSINE_DISTANCE_EPS,
    attach_faces,
    attach_to_anchors,
    cluster_face_embeddings,
)
from services.face.detector import FaceDetector, create_detector, merge_faces
from services.face.recognizer import FaceRecognizerSF
from services.intelligence.geo import load_place_index
from services.vision.loader import ImageLoadError, load_image_bytes
from services.organization.similarity import compute_features, compute_phash
from services.vision.metadata import extract_metadata
from models import TS_CONTAINER, TS_FILE_MTIME, ImageRecord
from services.pipeline.scanner import iter_image_files
from services.intelligence.tagger import SceneTagger, create_tagger
from services.vision.video import probe_video
from database import DatabaseManager, ScanStats
from services.organization.bursts import detect_bursts
from services.pipeline.control import ProgressEvent, RunControl
from services.face.processor import process_faces
from services.organization.grouper import group_images, name_groups, refine_events
from services.organization.live_pairs import link_live_pairs
from services.pipeline.maintenance import enforce_cache_cap, refresh_states
from services.pipeline.reporter import write_group_manifest
from services.vision.thumbnails import save_thumbnail, shard_dir
from utils.file_utils import lower_process_priority, sha256_file
from utils.logger import get_logger
from utils.model_downloader import ensure_model

log = get_logger("processing.pipeline")

_Task = tuple[int, str, int]                 # (image_id, path, mtime_ns)
_Outcome = tuple[bool, int, Any]             # (ok, image_id, result dict | error text)

# Per-process state, set by _init_worker.
_settings: Settings | None = None
_detector: FaceDetector | None = None
_recognizer: FaceRecognizerSF | None = None
_tagger: SceneTagger | None = None


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
    global _settings, _detector, _recognizer, _tagger
    if ignore_sigint:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    cv2.setNumThreads(settings.cv_threads)
    if settings.low_priority:
        lower_process_priority()
    _settings = settings
    _detector = create_detector(settings)
    _tagger = create_tagger(settings)
    if settings.sface_path.is_file():
        try:
            _recognizer = FaceRecognizerSF(settings.sface_path, use_gpu=settings.use_gpu)
        except Exception as exc:
            log.warning("Could not initialize SFace recognizer: %s", exc)
            _recognizer = None
    else:
        _recognizer = None


def _close_worker() -> None:
    global _settings, _detector, _recognizer, _tagger
    if _detector is not None:
        _detector.close()
    _settings = _detector = _recognizer = _tagger = None


def _process_video(image_id: int, path: Path, mtime_ns: int, settings: Settings) -> _Outcome:
    """Lightweight video indexing: header probe + poster frame, no face detection."""
    try:
        info = probe_video(path)
        exif_ts = info.created.strftime("%Y-%m-%dT%H:%M:%S") if info.created else None
        ts_source = TS_CONTAINER if info.created else TS_FILE_MTIME
        if exif_ts is None:
            exif_ts = datetime.fromtimestamp(mtime_ns / 1e9).strftime("%Y-%m-%dT%H:%M:%S")

        thumb_path = None
        if info.poster is not None:
            try:
                thumb_path = str(save_thumbnail(
                    info.poster, image_id, path, settings.thumbnails_dir,
                    settings.thumbnail_size, settings.jpeg_quality,
                ))
            except OSError as exc:
                log.warning("Poster thumbnail not written for %s: %s", path.name, exc)

        res = {
            "image_id": image_id,
            "kind": "video",
            "format": path.suffix.lower().lstrip("."),
            "duration_s": round(info.duration_s, 2) if info.duration_s is not None else None,
            "width": info.width,
            "height": info.height,
            "exif_ts": exif_ts,
            "ts_source": ts_source,
            "thumb_path": thumb_path,
            "faces": [],
        }
        return True, image_id, res
    except Exception as exc:
        return False, image_id, f"VIDEO_INDEX_FAILED: {exc}"


def _process_one_inner(task: _Task) -> _Outcome:
    """Process one image from a single read of the file. Never raises."""
    image_id, path_str, mtime_ns = task
    settings, detector = _settings, _detector
    if settings is None or detector is None:
        return False, image_id, "worker was not initialised"
    path = Path(path_str)
    try:
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            return _process_video(image_id, path, mtime_ns, settings)
        try:
            data = path.read_bytes()                 # the only disk read for this image
        except OSError as exc:
            return False, image_id, f"FILE_UNREADABLE: {path.name}: {exc}"
        sha256 = hashlib.sha256(data).hexdigest()
        loaded = load_image_bytes(data, path.name, settings.max_detect_side)
        meta = extract_metadata(loaded.exif, loaded.width, loaded.height, mtime_ns)
        record = ImageRecord(
            image_id=image_id, path=path, meta=meta, sha256=sha256,
            phash=compute_phash(loaded.pil), features=compute_features(loaded.pil),
            fmt=loaded.format or None,
        )
        faces = detector.detect(loaded)
        if settings.tiled_detection and max(loaded.width, loaded.height) > settings.max_detect_side * 1.5:
            big = load_image_bytes(data, path.name, settings.tile_source_side)
            faces = merge_faces(faces + detector.detect_tiled(big, settings.tile_size))
            del big
        del data
        record.faces = process_faces(image_id, path, faces, settings, recognizer=_recognizer)
        try:
            record.thumb_path = str(save_thumbnail(
                loaded.pil, image_id, path, settings.thumbnails_dir,
                settings.thumbnail_size, settings.jpeg_quality))
        except OSError as exc:
            log.warning("Thumbnail not written for %s: %s", path.name, exc)
        result = record.to_result()
        result.update(analyze_image(loaded, path.name, meta.exif_ts, meta.ts_source))
        if _tagger is not None:
            try:
                tags, vec = _tagger.tag(loaded.pil)
                result["tags"], result["tag_model"] = tags, _tagger.signature
                if settings.store_embeddings:
                    result["embedding"] = vec
            except Exception as exc:  # noqa: BLE001 - tagging must never fail a photo
                log.warning("Tagging skipped for %s: %s", path.name, exc)
        return True, image_id, result
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
def _watch(files: Iterator[tuple[Path, int, int]], control: RunControl) -> Iterator[tuple[Path, int, int]]:
    """Pass files through, emit scan progress, and stop early on cancel."""
    n = 0
    for item in files:
        if control.cancelled:
            return
        n += 1
        if n % 200 == 0:
            control.emit(ProgressEvent("scan", n, 0, current=item[0].name))
        yield item


def scan_directory(
    settings: Settings, db: DatabaseManager, root: Path, control: RunControl | None = None
) -> ScanStats:
    """Discover images under ``root`` and register them (new / changed / unchanged).

    The workspace is excluded. Progress is committed every 1000 files, so a
    cancelled scan keeps what it found.
    """
    log.info("Scanning %s", root)
    files = iter_image_files(root, settings.extensions, exclude=[settings.workspace])
    if control is not None:
        files = _watch(files, control)
    stats = db.register_files(files)
    db.add_source(str(root))
    if control is not None:
        control.emit(ProgressEvent("scan", stats.total, stats.total, message="scan complete"))
    return stats


def process_pending(
    settings: Settings,
    db: DatabaseManager,
    *,
    retry_failed: bool = False,
    show_progress: bool = True,
    control: RunControl | None = None,
) -> ProcessSummary:
    """Process every ``pending`` image in batches and store the results.

    ``control`` (optional) provides progress events, pause, cancel and the
    memory guard. Cancel keeps everything finished so far; re-run to continue.

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
    try:
        ensure_model(settings.sface_path, SFACE_URL, SFACE_SHA256)
    except Exception as exc:
        log.warning("Face recognition model unavailable, people grouping disabled: %s", exc)
    create_tagger(settings)                 # fail fast if tagging is on but its files are missing
    if settings.low_priority:
        lower_process_priority()

    workers = settings.workers
    if settings.storage_type == "hdd" and workers > 2:
        log.info("HDD mode: using 2 workers instead of %d (parallel reads slow a hard drive)", workers)
        workers = 2

    executor: ProcessPoolExecutor | None = None
    if workers > 1:
        create_detector(settings).close()        # fail fast, before spawning workers
        # On Windows, OpenCV C++ threads/ONNX runtime handles deadlock if max_tasks_per_child recycles workers
        recycle = None if sys.platform == "win32" else (settings.worker_recycle_tasks or None)
        executor = ProcessPoolExecutor(
            max_workers=workers,
            max_tasks_per_child=recycle,
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
            if control is not None and not control.checkpoint():
                interrupted = True
                break
            rows = db.fetch_pending(settings.batch_size)
            if not rows:
                break
            tasks: list[_Task] = [(r["id"], r["path"], r["mtime_ns"]) for r in rows]
            names = {t[0]: t[1] for t in tasks}
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
                    if control is not None:
                        control.emit(ProgressEvent(
                            "process", done + failed + len(ok) + len(bad), total,
                            failed + len(bad), Path(names[image_id]).name))
                        if not control.checkpoint():
                            interrupted = True
                            break
            except KeyboardInterrupt:
                interrupted = True
            except BrokenProcessPool as exc:
                crash = exc
            db.save_results(ok)              # partial batches are kept on cancel/interrupt/crash
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

    if done:
        db.restore_marks()          # marks follow photos that moved, or came back after a reset

    if control is not None:
        control.emit(ProgressEvent("process", done + failed, total, failed,
                                   message="interrupted" if interrupted else "complete"))
    if crash is not None:
        raise PipelineError(
            "A worker process crashed (possibly out of memory). Progress so far is saved; "
            "re-run to continue, or try a smaller --workers value."
        ) from crash
    if interrupted:
        log.warning("Interrupted. Progress is saved; re-run to continue.")
    return ProcessSummary(done, failed, db.count_pending(), interrupted)


def update_duplicates(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Recompute duplicate clusters (pHash candidates confirmed by dHash)."""
    sig = f"{db.revision()}|{settings.phash_near_threshold}|{settings.dhash_confirm_threshold}"
    cached = db.get_meta("dup_state")
    if cached and not force and cached.split("#")[0] == sig:
        return int(cached.split("#")[1])
    records = [(r["id"], r["sha256"], r["phash"], r["dhash"]) for r in db.fetch_hash_records()]
    rows = find_duplicates(records, settings.phash_near_threshold, settings.dhash_confirm_threshold)
    db.replace_duplicates(rows)
    count = len({cluster_id for _, cluster_id, _ in rows})
    db.set_meta("dup_state", f"{sig}#{count}")
    return count


def update_places(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Resolve place names for GPS-tagged photos (offline). Returns how many got a name.

    Photos with no city within ``place_max_km`` get an empty place and are not retried
    unless ``force`` (use after adding a bigger cities file).
    """
    if force:
        db.clear_places()
    index = None
    named = 0
    while True:
        rows = db.fetch_gps_without_place(2000)
        if not rows:
            return named
        if index is None:
            index = load_place_index(settings.workspace / "data")
        points = np.array([[r["gps_lat"], r["gps_lon"]] for r in rows], dtype=np.float64)
        labels = index.lookup_many(points, settings.place_max_km)
        db.set_places([(int(r["id"]), label or "") for r, label in zip(rows, labels)])
        named += sum(1 for label in labels if label)


def update_bursts(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Detect bursts and suggest the best frame. Skipped if nothing changed."""
    sig = (f"{db.revision()}|{settings.burst_gap_seconds}|{settings.burst_hash_threshold}|"
           f"{settings.min_burst_size}")
    cached = db.get_meta("burst_state")
    if cached and not force and cached.split("#")[0] == sig:
        return int(cached.split("#")[1])
    bursts = detect_bursts(db.fetch_burst_rows(), gap_seconds=settings.burst_gap_seconds,
                           hash_threshold=settings.burst_hash_threshold,
                           min_size=settings.min_burst_size)
    count = db.replace_bursts(bursts)
    db.set_meta("burst_state", f"{sig}#{count}")
    return count


def update_groups(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Recompute groups: events (refined, place-named) and visual clusters."""
    link_live_pairs(db)
    sig = (f"{db.revision()}|{settings.event_gap_hours}|{settings.gps_split_km}|"
           f"{settings.visual_cluster_distance}|{settings.min_group_size}|"
           f"{settings.refine_min_event_size}|{settings.refine_merge_gap_hours}|"
           f"{settings.refine_max_event_hours}|{settings.group_screenshots}")
    cached = db.get_meta("group_state")
    if cached and not force and cached.split("#")[0] == sig:
        return int(cached.split("#")[1])
    rows = db.fetch_grouping_rows(include_junk=settings.group_screenshots)
    groups = group_images(
        rows, event_gap_hours=settings.event_gap_hours, gps_split_km=settings.gps_split_km,
        visual_distance=settings.visual_cluster_distance, min_group_size=1)
    times = {int(r["id"]): datetime.strptime(r["exif_ts"], "%Y-%m-%dT%H:%M:%S")
             for r in rows if r["exif_ts"]}
    groups = refine_events(groups, times, min_size=settings.refine_min_event_size,
                           merge_gap_hours=settings.refine_merge_gap_hours,
                           max_hours=settings.refine_max_event_hours)
    name_groups(groups, {int(r["id"]): r["place"] for r in rows})
    groups = [g for g in groups if len(g["image_ids"]) >= settings.min_group_size]
    count = db.replace_groups(groups)
    try:
        write_group_manifest(settings, db)
    except OSError as exc:
        log.warning("Could not write group manifest: %s", exc)
    db.set_meta("group_state", f"{sig}#{count}")
    return count


PERSON_MIN_FACE_PX = 40
PERSON_MIN_CONF = 0.8
MIN_PERSON_FACES = 2


def update_persons(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Rebuild people. Confirmed (locked) faces are fixed points; everything else is re-derived."""
    rows = db.fetch_faces_with_embeddings()
    locked = [r for r in rows if r["locked"]]
    sig = (f"{len(rows)}|{sum(int(r['id']) for r in rows)}|{len(locked)}|"
           f"{sum(int(r['id']) for r in locked)}|{DEFAULT_COSINE_DISTANCE_EPS}")
    if not force and db.get_meta("person_state") == sig:
        return len(db.list_persons())

    anchors: dict[int, list[bytes]] = {}
    for r in locked:
        if r["person_id"] is not None:
            anchors.setdefault(int(r["person_id"]), []).append(r["embedding"])
    good, weak = [], []
    for r in rows:
        if r["locked"]:
            continue
        strong = min(r["w"], r["h"]) >= PERSON_MIN_FACE_PX and r["confidence"] >= PERSON_MIN_CONF
        (good if strong else weak).append((int(r["id"]), r["embedding"]))

    # 1. confirmed people claim the free faces that clearly look like them (weak faces: stricter)
    fixed = attach_to_anchors(anchors, good, DEFAULT_COSINE_DISTANCE_EPS)
    for pid, fids in attach_to_anchors(anchors, weak, DEFAULT_COSINE_DISTANCE_EPS * 0.85).items():
        fixed.setdefault(pid, []).extend(fids)
    claimed = {f for fids in fixed.values() for f in fids}
    good = [g for g in good if g[0] not in claimed]
    weak = [w for w in weak if w[0] not in claimed]

    # 2. cluster the rest
    if not good:
        good, weak = weak, []
    clusters = cluster_face_embeddings(good)
    clusters = attach_faces(clusters, good, weak, DEFAULT_COSINE_DISTANCE_EPS * 1.15)
    clusters = {k: v for k, v in clusters.items() if len(v) >= MIN_PERSON_FACES}
    count = db.replace_person_clusters(clusters, fixed=fixed)
    db.set_meta("person_state", sig)
    return count


def update_search_index(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Rebuild the text index when results, groups or places changed. Returns rows indexed."""
    sig = f"{db.revision()}|{(db.get_meta('group_state') or '').replace('#', ':')}|{db.get_meta('persons_rev') or ''}"
    cached = db.get_meta("fts_state")
    if cached and not force and cached.split("#")[0] == sig:
        return int(cached.split("#")[1])
    count = db.rebuild_fts()
    db.set_meta("fts_state", f"{sig}#{count}")
    return count


def run_pipeline(
    settings: Settings,
    db: DatabaseManager,
    root: Path,
    *,
    retry_failed: bool = False,
    show_progress: bool = True,
    control: RunControl | None = None,
) -> ProcessSummary:
    """Scan, process, then rebuild duplicates and groups (skipped if interrupted)."""
    scan_directory(settings, db, root, control)
    refresh_states(db)                      # lets moved files be recognised
    summary = process_pending(
        settings, db, retry_failed=retry_failed, show_progress=show_progress, control=control)
    if not summary.interrupted and not (control and control.cancelled):
        for stage_name, update_fn in (
            ("duplicates", lambda: update_duplicates(settings, db)),
            ("places", lambda: update_places(settings, db)),
            ("bursts", lambda: update_bursts(settings, db)),
            ("groups", lambda: update_groups(settings, db)),
            ("persons", lambda: update_persons(settings, db)),
            ("index", lambda: update_search_index(settings, db)),
        ):
            if control and control.cancelled:
                break
            if control:
                control.emit(ProgressEvent(stage_name, message=f"building {stage_name}"))
            try:
                update_fn()
            except Exception as exc:
                log.warning("Stage %s failed: %s", stage_name, exc)
                if control:
                    control.emit(ProgressEvent(stage_name, message=f"{stage_name} warning: {exc}"))

        if settings.thumb_cache_max_mb:
            try:
                enforce_cache_cap(settings, db, settings.thumb_cache_max_mb)
            except Exception as exc:
                log.warning("Cache cap enforcement failed: %s", exc)

        if control:
            control.emit(ProgressEvent("done", message="finished"))
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
        update_persons(settings, db)
    return removed