"""RPC handlers for unified Error Intelligence, Controlled Self-Healing, and Config Audit Log."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from memoframe_engine.rpc.protocol import BridgeError


def register_error_handlers(registry: dict[str, Any], ctx: Any) -> None:
    """Register errors.*, recoveries.list, and system.audit_log RPC methods."""

    def errors_report(params: dict[str, Any]) -> dict[str, Any]:
        rec = ctx.observability.record_error(
            origin=str(params.get("origin") or "frontend"),
            category=str(params.get("category") or "runtime"),
            module=str(params.get("module") or "renderer"),
            message=str(params.get("message") or "Unhandled frontend error"),
            severity=str(params.get("severity") or "error"),
            code=str(params.get("code") or ""),
            stack_trace=str(params.get("stack_trace") or ""),
            correlation_id=str(params.get("correlation_id") or ""),
            context=dict(params.get("context") or {}),
        )
        ctx.emit_event("error.captured", {"error": rec})
        return {"recorded": True, "error": rec}

    def errors_list(params: dict[str, Any]) -> dict[str, Any]:
        items = ctx.observability.list_errors(
            severity=str(params.get("severity") or ""),
            origin=str(params.get("origin") or ""),
            status=str(params.get("status") or ""),
            query=str(params.get("query") or ""),
            range_key=str(params.get("range") or "all"),
            limit=int(params.get("limit") or 100),
        )
        return {"items": items, "total": len(items)}

    def errors_detail(params: dict[str, Any]) -> dict[str, Any]:
        error_id = int(params["error_id"])
        detail = ctx.observability.get_error_detail(error_id)
        if detail is None:
            raise BridgeError("NOT_FOUND", f"Error record #{error_id} not found.")
        return detail

    def errors_update_status(params: dict[str, Any]) -> dict[str, Any]:
        error_id = int(params["error_id"])
        status = str(params["status"])
        notes = params.get("notes")
        updated = ctx.observability.update_error_status(
            error_id,
            status,
            notes=str(notes) if notes is not None else None,
        )
        if updated is None:
            raise BridgeError("NOT_FOUND", f"Error record #{error_id} not found.")
        return {"error": updated}

    def errors_recover(params: dict[str, Any]) -> dict[str, Any]:
        error_id = int(params["error_id"])
        strategy = str(params.get("strategy") or "auto")
        detail = ctx.observability.get_error_detail(error_id)
        if detail is None:
            raise BridgeError("NOT_FOUND", f"Error record #{error_id} not found.")

        err_rec = detail["error"]
        if err_rec.get("recovery_class") == "never_auto" and strategy == "auto":
            rec = ctx.observability.record_recovery_attempt(
                error_id=error_id,
                strategy="blocked_policy",
                trigger_source="manual",
                outcome="skipped",
                duration_ms=0.0,
                final_state="requires_manual_review",
                detail="Safety policy blocks automatic repair for this error class.",
            )
            return {"attempt": rec}

        def run_safe_strategy() -> str:
            chosen = strategy
            if chosen == "auto":
                msg = str(err_rec.get("message") or "").lower()
                if "model" in msg or ".tmp" in msg:
                    chosen = "clean_tmp_models"
                elif "database" in msg or "sqlite" in msg or "locked" in msg:
                    chosen = "db_wal_checkpoint"
                else:
                    chosen = "ensure_workspace_dirs"

            if chosen == "clean_tmp_models":
                models_dir = ctx.workspace / "models"
                removed = 0
                if models_dir.is_dir():
                    for tmp in models_dir.rglob("*.tmp"):
                        tmp.unlink(missing_ok=True)
                        removed += 1
                return f"Cleaned {removed} stale .tmp model download file(s)."

            if chosen == "db_wal_checkpoint":
                if ctx.engine is None or not hasattr(ctx.engine, "db") or ctx.engine.db is None:
                    raise RuntimeError("Main engine database is not connected.")
                with ctx.lock:
                    conn = ctx.engine.db._conn
                    if conn is None:
                        ctx.engine.db.open()
                        conn = ctx.engine.db._conn
                    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                return "Verified SQLite connection and ran passive WAL checkpoint."

            if chosen == "ensure_workspace_dirs":
                for sub in ("models", "models/tags", "thumbnails", "face_crops", "annotated", "reports"):
                    (Path(ctx.workspace) / sub).mkdir(parents=True, exist_ok=True)
                return "Verified and ensured all workspace subdirectories exist."

            raise ValueError(f"Unsupported recovery strategy: {chosen}")

        attempt = ctx.observability.execute_recovery(
            error_id=error_id,
            strategy=strategy,
            trigger_source="manual",
            action_fn=run_safe_strategy,
        )
        ctx.emit_event("recovery.attempted", {"attempt": attempt})
        return {"attempt": attempt}

    def recoveries_list(params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit") or 100)
        items = ctx.observability.list_recoveries(limit=limit)
        return {"items": items, "total": len(items)}

    def audit_log_list(params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit") or 50)
        items = ctx.observability.list_config_audit(limit=limit)
        return {"items": items, "total": len(items)}

    registry.update(
        {
            "errors.report": errors_report,
            "errors.list": errors_list,
            "errors.detail": errors_detail,
            "errors.update_status": errors_update_status,
            "errors.recover": errors_recover,
            "recoveries.list": recoveries_list,
            "system.audit_log": audit_log_list,
        }
    )
