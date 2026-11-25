"""RPC handlers for workspace stats, doctor, maintenance, config, prefs, and folder scanning."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from bridge.progress import StageProgress, describe
from bridge.protocol import BridgeError


def register_system_handlers(registry: dict[str, Any], ctx: Any) -> None:
    """Register system, maintenance, preferences, and scan lifecycle RPC handlers."""

    def system_init(_params: dict[str, Any]) -> dict[str, Any]:
        settings = getattr(ctx.engine, "settings", None) if ctx.engine else None
        return {
            "connected": ctx.engine is not None,
            "workspace": str(ctx.workspace),
            "backend_error": ctx.backend_error,
            "config_warnings": list(getattr(ctx.engine, "config_warnings", []) or []) if ctx.engine else [],
            "prefs": ctx.prefs.all(),
            "config": {
                "tagging_enabled": bool(getattr(settings, "tagging_enabled", False)),
                "store_embeddings": bool(getattr(settings, "store_embeddings", False)),
                "log_path": str(getattr(settings, "log_path", ctx.workspace / "photo_organizer.log")),
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

    def system_clear_cache(_params: dict[str, Any]) -> dict[str, Any]:
        eng = ctx.require_engine()
        with ctx.lock:
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
        with ctx.lock:
            return dict(
                eng.reset_workspace(clear_sources=clear_sources, clear_saved_searches=clear_saved) or {}
            )

    def scan_start(params: dict[str, Any]) -> dict[str, Any]:
        folder = str(params["folder"])
        if not Path(folder).is_dir():
            raise BridgeError("INVALID_FOLDER", f"Folder does not exist: {folder}")
        eng = ctx.require_engine()
        if ctx.scan_thread is not None and ctx.scan_thread.is_alive():
            raise BridgeError("SCAN_IN_PROGRESS", "A scan is already running.")

        progress = StageProgress()

        def on_event(ev: Any) -> None:
            ev_dict = ev.to_dict() if hasattr(ev, "to_dict") else (dict(ev) if isinstance(ev, dict) else {})
            if not ev_dict:
                ev_dict = {
                    "stage": getattr(ev, "stage", ""),
                    "done": getattr(ev, "done", 0),
                    "total": getattr(ev, "total", 0),
                    "current": getattr(ev, "current", "") or "",
                    "message": getattr(ev, "message", "") or "",
                }
            ctx.emit_event("scan.progress", {
                "percent": progress.update(ev_dict),
                "label": describe(ev_dict),
                "raw": ev_dict,
            })

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

    registry.update({
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
        "scan.start": scan_start,
        "scan.pause": scan_pause,
        "scan.resume": scan_resume,
        "scan.cancel": scan_cancel,
    })
