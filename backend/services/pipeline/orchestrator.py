"""Orchestration: scan, process in batches (optionally in parallel), duplicates, groups.

The parent process is the only database writer. Workers return plain dicts.
Re-running continues where the last run stopped, because only ``pending``
images are fetched and each batch is committed atomically.

Parallel modes
--------------
* ``process`` - ProcessPoolExecutor (non-Windows). Each worker process owns one
  set of models.
* ``thread``  - ThreadPoolExecutor (Windows). Each *thread* owns its own set of
  models through ``threading.local()``, so no detector/tagger is ever shared
  between threads. OpenCV and ONNX Runtime release the GIL during inference.
* ``inline``  - single worker in the calling thread.
"""

from __future__ import annotations

from services.organization.duplicates import find_duplicates  # noqa: F401 (re-exported for pipeline_steps)

import gc
import hashlib
import os
import signal
import sys
import threading
import time
from concurrent.futures import (
    BrokenExecutor,
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import cv2
from tqdm import tqdm

from config import SFACE_SHA256, SFACE_URL, VIDEO_EXTENSIONS, Settings
from services.intelligence.analysis import analyze_image
from services.face.detector import FaceDetector, create_detector, merge_faces
from services.face.recognizer import FaceRecognizerSF
from services.vision.loader import ImageLoadError, load_image_bytes
from services.organization.similarity import compute_features, compute_phash
from services.vision.metadata import extract_metadata
from models import TS_CONTAINER, TS_FILE_MTIME, ImageRecord
from services.pipeline.scanner import iter_image_files
from services.intelligence.tagger import SceneTagger, create_tagger
from services.vision.video import probe_video
from database import DatabaseManager, ScanStats
from services.pipeline.control import ProgressEvent, RunControl
from services.face.processor import process_faces
from services.pipeline.maintenance import enforce_cache_cap, refresh_states
from services.vision.thumbnails import save_thumbnail, shard_dir
from utils.file_utils import lower_process_priority
from utils.logger import get_logger
from utils.model_downloader import ensure_model

log = get_logger("processing.pipeline")

_Task = tuple[int, str, int]  # (image_id, path, mtime_ns)
_Outcome = tuple[bool, int, Any]  # (ok, image_id, result dict | error text)

# Maximum threads used on Windows (each thread loads its own model copies).
_MAX_THREADS = 4

# Per-thread model state. In a worker process the task thread is the process's
# main thread, so the same mechanism serves both process and thread pools.
_tls = threading.local()

# Every detector created in this process, so they can all be closed at the end.
_registry: list[FaceDetector] = []
_registry_lock = threading.Lock()


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
def _setup_models(settings: Settings) -> None:
    """Create this thread's detector, tagger and recognizer."""
    _tls.settings = settings
    _tls.detector = create_detector(settings)
    with _registry_lock:
        _registry.append(_tls.detector)
    _tls.tagger = create_tagger(settings)
    _tls.recognizer = None
    if settings.face_recognition and settings.sface_path.is_file():
        try:
            _tls.recognizer = FaceRecognizerSF(settings.sface_path, use_gpu=settings.use_gpu)
        except Exception as exc:
            log.warning("Could not initialize SFace recognizer: %s", exc)
            _tls.recognizer = None


def _init_worker(settings: Settings, ignore_sigint: bool) -> None:
    """Process initializer. Workers ignore Ctrl+C; the parent handles it."""
    if ignore_sigint:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        from utils.logger import setup_worker_logging

        setup_worker_logging(settings.workspace)
    cv2.setNumThreads(settings.cv_threads)
    if settings.low_priority and ignore_sigint:
        lower_process_priority()
    _setup_models(settings)


def _init_thread(settings: Settings) -> None:
    """Thread initializer: runs once per pool thread, giving it private models."""
    _setup_models(settings)


def _close_all() -> None:
    """Close every detector created in this process and clear this thread's state."""
    with _registry_lock:
        detectors = list(_registry)
        _registry.clear()
    for det in detectors:
        try:
            det.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("Detector close failed: %s", exc)
    for name in ("settings", "detector", "recognizer", "tagger"):
        if hasattr(_tls, name):
            setattr(_tls, name, None)


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
                thumb_path = str(
                    save_thumbnail(
                        info.poster,
                        image_id,
                        path,
                        settings.thumbnails_dir,
                        settings.thumbnail_size,
                        settings.jpeg_quality,
                    )
                )
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
        log.exception("Video indexing failed for %s", path)
        return False, image_id, f"VIDEO_INDEX_FAILED: {exc}"


def _process_one_inner(task: _Task) -> _Outcome:
    """Process one image from a single read of the file. Never raises."""
    image_id, path_str, mtime_ns = task
    settings = getattr(_tls, "settings", None)
    detector: FaceDetector | None = getattr(_tls, "detector", None)
    recognizer: FaceRecognizerSF | None = getattr(_tls, "recognizer", None)
    tagger: SceneTagger | None = getattr(_tls, "tagger", None)
    if settings is None or detector is None:
        return False, image_id, "worker was not initialised"
    path = Path(path_str)
    try:
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            return _process_video(image_id, path, mtime_ns, settings)
        try:
            data = path.read_bytes()  # the only disk read for this image
        except OSError as exc:
            return False, image_id, f"FILE_UNREADABLE: {path.name}: {exc}"
        sha256 = hashlib.sha256(data).hexdigest()
        loaded = load_image_bytes(data, path.name, settings.max_detect_side)
        meta = extract_metadata(loaded.exif, loaded.width, loaded.height, mtime_ns)
        record = ImageRecord(
            image_id=image_id,
            path=path,
            meta=meta,
            sha256=sha256,
            phash=compute_phash(loaded.pil),
            features=compute_features(loaded.pil),
            fmt=loaded.format or None,
        )
        faces = detector.detect(loaded)
        if (
            settings.tiled_detection
            and max(loaded.width, loaded.height) > settings.max_detect_side * 1.5
        ):
            big = load_image_bytes(data, path.name, settings.tile_source_side)
            faces = merge_faces(faces + detector.detect_tiled(big, settings.tile_size))
            del big
        record.faces = process_faces(
            image_id, path, faces, settings, recognizer=recognizer, data=data
        )
        del data
        try:
            record.thumb_path = str(
                save_thumbnail(
                    loaded.pil,
                    image_id,
                    path,
                    settings.thumbnails_dir,
                    settings.thumbnail_size,
                    settings.jpeg_quality,
                )
            )
        except OSError as exc:
            log.warning("Thumbnail not written for %s: %s", path.name, exc)
        result = record.to_result()
        result.update(analyze_image(loaded, path.name, meta.exif_ts, meta.ts_source))
        if tagger is not None:
            try:
                tags, vec = tagger.tag(loaded.pil)
                result["tags"], result["tag_model"] = tags, tagger.signature
                if settings.store_embeddings:
                    result["embedding"] = vec
            except Exception as exc:  # noqa: BLE001 - tagging must never fail a photo
                log.warning("Tagging skipped for %s: %s", path.name, exc)
        return True, image_id, result
    except ImageLoadError as exc:
        return False, image_id, str(exc)
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
        log.exception("Failed processing %s", path_str)
        return False, image_id, f"{type(exc).__name__}: {exc}"


_gc_counter = 0


def _process_one(task: _Task) -> _Outcome:
    """Process one image, then optionally sleep to honour ``cpu_limit``."""
    global _gc_counter
    start = time.perf_counter()
    outcome = _process_one_inner(task)
    _gc_counter += 1  # racy across threads, but only used to space out gc runs
    if _gc_counter % 50 == 0:
        gc.collect()
    settings = getattr(_tls, "settings", None)
    limit = settings.cpu_limit if settings else 1.0
    if 0 < limit < 1.0:
        time.sleep((time.perf_counter() - start) * (1.0 / limit - 1.0))
    return outcome


# ----------------------------------------------------------------------
# Stages
# ----------------------------------------------------------------------
def _watch(
    files: Iterator[tuple[Path, int, int]], control: RunControl
) -> Iterator[tuple[Path, int, int]]:
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


def _ensure_sface(settings: Settings) -> None:
    marker = settings.models_dir / ".sface_download_failed"
    try:
        if (
            not settings.sface_path.is_file()
            and marker.is_file()
            and time.time() - marker.stat().st_mtime < 3600
        ):
            log.warning(
                "SFace download failed recently; people grouping disabled for now "
                "(delete %s to retry now)",
                marker,
            )
            return
    except OSError:
        pass
    try:
        ensure_model(settings.sface_path, SFACE_URL, SFACE_SHA256)
        marker.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("Face recognition model unavailable, people grouping disabled: %s", exc)
        try:
            marker.write_text(str(exc)[:500], encoding="utf-8")
        except OSError:
            pass


def _make_process_executor(settings: Settings, workers: int) -> ProcessPoolExecutor:
    import multiprocessing

    recycle = None if sys.platform == "win32" else (settings.worker_recycle_tasks or None)
    mp_context = None if sys.platform == "win32" else multiprocessing.get_context("spawn")
    return ProcessPoolExecutor(
        max_workers=workers,
        max_tasks_per_child=recycle,
        mp_context=mp_context,
        initializer=_init_worker,
        initargs=(settings, True),
    )


def _make_thread_executor(settings: Settings, workers: int) -> ThreadPoolExecutor:
    return ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="photo-worker",
        initializer=_init_thread,
        initargs=(settings,),
    )


