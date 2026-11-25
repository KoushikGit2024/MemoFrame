"""Public engine API for the Windows app.

Everything returns plain dicts, lists and numbers. Failures raise
:class:`EngineError` with a stable code. The engine only reads photos; all
writes go to the workspace.
"""
from __future__ import annotations

import functools
import logging
import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, TypeVar

from config import DEFAULT_WORKSPACE, Settings
from database import DatabaseManager
from engine.contract import API_VERSION
from engine.doctor import run_checks
from engine.errors import EngineError, ErrorCode, translate
from engine.lock import WorkspaceLock
from engine.settings_file import load_settings, write_default_config
from engine.profiles import apply_profile
from services.pipeline import maintenance
from services.pipeline import orchestrator as pipeline
from services.pipeline.control import ProgressCallback, RunControl
from utils.file_utils import is_within
from utils.model_downloader import install_bundled_model

_log = logging.getLogger("photo_organizer.engine")

MARK_KINDS = ("keep", "reviewed", "favourite", "hidden")
_HIDDEN_COLUMNS = {"features", "embedding", "vec"}
F = TypeVar("F", bound=Callable[..., Any])


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys() if k not in _HIDDEN_COLUMNS}


def _translated(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except EngineError:
            _log.warning("%s failed", fn.__name__, exc_info=True)
            raise
        except Exception as exc:  # noqa: BLE001
            _log.error("Engine call %s failed", fn.__name__, exc_info=True)
            raise translate(exc) from exc
    return wrapper  # type: ignore[return-value]


class Engine:
    """Open a workspace, run scans and processing, query results.

    Usage::

        with Engine("D:/photo_ws", profile="gentle", on_event=print) as eng:
            eng.run_all("D:/Photos")
            rows = eng.search(min_faces=2)

    Run long calls (``run_all``, ``process``) on a background thread or use the
    JSON runner (``python -m engine``); ``cancel``/``pause``/``resume`` are safe
    to call from another thread.
    """

    @_translated
    def __init__(
        self,
        workspace: Path | str | None = None,
        *,
        profile: str | None = None,
        on_event: ProgressCallback | None = None,
        settings: Settings | None = None,
        strict_config: bool = True,
    ) -> None:
        self.config_warnings: list[str] = []
        if settings is None:
            settings = load_settings(
                Path(workspace or DEFAULT_WORKSPACE),
                profile,
                strict=strict_config,
                warnings=self.config_warnings,
            )
        elif profile:
            settings = apply_profile(settings, profile)
        self.settings = settings
        self.control = RunControl(on_event, settings.min_free_mem_mb)
        self._db: DatabaseManager | None = None
        self._lock = WorkspaceLock(settings.workspace / ".workspace.lock")

    @property
    def on_event(self) -> ProgressCallback | None:
        """Currently registered progress callback."""
        return self.control._on_progress

    @on_event.setter
    def on_event(self, callback: ProgressCallback | None) -> None:
        """Safely attach or swap the progress callback."""
        self.control.set_callback(callback)

    # ---- lifecycle ------------------------------------------------------
    @_translated
    def open(self) -> "Engine":
        """Open the workspace. Raises WORKSPACE_LOCKED if another process has it open."""
        if self._db is None:
            self.settings.ensure_dirs()
            from utils.logger import setup_logging
            if not logging.getLogger("photo_organizer").handlers:
                setup_logging(self.settings.log_path)
            self._lock.acquire()
            try:
                write_default_config(self.settings.workspace)
                install_bundled_model(self.settings.yunet_path)
                install_bundled_model(self.settings.sface_path)
                self._db = DatabaseManager(self.settings.db_path).open()
            except BaseException:
                self._lock.release()
                raise
        return self

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        self._lock.release()

    @property
    def api_version(self) -> str:
        return API_VERSION

    def __enter__(self) -> "Engine":
        return self.open()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def db(self) -> DatabaseManager:
        if self._db is None:
            raise EngineError(ErrorCode.NOT_OPEN, "Engine is not open. Call open() or use 'with'.")
        return self._db

    @staticmethod
    def _source(root: Path | str) -> Path:
        path = Path(root).expanduser()
        if not path.is_dir():
            raise EngineError(ErrorCode.DRIVE_OFFLINE,
                              f"Folder not found or drive not connected: {path}",
                              "Reconnect the drive and try again.")
        return path.resolve()

    # ---- control --------------------------------------------------------
    def cancel(self) -> None:
        """Stop after the current image. Finished work is kept; run again to continue."""
        self.control.cancel()

    def pause(self) -> None:
        self.control.pause()

    def resume(self) -> None:
        self.control.resume()

    # ---- work -----------------------------------------------------------
    @_translated
    def scan(self, root: Path | str) -> dict[str, int]:
        self.control.reset()
        stats = pipeline.scan_directory(self.settings, self.db, self._source(root), self.control)
        return {**asdict(stats), "total": stats.total}

    @_translated
    def process(self, *, retry_failed: bool = False) -> dict[str, Any]:
        self.control.reset()
        summary = pipeline.process_pending(
            self.settings, self.db, retry_failed=retry_failed,
            show_progress=False, control=self.control)
        return asdict(summary)

    @_translated
    def run_all(self, root: Path | str, *, retry_failed: bool = False) -> dict[str, Any]:
        """Scan, process, then rebuild duplicates and groups."""
        source = self._source(root)
        self.control.reset()
        summary = pipeline.run_pipeline(
            self.settings, self.db, source, retry_failed=retry_failed,
            show_progress=False, control=self.control)
        return {**asdict(summary), "stats": self.db.report_stats()}

    @_translated
    def rescan(self, root: Path | str | None = None, *, retry_failed: bool = False) -> dict[str, Any]:
        """On-demand, offline rescan.

        Discovers new/modified photos, processes only pending items, updates duplicates
        and groups, and terminates without any persistent background polling or watchers.
        If root is None, rescans every previously known source folder.
        """
        self.control.reset()
        if root is not None:
            return self.run_all(root, retry_failed=retry_failed)
        sources = [Path(s) for s in self.db.list_sources()]
        if not sources:
            raise EngineError(ErrorCode.INVALID_INPUT,
                              "No folders to rescan. Pass a folder, or run a scan first.")
        total_processed = total_failed = 0
        interrupted = False
        for s in sources:
            if s.is_dir():
                res = pipeline.run_pipeline(
                    self.settings, self.db, s, retry_failed=retry_failed,
                    show_progress=False, control=self.control)
                total_processed += res.processed
                total_failed += res.failed
                if res.interrupted:
                    interrupted = True
                    break
        return {
            "processed": total_processed,
            "failed": total_failed,
            "interrupted": interrupted,
            "stats": self.db.report_stats(),
        }

    # ---- queries (plain data) -------------------------------------------
    @_translated
    def stats(self) -> dict[str, int]:
        return self.db.report_stats()

    @_translated
    def search(self, **filters: Any) -> list[dict[str, Any]]:
        """Filters: min_faces, max_faces, taken_from, taken_until, group_id,
        path_contains, limit, offset."""
        return [_row(r) for r in self.db.search_images(**filters)]

    @_translated
    def get_image(self, image_id: int) -> dict[str, Any] | None:
        row = self.db.get_image(image_id)
        return _row(row) if row else None

    @_translated
    def get_faces(self, image_id: int) -> list[dict[str, Any]]:
        """Face boxes in full-resolution pixels. Labels are local to one image."""
        return [_row(r) for r in self.db.get_faces(image_id)]

    @_translated
    def get_groups(self) -> list[dict[str, Any]]:
        return [_row(r) for r in self.db.get_groups()]

    @_translated
    def get_group_images(self, group_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        rows = [_row(r) for r in self.db.get_group_images(group_id)]
        return rows[:limit] if limit is not None else rows

    @_translated
    def get_duplicate_clusters(self) -> dict[int, list[dict[str, Any]]]:
        from services.organization.duplicates import choose_keeper
        out = {}
        for cid, members in self.db.get_duplicate_clusters().items():
            dict_members = [_row(m) for m in members]
            keeper = choose_keeper(dict_members)
            out[cid] = [{**m, "suggested_keep": int(m["id"]) == keeper} for m in dict_members]
        return out

    @_translated
    def get_persons(self) -> list[dict[str, Any]]:
        """List all identified person clusters with names, cover faces, and counts."""
        return [_row(r) for r in self.db.list_persons()]

    @_translated
    def get_person(self, person_id: int) -> dict[str, Any] | None:
        """Get details for a single person cluster."""
        row = self.db.get_person(person_id)
        return _row(row) if row else None

    @_translated
    def rename_person(self, person_id: int, new_name: str, confirm_faces: bool = False) -> bool:
        """Name a person. Faces are only locked (and their boxes labeled) when
        ``confirm_faces`` is True; otherwise name faces individually with name_face()."""
        clean = (new_name or "").strip()
        if not clean:
            raise EngineError(ErrorCode.INVALID_INPUT, "Person name cannot be empty.")
        if self.db.get_person(person_id) is None:
            raise EngineError(ErrorCode.INVALID_INPUT, f"No person with id {person_id}.")
        ok = self.db.rename_person(person_id, clean)
        if ok:
            if confirm_faces:
                self.db.confirm_person(person_id)
            pipeline.update_search_index(self.settings, self.db)
        return ok

    def _people_changed(self) -> None:
        pipeline.update_search_index(self.settings, self.db)   # names in the text index

    @_translated
    def get_person_faces(self, person_id: int, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        """Faces of one person, best first. ``locked`` = confirmed by the user."""
        return [_row(r) for r in self.db.person_faces(person_id, limit, offset)]

    @_translated
    def get_unassigned_faces(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        return [_row(r) for r in self.db.unassigned_faces(limit, offset)]

    @_translated
    def assign_face(self, face_id: int, person_id: int | None) -> None:
        """Move a face to a person, or pass None to remove it from all people. Permanent."""
        self.db.assign_face(face_id, person_id)
        self._people_changed()

    @_translated
    def create_person(self, name: str, face_ids: list[int]) -> int:
        """Make a new named person from specific faces. Returns the new person id."""
        pid = self.db.create_person(name, face_ids)
        self._people_changed()
        return pid

    @_translated
    def merge_persons(self, keep_id: int, merge_id: int) -> dict[str, Any] | None:
        """Merge two clusters of the same person. ``merge_id`` disappears."""
        self.db.merge_persons(keep_id, merge_id)
        self._people_changed()
        return self.get_person(keep_id)

    @_translated
    def confirm_person(self, person_id: int) -> int:
        """Mark a cluster as correct: its faces are locked. Returns how many."""
        return self.db.confirm_person(person_id)

    @_translated
    def unlock_face(self, face_id: int) -> bool:
        """Let automatic clustering decide this face again (effective on next rebuild)."""
        return self.db.unlock_face(face_id)

    @_translated
    def failed_images(self) -> list[dict[str, Any]]:
        return [_row(r) for r in self.db.failed_images()]

    @_translated
    def live_video(self, image_id: int) -> dict[str, Any] | None:
        """The video component of a Live Photo, or None."""
        row = self.db.get_paired_video(image_id)
        return _row(row) if row else None

    # ---- marks (database only) -------------------------------------------
    @_translated
    def set_mark(self, image_id: int, kind: str, note: str | None = None) -> None:
        if kind not in MARK_KINDS:
            raise EngineError(ErrorCode.INVALID_INPUT,
                              f"Unknown mark {kind!r}. Use one of: {', '.join(MARK_KINDS)}.")
        if self.db.get_image(image_id) is None:
            raise EngineError(ErrorCode.INVALID_INPUT, f"No image with id {image_id}.")
        self.db.set_mark(image_id, kind, note)

    @_translated
    def clear_mark(self, image_id: int, kind: str) -> bool:
        return self.db.clear_mark(image_id, kind)

    @_translated
    def get_marks(self, image_id: int | None = None, kind: str | None = None) -> list[dict[str, Any]]:
        return [_row(r) for r in self.db.get_marks(image_id, kind)]

    # ---- Phase B: file states, cache, health ------------------------------
    @_translated
    def check_files(self) -> dict[str, int]:
        """Mark photos ok / offline / missing. Returns counts. Nothing on disk changes."""
        return maintenance.refresh_states(self.db)

    @_translated
    def forget_missing(self) -> int:
        """Drop DATABASE records of photos confirmed missing (never offline ones)."""
        n = maintenance.forget_missing(self.settings, self.db)
        if n:
            pipeline.update_duplicates(self.settings, self.db)
            pipeline.update_groups(self.settings, self.db)
            pipeline.update_persons(self.settings, self.db)
        return n

    @_translated
    def rebuild(self) -> dict[str, int]:
        """Force-rebuild duplicates, places, bursts and groups (e.g. after changing settings)."""
        return {"duplicate_clusters": pipeline.update_duplicates(self.settings, self.db, force=True),
                "places_named": pipeline.update_places(self.settings, self.db, force=True),
                "bursts": pipeline.update_bursts(self.settings, self.db, force=True),
                "groups": pipeline.update_groups(self.settings, self.db, force=True),
                "persons": pipeline.update_persons(self.settings, self.db, force=True),
                "search_index": pipeline.update_search_index(self.settings, self.db, force=True)}

    @_translated
    def thumbnail(self, image_id: int) -> str:
        """Path of the image's thumbnail, recreated from the original if needed."""
        return str(maintenance.get_thumbnail(self.settings, self.db, image_id))

    @_translated
    def cache_info(self) -> dict[str, dict[str, int]]:
        return maintenance.cache_info(self.settings)

    @_translated
    def clear_cache(self, kinds: list[str] | None = None) -> dict[str, int]:
        return maintenance.clear_cache(self.settings, self.db, kinds or ["thumbnails"])

    @_translated
    def maintenance(self, vacuum: bool = False) -> dict[str, Any]:
        return maintenance.run_maintenance(self.settings, self.db, vacuum)

    @_translated
    def repair(self) -> dict[str, int]:
        return self.db.repair()

    # ---- Phase D ----------------------------------------------------------
    def _recog_sig(self) -> str:
        return f"{self.settings.detector_backend}|{self.settings.sface_path.stat().st_size}"

    @_translated
    def recognize_existing(self, force: bool = False) -> dict[str, int]:
        """Backfill face recognition on photos processed before SFace was downloaded.
        Runs once per (detector backend, SFace file); faces that still get no embedding
        (too small, no landmarks) are not retried until one of those changes or force=True."""
        if not self.settings.sface_path.is_file():
            raise EngineError(ErrorCode.MODEL_MISSING,
                              f"Face recognition model not found at {self.settings.sface_path}. "
                              "Run doctor or process a photo to download it.")
        sig = self._recog_sig()
        if not force and self.db.get_meta("recog_backfill") == sig:
            return {"requeued": 0, "processed": 0}
        self.control.reset()
        requeued = self.db.requeue_faces_without_embeddings()
        processed = 0
        interrupted = False
        if requeued:
            summary = pipeline.process_pending(
                self.settings, self.db, show_progress=False, control=self.control)
            processed, interrupted = summary.processed, summary.interrupted
            pipeline.update_persons(self.settings, self.db)
            pipeline.update_search_index(self.settings, self.db)
        if not interrupted:
            self.db.set_meta("recog_backfill", sig)
        return {"requeued": requeued, "processed": processed}

    @_translated
    def analyze_existing(self) -> dict[str, int]:
        """Fill quality, dHash, content type and date flags for photos processed earlier."""
        from services.pipeline.enrich import enrich_existing
        self.control.reset()
        n = enrich_existing(self.settings, self.db, self.control)
        return {"analyzed": n, **self.rebuild()}

    @_translated
    def get_bursts(self) -> list[dict[str, Any]]:
        return [_row(r) for r in self.db.get_bursts()]

    @_translated
    def get_burst_images(self, burst_id: int) -> list[dict[str, Any]]:
        return [_row(r) for r in self.db.get_burst_images(burst_id)]

    @_translated
    def suspicious_dates(self, limit: int = 500) -> list[dict[str, Any]]:
        return [_row(r) for r in self.db.suspicious_dates(limit)]

    @_translated
    def set_date_override(self, image_id: int, iso_datetime: str, note: str | None = None) -> None:
        """Correct a photo's date in the DATABASE only. Format: YYYY-MM-DDTHH:MM:SS."""
        from datetime import datetime
        try:
            datetime.strptime(iso_datetime, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            raise EngineError(ErrorCode.INVALID_INPUT, "Use the format YYYY-MM-DDTHH:MM:SS.")
        if self.db.get_image(image_id) is None:
            raise EngineError(ErrorCode.INVALID_INPUT, f"No image with id {image_id}.")
        self.db.set_date_override(image_id, iso_datetime, note)

    @_translated
    def clear_date_override(self, image_id: int) -> bool:
        return self.db.clear_date_override(image_id)

    @_translated
    def low_confidence_faces(self, below: float = 0.8, limit: int = 500) -> list[dict[str, Any]]:
        """Detected faces the app may want the user to review (boxes only)."""
        return [_row(r) for r in self.db.low_confidence_faces(below, limit)]

    # ---- Phase E ----------------------------------------------------------
    @_translated
    def find(self, *, sort: str = "date", limit: int = 100, offset: int = 0,
             **filters: Any) -> list[dict[str, Any]]:
        """Combined search. Filters: text, min_faces, max_faces, taken_from, taken_until,
        group_id, path_contains, place_contains, content_type, kind, format, min_quality,
        burst_id, in_burst, duplicate (none/any/exact/near), mark, no_mark,
        include_missing, include_live_video, include_hidden.
        ``sort``: date, date_desc, quality, path, size. Bad filters raise INVALID_INPUT."""
        if filters.get("text"):
            pipeline.update_search_index(self.settings, self.db)
        return [_row(r) for r in self.db.find_images(sort=sort, limit=limit, offset=offset, **filters)]

    @_translated
    def count(self, **filters: Any) -> int:
        if filters.get("text"):
            pipeline.update_search_index(self.settings, self.db)
        return self.db.count_images(**filters)

    @_translated
    def timeline(self, granularity: str = "month") -> list[dict[str, Any]]:
        return self.db.timeline(granularity)

    @_translated
    def save_search(self, name: str, filters: dict[str, Any]) -> None:
        self.db.save_search(name, filters)

    @_translated
    def list_saved_searches(self) -> list[dict[str, Any]]:
        return self.db.list_saved_searches()

    @_translated
    def delete_saved_search(self, name: str) -> bool:
        return self.db.delete_saved_search(name)

    @_translated
    def run_saved_search(self, name: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        saved = self.db.get_saved_search(name)
        if saved is None:
            raise EngineError(ErrorCode.INVALID_INPUT, f"No saved search named {name!r}.")
        return self.find(limit=limit, offset=offset, **saved)

    @_translated
    def moves(self) -> list[dict[str, Any]]:
        """Photos that appear to have been moved or renamed outside the app (marks follow them)."""
        maintenance.refresh_states(self.db)
        self.db.restore_marks()
        return [_row(r) for r in self.db.find_moves()]

    # ---- Phase F ----------------------------------------------------------
    @_translated
    def tag_existing(self) -> dict[str, int]:
        """Tag photos processed earlier (needs tagging_enabled and the model files)."""
        from services.intelligence.tagging import tag_existing
        self.control.reset()
        n = tag_existing(self.settings, self.db, self.control)
        pipeline.update_search_index(self.settings, self.db)
        return {"tagged": n}

    @_translated
    def get_tags(self, image_id: int) -> list[dict[str, Any]]:
        return [_row(r) for r in self.db.get_tags(image_id)]

    @_translated
    def list_tags(self, limit: int = 100) -> list[dict[str, Any]]:
        """Tags with photo counts, most common first (for a tag browser)."""
        return [{"label": r["label"], "count": int(r["n"])} for r in self.db.list_tag_counts(limit)]

    @_translated
    def similar(self, image_id: int, limit: int = 20) -> list[dict[str, Any]]:
        """Photos with a similar whole-image content, best first (needs stored embeddings)."""
        from services.intelligence.similar import find_similar
        out = []
        for other_id, score in find_similar(self.db, image_id, limit):
            row = self.db.get_image(other_id)
            if row is not None:
                out.append({**_row(row), "similarity": round(score, 4)})
        return out

    # ---- Phase G ----------------------------------------------------------
    @_translated
    def watch(self, folders: list[Path | str] | None = None, *, interval_s: float | None = None,
              settle_s: float | None = None, profile: str | None = "gentle",
              max_cycles: int | None = None) -> dict[str, int]:
        """Watch folders and process new or changed photos until ``cancel()`` is called.

        ``folders=None`` watches every folder scanned before. Runs on the calling thread, so
        call it from a worker thread. Events use stage ``watch`` (and ``waiting`` with
        message ``on battery``). Returns ``{"cycles", "processed", "failed"}``.
        """
        from services.pipeline.watcher import FolderWatcher
        roots = ([Path(f) for f in folders] if folders
                 else [Path(s) for s in self.db.list_sources()])
        if not roots:
            raise EngineError(ErrorCode.INVALID_INPUT,
                              "No folders to watch. Pass folders, or run a scan first.")
        self.control.reset()
        settings = apply_profile(self.settings, profile) if profile else self.settings
        return FolderWatcher(settings, self.db, roots, self.control,
                             interval_s=interval_s, settle_s=settle_s).run(max_cycles)

    @_translated
    def export_diagnostics(self, include_log: bool = True) -> str:
        """Write a diagnostics zip inside the workspace and return its path."""
        from engine.diagnostics import build_bundle
        return str(build_bundle(self.settings, self.doctor(), self.db.report_stats(), include_log))

    # ---- environment ----------------------------------------------------
    @_translated
    def doctor(self, source_dirs: list[Path | str] | None = None) -> dict[str, Any]:
        checks = run_checks(self.settings, source_dirs or [])
        return {"ok": not any(c.status == "fail" for c in checks),
                "checks": [c.to_dict() for c in checks]}

    @_translated
    def get_faces_many(self, image_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        """Faces of many images in a few queries, with `person_name` populated."""
        return {
            img_id: [_row(r) for r in rows]
            for img_id, rows in self.db.faces_for_images(image_ids).items()
        }

    @_translated
    def name_face(self, face_id: int, name: str) -> int:
        """Name a single face: reuses a person with `name` or creates one, and locks the face."""
        clean = (name or "").strip()
        if not clean:
            raise EngineError(ErrorCode.INVALID_INPUT, "Person name cannot be empty.")
        # Find existing person by this exact name (case-insensitive)
        existing = [p for p in self.get_persons() if p.get("name", "").lower() == clean.lower()]
        if existing:
            pid = int(existing[0]["id"])
            self.db.assign_face(face_id, pid)
        else:
            pid = self.db.create_person(clean, [face_id])
        self.db.set_face_locked(face_id, True)
        self._people_changed()
        return pid

    @_translated
    def reset_workspace(self, *, keep_generated: bool = False, clear_sources: bool = False,
                        clear_saved_searches: bool = False) -> dict[str, int]:
        """Clear the database and generated files. Original photos are never touched.
        Scanned folders and saved searches are kept unless you ask to clear them."""
        before = self.db.report_stats()["total_images"]
        self.db.reset()
        self.db.rebuild_fts()
        if clear_sources:
            self.db.clear_sources()
        if clear_saved_searches:
            self.db.clear_saved_searches()
        if not keep_generated:
            maintenance.clear_cache(self.settings, self.db,
                                    ("thumbnails", "face_crops", "annotated"))
            grouped = self.settings.grouped_dir
            if grouped.is_dir() and is_within(grouped, self.settings.workspace):
                shutil.rmtree(grouped, ignore_errors=True)
            self.settings.ensure_dirs()
        return {"images_removed": before, "cleared_images": before}
