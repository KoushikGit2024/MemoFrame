"""RPC handlers for workspace stats, doctor, maintenance, config, prefs, and folder scanning."""

from __future__ import annotations

import os
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from backend.config import (
    SFACE_FILENAME,
    SFACE_SHA256,
    SFACE_URL,
    YUNET_FILENAME,
    YUNET_SHA256,
    YUNET_URL,
)
from backend.utils.file_utils import atomic_write_bytes, ensure_dir, sha256_file
from bridge.progress import StageProgress, StepProgress, describe
from bridge.protocol import BridgeError


def register_system_handlers(registry: dict[str, Any], ctx: Any) -> None:
    """Register system, maintenance, preferences, and scan lifecycle RPC handlers."""

    def system_init(_params: dict[str, Any]) -> dict[str, Any]:
        settings = getattr(ctx.engine, "settings", None) if ctx.engine else None
        return {
            "connected": ctx.engine is not None,
            "workspace": str(ctx.workspace),
            "backend_error": ctx.backend_error,
            "config_warnings": list(getattr(ctx.engine, "config_warnings", []) or [])
            if ctx.engine
            else [],
            "prefs": ctx.prefs.all(),
            "config": {
                "tagging_enabled": bool(getattr(settings, "tagging_enabled", False)),
                "store_embeddings": bool(getattr(settings, "store_embeddings", False)),
                "log_path": str(
                    getattr(settings, "log_path", ctx.workspace / "photo_organizer.log")
                ),
            },
        }

    def prefs_set(params: dict[str, Any]) -> dict[str, Any]:
        return ctx.prefs.set(str(params["key"]), params.get("value"))

    def system_stats(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
            return dict(eng.stats() or {})

    def system_doctor(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
            return dict(eng.doctor() or {})

    def system_clear_cache(params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        kinds = params.get("kinds") or ["thumbnails", "face_crops", "annotated"]
        with ctx.lock:
            try:
                res = dict(eng.clear_cache(kinds) or {})
            except TypeError:
                res = dict(eng.clear_cache() or {})
        return {"details": res, "freed_mb": sum(res.values()) if res else 0}

    def system_export_diagnostics(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
            path = eng.export_diagnostics()
        return {"path": str(path) if path else None}

    def system_update_config(params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        tagging = bool(params["tagging_enabled"])
        embeddings = bool(params["store_embeddings"])
        with ctx.lock:
            eng.update_config(tagging_enabled=tagging, store_embeddings=embeddings)
        return {"tagging_enabled": tagging, "store_embeddings": embeddings}

    def system_tag_existing(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
            return dict(eng.tag_existing() or {})

    def system_check_files(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
            return dict(eng.check_files() or {})

    def system_forget_missing(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
            removed = eng.forget_missing()
        return {"removed": int(removed or 0)}

    def system_moves(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
            rows = list(eng.moves() or [])
        return {"count": len(rows), "rows": rows}

    def system_rebuild(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
            return dict(eng.rebuild() or {})

    def system_repair(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
            return dict(eng.repair() or {})

    def system_reset_workspace(params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        clear_sources = bool(params.get("clear_sources", False))
        clear_saved = bool(params.get("clear_saved_searches", False))

        # Race condition guard: Cancel and wait for active scan before wiping workspace
        if ctx.scan_thread is not None and ctx.scan_thread.is_alive():
            try:
                eng.control.cancel()
                ctx.scan_thread.join(timeout=3.0)
            except Exception:
                pass

        with ctx.lock:
            return dict(
                eng.reset_workspace(clear_sources=clear_sources, clear_saved_searches=clear_saved)
                or {}
            )

    def scan_start(params: dict[str, Any]) -> dict[str, Any]:
        folder = str(params["folder"])
        if not Path(folder).is_dir():
            raise BridgeError("INVALID_FOLDER", f"Folder does not exist: {folder}")
        eng = ctx.require_engine()
        if ctx.scan_thread is not None and ctx.scan_thread.is_alive():
            raise BridgeError("SCAN_IN_PROGRESS", "A scan is already running.")

        # Race condition barrier: Ensure required models are verified on disk before scanning
        st = models_status({})
        if not st.get("ready"):
            raise BridgeError(
                "MODELS_NOT_READY",
                "AI face detection and recognition models are not downloaded or verified.",
                "Please wait for model download to complete or trigger models.download first.",
            )

        step_progress = StepProgress()

        def on_event(ev: Any) -> None:
            ev_dict = (
                ev.to_dict()
                if hasattr(ev, "to_dict")
                else (dict(ev) if isinstance(ev, dict) else {})
            )
            if not ev_dict:
                ev_dict = {
                    "stage": getattr(ev, "stage", ""),
                    "done": getattr(ev, "done", 0),
                    "total": getattr(ev, "total", 0),
                    "current": getattr(ev, "current", "") or "",
                    "message": getattr(ev, "message", "") or "",
                }
            pct = step_progress.update(ev_dict)
            ctx.emit_event(
                "scan.progress",
                {
                    "percent": pct,
                    "label": describe(ev_dict),
                    "stage": ev_dict.get("stage", ""),
                    "done": ev_dict.get("done", 0),
                    "total": ev_dict.get("total", 0),
                    "raw": ev_dict,
                },
            )

        def worker() -> None:
            prev_cb = getattr(eng, "on_event", None)
            try:
                eng.on_event = on_event
                eng.run_all(folder)
                ctx.emit_event("scan.finished", {"folder": folder})
            except Exception as exc:
                ctx.emit_event("scan.error", {"message": str(exc)})
            finally:
                eng.on_event = prev_cb

        ctx.scan_thread = threading.Thread(target=worker, name="MemoFrameScan", daemon=True)
        ctx.scan_thread.start()
        return {"started": True, "folder": folder}

    def scan_pause(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        eng.control.pause()
        return {"paused": True}

    def scan_resume(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        eng.control.resume()
        return {"paused": False}

    def scan_cancel(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        eng.control.cancel()
        return {"cancelling": True}

    def _verify_model(path: Path, expected_sha256: str) -> bool:
        if not path.is_file() or path.stat().st_size < 10_000:
            return False
        if os.environ.get("MEMOFRAME_SKIP_MODEL_HASH") == "1":
            return True
        if expected_sha256:
            try:
                return sha256_file(path).lower() == expected_sha256.lower()
            except Exception:
                return False
        return True

    def models_status(_params: dict[str, Any]) -> dict[str, Any]:
        models_dir = ctx.workspace / "models"
        yunet_path = models_dir / YUNET_FILENAME
        sface_path = models_dir / SFACE_FILENAME

        yunet_ok = _verify_model(yunet_path, YUNET_SHA256)
        sface_ok = _verify_model(sface_path, SFACE_SHA256)

        missing = []
        if not yunet_ok:
            missing.append("yunet")
        if not sface_ok:
            missing.append("sface")

        return {
            "ready": len(missing) == 0,
            "missing": missing,
            "models": {
                "yunet": {
                    "name": "Face Detection (YuNet)",
                    "filename": YUNET_FILENAME,
                    "present": yunet_ok,
                    "size_bytes": yunet_path.stat().st_size if yunet_path.is_file() else 0,
                },
                "sface": {
                    "name": "Face Recognition (SFace)",
                    "filename": SFACE_FILENAME,
                    "present": sface_ok,
                    "size_bytes": sface_path.stat().st_size if sface_path.is_file() else 0,
                },
            },
        }

    _download_lock = threading.Lock()
    _download_active = False

    def models_download(_params: dict[str, Any]) -> dict[str, Any]:
        nonlocal _download_active
        models_dir = ctx.workspace / "models"
        ensure_dir(models_dir)

        status = models_status({})
        if status["ready"]:
            return {"ready": True, "downloaded": []}

        if _download_active:
            return {"downloading": True, "message": "Download already in progress"}

        def download_worker() -> None:
            nonlocal _download_active
            with _download_lock:
                _download_active = True
                try:
                    targets = [
                        (
                            "yunet",
                            "Face Detection (YuNet)",
                            YUNET_FILENAME,
                            YUNET_URL,
                            YUNET_SHA256,
                            232_589,
                        ),
                        (
                            "sface",
                            "Face Recognition (SFace)",
                            SFACE_FILENAME,
                            SFACE_URL,
                            SFACE_SHA256,
                            38_696_353,
                        ),
                    ]
                    for key, display_name, filename, url, sha, est_total in targets:
                        dest = models_dir / filename
                        if _verify_model(dest, sha):
                            ctx.emit_event(
                                "models.progress",
                                {
                                    "model": key,
                                    "name": display_name,
                                    "downloaded": dest.stat().st_size,
                                    "total": dest.stat().st_size,
                                    "percent": 100,
                                    "stage": "ready",
                                },
                            )
                            continue

                        ctx.emit_event(
                            "models.progress",
                            {
                                "model": key,
                                "name": display_name,
                                "downloaded": 0,
                                "total": est_total,
                                "percent": 0,
                                "stage": "downloading",
                            },
                        )

                        req = urllib.request.Request(url, headers={"User-Agent": "memoframe/1.0"})
                        tmp_dest = dest.with_suffix(".tmp")
                        downloaded_bytes = 0

                        with (
                            urllib.request.urlopen(req, timeout=60) as resp,
                            open(tmp_dest, "wb") as f_out,
                        ):
                            content_len = resp.headers.get("Content-Length")
                            total_bytes = (
                                int(content_len)
                                if content_len and content_len.isdigit()
                                else est_total
                            )

                            chunk_size = 128 * 1024  # 128 KB
                            while True:
                                chunk = resp.read(chunk_size)
                                if not chunk:
                                    break
                                f_out.write(chunk)
                                downloaded_bytes += len(chunk)
                                pct = (
                                    min(99, int((downloaded_bytes / total_bytes) * 100))
                                    if total_bytes > 0
                                    else 50
                                )
                                ctx.emit_event(
                                    "models.progress",
                                    {
                                        "model": key,
                                        "name": display_name,
                                        "downloaded": downloaded_bytes,
                                        "total": total_bytes,
                                        "percent": pct,
                                        "stage": "downloading",
                                    },
                                )

                        # Atomic move
                        if dest.exists():
                            try:
                                dest.unlink()
                            except OSError:
                                pass
                        tmp_dest.replace(dest)

                        if not _verify_model(dest, sha):
                            raise BridgeError(
                                "VERIFICATION_FAILED", f"Model verification failed for {filename}"
                            )

                        ctx.emit_event(
                            "models.progress",
                            {
                                "model": key,
                                "name": display_name,
                                "downloaded": downloaded_bytes,
                                "total": downloaded_bytes,
                                "percent": 100,
                                "stage": "done",
                            },
                        )

                    ctx.emit_event("models.ready", {"ready": True})
                except Exception as exc:
                    ctx.emit_event("models.error", {"message": str(exc)})
                finally:
                    _download_active = False

        t = threading.Thread(target=download_worker, name="ModelDownloader", daemon=True)
        t.start()
        return {"started": True}

    def system_open_file(params: dict[str, Any]) -> dict[str, Any]:
        """Launch the system default application for a photo or directory path."""
        p_str = str(params.get("path") or "").strip()
        if not p_str:
            return {"ok": False, "error": "Path cannot be empty"}
        p = Path(p_str)
        if not p.exists():
            return {"ok": False, "error": f"File not found: {p_str}"}

        import subprocess
        import sys

        try:
            if sys.platform.startswith("win"):
                os.startfile(str(p))  # type: ignore[attr-defined]
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    registry.update(
        {
            "system.init": system_init,
            "prefs.set": prefs_set,
            "system.stats": system_stats,
            "system.doctor": system_doctor,
            "system.clear_cache": system_clear_cache,
            "system.export_diagnostics": system_export_diagnostics,
            "system.update_config": system_update_config,
            "system.tag_existing": system_tag_existing,
            "system.check_files": system_check_files,
            "system.forget_missing": system_forget_missing,
            "system.moves": system_moves,
            "system.rebuild": system_rebuild,
            "system.repair": system_repair,
            "system.reset_workspace": system_reset_workspace,
            "system.open_file": system_open_file,
            "scan.start": scan_start,
            "scan.pause": scan_pause,
            "scan.resume": scan_resume,
            "scan.cancel": scan_cancel,
            "models.status": models_status,
            "models.download": models_download,
        }
    )
