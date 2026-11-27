"""Unified Error Intelligence, Controlled Self-Healing, RPC Metrics & Config Audit Store.

Persisted in an independent SQLite database (``workspace/observability.db``) so
error capture, correlation, recovery history, and telemetry continue operating
even when the main ``photos.db`` or ML engine fails to initialize.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

APP_VERSION = "1.0.0"

_SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(bearer)\s+[A-Za-z0-9._\-]+"),
)
_USER_PATH_RE = re.compile(r"(?i)([A-Za-z]:\\Users\\|/Users/|/home/)([^\\/\s\"']+)")
_NUM_NORM_RE = re.compile(r"\d{2,}")
_HEX_NORM_RE = re.compile(r"\b[0-9a-fA-F]{8,}\b")


def utc_now_iso() -> str:
    """Return current UTC timestamp in canonical ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def redact_sensitive(text: str | None) -> str:
    """Strip credentials, auth headers, and OS usernames from diagnostic text."""
    if not text:
        return ""
    out = str(text)
    for pat in _SECRET_PATTERNS:
        out = pat.sub(r"\1=[REDACTED]", out)
    out = _USER_PATH_RE.sub(r"\1<user>", out)
    return out[:8000]


def make_fingerprint(origin: str, category: str, module: str, message: str) -> str:
    """Stable deduplication fingerprint ignoring volatile IDs, numbers, and paths."""
    norm = redact_sensitive(message).lower().strip()
    norm = _HEX_NORM_RE.sub("<hex>", norm)
    norm = _NUM_NORM_RE.sub("<n>", norm)
    raw = f"{origin}|{category}|{module}|{norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def classify_recovery(category: str, code: str = "", message: str = "") -> str:
    """Classify whether an error is safely auto-recoverable or needs intervention."""
    msg = (message or "").lower()
    cat = (category or "").lower()
    code_u = (code or "").upper()
    if any(k in msg for k in ("database is locked", "disk i/o", "no such directory", "timeout")):
        return "auto_recoverable"
    if code_u in ("RPC_TIMEOUT", "NETWORK_ERROR", "WORKSPACE_LOCKED", "CACHE_ERROR"):
        return "auto_recoverable"
    if code_u in ("INVALID_FOLDER", "MODELS_NOT_READY", "PERMISSION_DENIED"):
        return "user_action"
    if cat in ("security", "data_integrity", "migration"):
        return "never_auto"
    if cat in ("network", "rpc_timeout", "database_transient"):
        return "auto_recoverable"
    return "dev_action"


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rpc_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id  TEXT    NOT NULL,
    method          TEXT    NOT NULL,
    status          TEXT    NOT NULL CHECK (status IN ('ok', 'error')),
    duration_ms     REAL    NOT NULL,
    error_code      TEXT    DEFAULT '',
    created_at_utc  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rpc_metrics_ts ON rpc_metrics(created_at_utc);
CREATE INDEX IF NOT EXISTS idx_rpc_metrics_method ON rpc_metrics(method);

CREATE TABLE IF NOT EXISTS error_records (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint       TEXT    NOT NULL UNIQUE,
    severity          TEXT    NOT NULL CHECK (severity IN ('critical', 'error', 'warning', 'info')),
    category          TEXT    NOT NULL,
    origin            TEXT    NOT NULL CHECK (origin IN ('frontend', 'backend', 'bridge')),
    module            TEXT    NOT NULL,
    code              TEXT    NOT NULL DEFAULT '',
    message           TEXT    NOT NULL,
    stack_trace       TEXT    NOT NULL DEFAULT '',
    correlation_id    TEXT    NOT NULL DEFAULT '',
    status            TEXT    NOT NULL DEFAULT 'detected'
                      CHECK (status IN ('detected', 'investigating', 'recovered', 'resolved')),
    recovery_class    TEXT    NOT NULL DEFAULT 'dev_action'
                      CHECK (recovery_class IN ('auto_recoverable', 'user_action', 'dev_action', 'never_auto')),
    occurrence_count  INTEGER NOT NULL DEFAULT 1,
    first_seen_utc    TEXT    NOT NULL,
    last_seen_utc     TEXT    NOT NULL,
    notes             TEXT    NOT NULL DEFAULT '',
    context_json      TEXT    NOT NULL DEFAULT '{}',
    app_version       TEXT    NOT NULL DEFAULT '1.0.0'
);
CREATE INDEX IF NOT EXISTS idx_error_records_last ON error_records(last_seen_utc);
CREATE INDEX IF NOT EXISTS idx_error_records_corr ON error_records(correlation_id);
CREATE INDEX IF NOT EXISTS idx_error_records_status ON error_records(status);