def _run_isolated(settings: Settings, task: _Task) -> _Outcome:
    """Run one task in its own throwaway process, so a crash only blames that image."""
    ex = _make_process_executor(settings, 1)
    try:
        return ex.submit(_process_one, task).result()
    except BrokenProcessPool:
        return False, task[0], f"WORKER_CRASHED: {Path(task[1]).name} killed its worker process"
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def _choose_mode(settings: Settings, workers: int) -> tuple[str, int]:
    """Pick ``(mode, n_workers)``: 'process', 'thread' or 'inline'."""
    cpus = os.cpu_count() or 2
    if sys.platform == "win32":
        n = min(workers, _MAX_THREADS, cpus)
        return ("thread", n) if n > 1 else ("inline", 1)
    n = min(workers, max(1, cpus // 2))
    return ("process", n) if n > 1 else ("inline", 1)


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
        PipelineError: if worker processes/threads keep failing.
    """
    if retry_failed:
        log.info("Re-queued %d failed image(s)", db.retry_failed())
    total = db.count_pending()
    if total == 0:
        return ProcessSummary(0, 0, 0, False)

    settings.ensure_dirs()
    if settings.detector_backend.lower() == "yunet":
        ensure_model(settings.yunet_path)
    _ensure_sface(settings)
    try:
        create_tagger(settings)
    except Exception as exc:
        log.warning("Scene tagging unavailable: %s. Tagging will be skipped.", exc)
        settings = replace(settings, tagging_enabled=False)
    if settings.low_priority:
        lower_process_priority()

    workers = settings.workers
    if settings.storage_type == "hdd" and workers > 2:
        log.info(
            "HDD mode: using 2 workers instead of %d (parallel reads slow a hard drive)", workers
        )
        workers = 2

    if control is not None:
        control.emit(
            ProgressEvent("process", 0, total, message=f"Starting analysis of {total} photos...")
        )

    mode, n_workers = _choose_mode(settings, workers)
    log.info("Processing %d image(s): mode=%s, workers=%d", total, mode, n_workers)

    executor: Executor | None = None
    if mode == "process":
        create_detector(settings).close()  # fail fast, before spawning workers
        executor = _make_process_executor(settings, n_workers)
    elif mode == "thread":
        create_detector(settings).close()  # fail fast, before starting threads
        # cv2's thread count is process-wide: split it so N threads don't oversubscribe.
        cv2.setNumThreads(max(1, settings.cv_threads // n_workers))
        executor = _make_thread_executor(settings, n_workers)
    else:
        _init_worker(settings, False)

    done = failed = 0
    interrupted = False
    crash: BrokenExecutor | None = None
    crash_events = 0
    max_crashes = 3
    attempted: set[int] = set()  # guards against refetching the same rows forever
    bar = tqdm(total=total, unit="img", disable=not show_progress)
    try:
        while True:
            if control is not None and not control.checkpoint():
                interrupted = True
                break
            rows = [r for r in db.fetch_pending(settings.batch_size) if r["id"] not in attempted]
            if not rows:
                break
            tasks: list[_Task] = [(r["id"], r["path"], r["mtime_ns"]) for r in rows]
            attempted.update(t[0] for t in tasks)
            names = {t[0]: t[1] for t in tasks}
            ok: list[dict[str, Any]] = []
            bad: list[tuple[int, str]] = []
            handled: set[int] = set()

            def _handle(outcome: _Outcome) -> bool:
                """Record one outcome. Returns False if the run should stop."""
                success, image_id, payload = outcome
                if image_id in handled:
                    return True
                handled.add(image_id)
                if success:
                    ok.append(payload)
                else:
                    bad.append((image_id, payload))
                    log.warning("Failed: %s", payload)
                bar.update(1)
                if control is not None:
                    control.emit(
                        ProgressEvent(
                            "process",
                            done + failed + len(ok) + len(bad),
                            total,
                            failed + len(bad),
                            Path(names[image_id]).name,
                        )
                    )
                    return control.checkpoint()
                return True

            crashed_exc: BrokenExecutor | None = None
            futures: dict = {}
            try:
                if executor is not None:
                    futures = {executor.submit(_process_one, t): t[0] for t in tasks}
                    for fut in as_completed(futures):
                        if not _handle(fut.result()):
                            interrupted = True
                            break
                else:
                    for t in tasks:
                        if not _handle(_process_one(t)):
                            interrupted = True
                            break
            except KeyboardInterrupt:
                interrupted = True
            except BrokenExecutor as exc:
                crashed_exc = exc

            # On cancel/interrupt: drop queued work, but keep anything already finished.
            if interrupted and futures:
                for fut in futures:
                    fut.cancel()
                for fut in futures:
                    if fut.cancelled():
                        continue
                    try:
                        _handle(fut.result())
                    except (BrokenExecutor, KeyboardInterrupt):
                        break
                    except Exception:  # noqa: BLE001
                        pass

            if crashed_exc is not None:
                crash_events += 1
                if mode == "process":
                    # Find the culprit by re-running unfinished images one at a time.
                    log.warning(
                        "Worker pool crashed (%s); isolating unfinished images...", crashed_exc
                    )
                    if executor is not None:
                        executor.shutdown(wait=False, cancel_futures=True)
                        executor = None
                    for t in tasks:
                        if t[0] in handled:
                            continue
                        if not _handle(_run_isolated(settings, t)):
                            interrupted = True
                            break
                    if crash_events > max_crashes:
                        crash = crashed_exc
                        interrupted = True  # stop cleanly; progress below is still saved
                    elif not interrupted:
                        executor = _make_process_executor(settings, n_workers)
                else:
                    # A broken thread pool means its initializer failed (e.g. a model could
                    # not load). Retrying would fail the same way, so stop cleanly.
                    log.error("Thread pool failed to start workers: %s", crashed_exc)
                    crash = crashed_exc
                    interrupted = True

            db.save_results(ok)  # partial batches are kept on cancel/interrupt/crash
            db.save_failures(bad)
            done += len(ok)
            failed += len(bad)
            if interrupted:
                break
    finally:
        bar.close()
        if executor is not None:
            # Threads must finish their current image before their models are closed.
            wait = mode == "thread" or not (interrupted or crash)
            executor.shutdown(wait=wait, cancel_futures=True)
        _close_all()

    if done:
        db.restore_marks()  # marks follow photos that moved, or came back after a reset

    if control is not None:
        control.emit(
            ProgressEvent(
                "process",
                done + failed,
                total,
                failed,
                message="interrupted" if interrupted else "complete",
            )
        )
    if crash is not None:
        raise PipelineError(
            "Workers failed repeatedly (possibly out of memory or a model failed to load). "
            "Progress so far is saved; re-run to continue, or try a smaller --workers value."
        ) from crash
    if interrupted:
        log.warning("Interrupted. Progress is saved; re-run to continue.")
    return ProcessSummary(done, failed, db.count_pending(), interrupted)


from services.pipeline.pipeline_steps import (  # noqa: E402
    update_bursts,
    update_duplicates,
    update_groups,
    update_persons,
    update_places,
    update_search_index,
)


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
    refresh_states(db)  # lets moved files be recognised
    summary = process_pending(
        settings, db, retry_failed=retry_failed, show_progress=show_progress, control=control
    )
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
                log.error("Stage %s failed", stage_name, exc_info=True)
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
        if prefix is not None and not os.path.normcase(os.path.realpath(path)).startswith(prefix):
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