CREATE TABLE IF NOT EXISTS error_occurrences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    error_id        INTEGER NOT NULL REFERENCES error_records(id) ON DELETE CASCADE,
    correlation_id  TEXT    NOT NULL DEFAULT '',
    occurred_at_utc TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    context_json    TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_error_occ_err ON error_occurrences(error_id, occurred_at_utc);
CREATE INDEX IF NOT EXISTS idx_error_occ_ts ON error_occurrences(occurred_at_utc);

CREATE TABLE IF NOT EXISTS recovery_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    error_id        INTEGER NOT NULL REFERENCES error_records(id) ON DELETE CASCADE,
    strategy        TEXT    NOT NULL,
    trigger_source  TEXT    NOT NULL CHECK (trigger_source IN ('automatic', 'manual')),
    attempt_no      INTEGER NOT NULL DEFAULT 1,
    started_at_utc  TEXT    NOT NULL,
    duration_ms     REAL    NOT NULL DEFAULT 0,
    outcome         TEXT    NOT NULL CHECK (outcome IN ('succeeded', 'failed', 'skipped')),
    final_state     TEXT    NOT NULL DEFAULT '',
    detail          TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_recovery_err ON recovery_attempts(error_id, started_at_utc);

CREATE TABLE IF NOT EXISTS config_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT    NOT NULL,
    old_value       TEXT    NOT NULL DEFAULT '',
    new_value       TEXT    NOT NULL DEFAULT '',
    changed_at_utc  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_config_audit_ts ON config_audit_log(changed_at_utc);
"""


class ObservabilityStore:
    """Thread-safe local telemetry, error intelligence, and self-healing store."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.db_path = self.workspace / "observability.db"
        self.started_at_utc = utc_now_iso()
        self._started_mono = time.monotonic()
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._open()

    def _open(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._open()
        assert self._conn is not None
        return self._conn

    @property
    def uptime_seconds(self) -> float:
        return round(time.monotonic() - self._started_mono, 1)

    def _cutoff_iso(self, range_key: str | None) -> str | None:
        days_map = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}
        if not range_key or range_key == "all":
            return None
        days = days_map.get(range_key)
        if not days:
            return None
        dt = datetime.now(timezone.utc) - timedelta(days=days)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # ------------------------------------------------------------------
    # RPC Metrics
    # ------------------------------------------------------------------
    def record_rpc_metric(
        self,
        correlation_id: str,
        method: str,
        status: str,
        duration_ms: float,
        error_code: str = "",
    ) -> None:
        with self._lock:
            try:
                conn = self._ensure_conn()
                conn.execute(
                    "INSERT INTO rpc_metrics (correlation_id, method, status, duration_ms, error_code, created_at_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(correlation_id or ""),
                        str(method or ""),
                        "ok" if status == "ok" else "error",
                        round(float(duration_ms), 2),
                        str(error_code or ""),
                        utc_now_iso(),
                    ),
                )
                conn.commit()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Error Intelligence
    # ------------------------------------------------------------------
    def record_error(
        self,
        *,
        origin: str,
        category: str,
        module: str,
        message: str,
        severity: str = "error",
        code: str = "",
        stack_trace: str = "",
        correlation_id: str = "",
        context: dict[str, Any] | None = None,
        recovery_class: str | None = None,
    ) -> dict[str, Any]:
        sev = severity if severity in ("critical", "error", "warning", "info") else "error"
        orig = origin if origin in ("frontend", "backend", "bridge") else "backend"
        clean_msg = redact_sensitive(message) or "Unknown error"
        clean_stack = redact_sensitive(stack_trace)
        fp = make_fingerprint(orig, category, module, clean_msg)
        rclass = recovery_class or classify_recovery(category, code, clean_msg)
        now = utc_now_iso()
        ctx_str = redact_sensitive(json.dumps(context or {}, default=str))

        with self._lock:
            conn = self._ensure_conn()
            existing = conn.execute(
                "SELECT id, occurrence_count, status FROM error_records WHERE fingerprint = ?",
                (fp,),
            ).fetchone()
            if existing:
                err_id = int(existing["id"])
                new_status = existing["status"]
                if new_status in ("resolved", "recovered"):
                    new_status = "detected"
                conn.execute(
                    "UPDATE error_records SET occurrence_count = occurrence_count + 1, "
                    "last_seen_utc = ?, correlation_id = CASE WHEN ? != '' THEN ? ELSE correlation_id END, "
                    "stack_trace = CASE WHEN ? != '' THEN ? ELSE stack_trace END, "
                    "status = ?, severity = ? WHERE id = ?",
                    (now, correlation_id, correlation_id, clean_stack, clean_stack, new_status, sev, err_id),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO error_records "
                    "(fingerprint, severity, category, origin, module, code, message, stack_trace, "
                    "correlation_id, status, recovery_class, occurrence_count, first_seen_utc, last_seen_utc, "
                    "context_json, app_version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'detected', ?, 1, ?, ?, ?, ?)",
                    (
                        fp, sev, str(category or "runtime"), orig, str(module or "unknown"),
                        str(code or ""), clean_msg, clean_stack, str(correlation_id or ""),
                        rclass, now, now, ctx_str, APP_VERSION,
                    ),
                )
                err_id = int(cur.lastrowid or 0)

            conn.execute(
                "INSERT INTO error_occurrences (error_id, correlation_id, occurred_at_utc, message, context_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (err_id, str(correlation_id or ""), now, clean_msg, ctx_str),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM error_records WHERE id = ?", (err_id,)).fetchone()
            return dict(row) if row else {"id": err_id, "fingerprint": fp}

    def list_errors(
        self,
        *,
        severity: str = "",
        origin: str = "",
        status: str = "",
        query: str = "",
        range_key: str = "all",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: list[Any] = []
        cutoff = self._cutoff_iso(range_key)
        if cutoff:
            clauses.append("last_seen_utc >= ?")
            params.append(cutoff)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if origin:
            clauses.append("origin = ?")
            params.append(origin)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if query:
            q = f"%{query.strip().lower()}%"
            clauses.append("(LOWER(message) LIKE ? OR LOWER(module) LIKE ? OR LOWER(category) LIKE ? OR LOWER(code) LIKE ?)")
            params.extend([q, q, q, q])
        params.append(max(1, min(500, int(limit))))

        with self._lock:
            conn = self._ensure_conn()
            rows = conn.execute(
                f"SELECT * FROM error_records WHERE {' AND '.join(clauses)} "
                "ORDER BY last_seen_utc DESC, id DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def get_error_detail(self, error_id: int) -> dict[str, Any] | None:
        with self._lock:
            conn = self._ensure_conn()
            row = conn.execute("SELECT * FROM error_records WHERE id = ?", (error_id,)).fetchone()
            if not row:
                return None
            rec = dict(row)
            occurrences = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM error_occurrences WHERE error_id = ? ORDER BY occurred_at_utc DESC LIMIT 50",
                    (error_id,),
                ).fetchall()
            ]
            recoveries = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM recovery_attempts WHERE error_id = ? ORDER BY started_at_utc DESC LIMIT 30",
                    (error_id,),
                ).fetchall()
            ]
            related: list[dict[str, Any]] = []
            corr = rec.get("correlation_id") or ""
            if corr:
                related = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT id, origin, module, severity, message, status, last_seen_utc "
                        "FROM error_records WHERE correlation_id = ? AND id != ? ORDER BY first_seen_utc ASC",
                        (corr, error_id),
                    ).fetchall()
                ]
            return {
                "error": rec,
                "occurrences": occurrences,
                "recoveries": recoveries,
                "related": related,
            }

    def update_error_status(self, error_id: int, status: str, notes: str | None = None) -> dict[str, Any] | None:
        if status not in ("detected", "investigating", "recovered", "resolved"):
            raise ValueError(f"Invalid error status: {status}")
        with self._lock:
            conn = self._ensure_conn()
            if notes is not None:
                conn.execute(
                    "UPDATE error_records SET status = ?, notes = ? WHERE id = ?",
                    (status, str(notes)[:4000], error_id),
                )
            else:
                conn.execute("UPDATE error_records SET status = ? WHERE id = ?", (status, error_id))
            conn.commit()
            row = conn.execute("SELECT * FROM error_records WHERE id = ?", (error_id,)).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # Controlled Self-Healing & Recovery History
    # ------------------------------------------------------------------
    def record_recovery_attempt(
        self,
        *,
        error_id: int,
        strategy: str,
        trigger_source: str,
        outcome: str,
        duration_ms: float,
        final_state: str,
        detail: str = "",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._lock:
            conn = self._ensure_conn()
            prev = conn.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) FROM recovery_attempts WHERE error_id = ?",
                (error_id,),
            ).fetchone()[0]
            attempt_no = int(prev) + 1
            cur = conn.execute(
                "INSERT INTO recovery_attempts "
                "(error_id, strategy, trigger_source, attempt_no, started_at_utc, duration_ms, outcome, final_state, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    error_id,
                    strategy,
                    "automatic" if trigger_source == "automatic" else "manual",
                    attempt_no,
                    now,
                    round(float(duration_ms), 2),
                    outcome if outcome in ("succeeded", "failed", "skipped") else "failed",
                    final_state,
                    redact_sensitive(detail),
                ),
            )
            if outcome == "succeeded":
                conn.execute(
                    "UPDATE error_records SET status = 'recovered' WHERE id = ? AND status != 'resolved'",
                    (error_id,),
                )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM recovery_attempts WHERE id = ?", (int(cur.lastrowid or 0),)
            ).fetchone()
            return dict(row) if row else {}

    def execute_recovery(
        self,
        error_id: int,
        strategy: str,
        trigger_source: str,
        action_fn: Callable[[], str],
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            detail = action_fn()
            dur = (time.perf_counter() - t0) * 1000.0
            return self.record_recovery_attempt(
                error_id=error_id,
                strategy=strategy,
                trigger_source=trigger_source,
                outcome="succeeded",
                duration_ms=dur,
                final_state="healthy",
                detail=detail,
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000.0
            return self.record_recovery_attempt(
                error_id=error_id,
                strategy=strategy,
                trigger_source=trigger_source,
                outcome="failed",
                duration_ms=dur,
                final_state="degraded",
                detail=f"{exc.__class__.__name__}: {exc}",
            )

    def list_recoveries(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._ensure_conn()
            rows = conn.execute(
                "SELECT r.*, e.module, e.category, e.message AS error_message "
                "FROM recovery_attempts r JOIN error_records e ON e.id = r.error_id "
                "ORDER BY r.started_at_utc DESC LIMIT ?",
                (max(1, min(300, int(limit))),),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Config Audit Log
    # ------------------------------------------------------------------
    def record_config_change(self, key: str, old_value: Any, new_value: Any) -> None:
        with self._lock:
            try:
                conn = self._ensure_conn()
                conn.execute(
                    "INSERT INTO config_audit_log (key, old_value, new_value, changed_at_utc) VALUES (?, ?, ?, ?)",
                    (
                        str(key),
                        redact_sensitive(json.dumps(old_value, default=str)),
                        redact_sensitive(json.dumps(new_value, default=str)),
                        utc_now_iso(),
                    ),
                )
                conn.commit()
            except Exception:
                pass

    def list_config_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._ensure_conn()
            rows = conn.execute(
                "SELECT * FROM config_audit_log ORDER BY changed_at_utc DESC LIMIT ?",
                (max(1, min(200, int(limit))),),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Analytics Aggregations (100% Real Recorded Data)
    # ------------------------------------------------------------------
    def get_rpc_summary(self, range_key: str = "all") -> dict[str, Any]:
        cutoff = self._cutoff_iso(range_key)
        where = "WHERE created_at_utc >= ?" if cutoff else ""
        params = (cutoff,) if cutoff else ()
        with self._lock:
            conn = self._ensure_conn()
            row = conn.execute(
                f"SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_count, "
                "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS err_count, "
                "AVG(duration_ms) AS avg_ms, MAX(duration_ms) AS max_ms "
                f"FROM rpc_metrics {where}",
                params,
            ).fetchone()
            total = int(row["total"] or 0)
            ok_c = int(row["ok_count"] or 0)
            err_c = int(row["err_count"] or 0)
            return {
                "total_requests": total,
                "success_count": ok_c,
                "error_count": err_c,
                "success_rate": round((ok_c / total) * 100.0, 1) if total else 100.0,
                "error_rate": round((err_c / total) * 100.0, 1) if total else 0.0,
                "avg_latency_ms": round(float(row["avg_ms"] or 0.0), 1),
                "max_latency_ms": round(float(row["max_ms"] or 0.0), 1),
            }

    def get_error_analytics(self, range_key: str = "all") -> dict[str, Any]:
        cutoff = self._cutoff_iso(range_key)
        where_occ = "WHERE o.occurred_at_utc >= ?" if cutoff else ""
        where_rec = "WHERE last_seen_utc >= ?" if cutoff else ""
        params = (cutoff,) if cutoff else ()
        with self._lock:
            conn = self._ensure_conn()
            by_sev = [
                {"label": r["severity"], "count": int(r["c"])}
                for r in conn.execute(
                    f"SELECT severity, SUM(occurrence_count) AS c FROM error_records {where_rec} GROUP BY severity",
                    params,
                ).fetchall()
            ]
            by_origin = [
                {"label": r["origin"], "count": int(r["c"])}
                for r in conn.execute(
                    f"SELECT origin, SUM(occurrence_count) AS c FROM error_records {where_rec} GROUP BY origin",
                    params,
                ).fetchall()
            ]
            over_time = [
                {"date": r["day"], "count": int(r["c"])}
                for r in conn.execute(
                    f"SELECT substr(o.occurred_at_utc, 1, 10) AS day, COUNT(*) AS c "
                    f"FROM error_occurrences o {where_occ} GROUP BY day ORDER BY day ASC LIMIT 90",
                    params,
                ).fetchall()
            ]
            top_errors = [
                dict(r)
                for r in conn.execute(
                    f"SELECT id, fingerprint, severity, category, origin, module, message, occurrence_count, status, recovery_class, last_seen_utc "
                    f"FROM error_records {where_rec} ORDER BY occurrence_count DESC, last_seen_utc DESC LIMIT 12",
                    params,
                ).fetchall()
            ]
            unresolved = int(
                conn.execute(
                    "SELECT COUNT(*) FROM error_records WHERE status IN ('detected', 'investigating')"
                ).fetchone()[0]
            )
            rec_row = conn.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN outcome = 'succeeded' THEN 1 ELSE 0 END) AS ok_c "
                "FROM recovery_attempts"
            ).fetchone()
            rec_total = int(rec_row["total"] or 0)
            rec_ok = int(rec_row["ok_c"] or 0)
            return {
                "unresolved_count": unresolved,
                "by_severity": by_sev,
                "by_origin": by_origin,
                "over_time": over_time,
                "top_errors": top_errors,
                "recovery_attempts": rec_total,
                "recovery_succeeded": rec_ok,
                "recovery_rate": round((rec_ok / rec_total) * 100.0, 1) if rec_total else 0.0,
            }

    def get_performance_analytics(self, range_key: str = "all") -> dict[str, Any]:
        cutoff = self._cutoff_iso(range_key)
        where = "WHERE created_at_utc >= ?" if cutoff else ""
        params = (cutoff,) if cutoff else ()
        with self._lock:
            conn = self._ensure_conn()
            by_method = [
                {
                    "method": r["method"],
                    "count": int(r["c"]),
                    "avg_ms": round(float(r["avg_ms"] or 0.0), 1),
                    "max_ms": round(float(r["max_ms"] or 0.0), 1),
                    "errors": int(r["err_c"] or 0),
                }
                for r in conn.execute(
                    f"SELECT method, COUNT(*) AS c, AVG(duration_ms) AS avg_ms, MAX(duration_ms) AS max_ms, "
                    f"SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS err_c "
                    f"FROM rpc_metrics {where} GROUP BY method ORDER BY avg_ms DESC LIMIT 20",
                    params,
                ).fetchall()
            ]
            # Latency histogram buckets (ms)
            buckets = [
                ("< 10ms", 0, 10),
                ("10–50ms", 10, 50),
                ("50–200ms", 50, 200),
                ("200–1000ms", 200, 1000),
                ("> 1000ms", 1000, 10**9),
            ]
            histogram = []
            for label, lo, hi in buckets:
                c = int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM rpc_metrics {where + (' AND ' if where else 'WHERE ')}"
                        "duration_ms >= ? AND duration_ms < ?",
                        (*params, lo, hi),
                    ).fetchone()[0]
                )
                histogram.append({"bucket": label, "count": c})

            slow_ops = [
                dict(r)
                for r in conn.execute(
                    f"SELECT correlation_id, method, status, duration_ms, error_code, created_at_utc "
                    f"FROM rpc_metrics {where} ORDER BY duration_ms DESC LIMIT 15",
                    params,
                ).fetchall()
            ]
            rpc_by_hour = [
                {"hour": int(r["hr"]), "count": int(r["c"])}
                for r in conn.execute(
                    f"SELECT CAST(substr(created_at_utc, 12, 2) AS INTEGER) AS hr, COUNT(*) AS c "
                    f"FROM rpc_metrics {where} GROUP BY hr ORDER BY hr ASC",
                    params,
                ).fetchall()
            ]
            return {
                "by_method": by_method,
                "latency_histogram": histogram,
                "slow_operations": slow_ops,
                "rpc_by_hour": rpc_by_hour,
            }
