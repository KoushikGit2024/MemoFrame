"""RPC handlers for the dedicated Analytics Center (100% real SQLite + telemetry data)."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any


def _cutoff_date_prefix(range_key: str) -> str | None:
    days_map = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}
    days = days_map.get(range_key)
    if not days:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def register_analytics_handlers(registry: dict[str, Any], ctx: Any) -> None:
    """Register analytics.overview, analytics.activity, analytics.errors, analytics.performance, analytics.export."""

    def analytics_overview(params: dict[str, Any]) -> dict[str, Any]:
        range_key = str(params.get("range") or "all")
        rpc_summary = ctx.observability.get_rpc_summary(range_key)
        err_summary = ctx.observability.get_error_analytics(range_key)

        library: dict[str, Any] = {
            "total_images": 0,
            "videos": 0,
            "total_faces": 0,
            "named_faces": 0,
            "unassigned_faces": 0,
            "persons": 0,
            "groups": 0,
            "duplicate_clusters": 0,
            "bursts": 0,
            "failed_images": 0,
            "avg_quality": 0.0,
            "total_size_mb": 0.0,
            "formats": [],
        }

        if ctx.engine is not None and hasattr(ctx.engine, "db") and ctx.engine.db is not None:
            with ctx.lock:
                db = ctx.engine.db
                try:
                    stats = dict(ctx.engine.stats() or {})
                    library["total_images"] = int(stats.get("total_images") or 0)
                    library["videos"] = int(stats.get("videos") or 0)
                    library["total_faces"] = int(stats.get("total_faces") or 0)
                    library["groups"] = int(stats.get("groups") or 0)
                    library["duplicate_clusters"] = int(stats.get("duplicate_clusters") or 0)

                    row = db._query_one(
                        "SELECT "
                        "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_c, "
                        "AVG(CASE WHEN quality IS NOT NULL THEN quality END) AS avg_q, "
                        "SUM(COALESCE(size, 0)) AS total_bytes "
                        "FROM images"
                    )
                    if row:
                        library["failed_images"] = int(row["failed_c"] or 0)
                        library["avg_quality"] = round(float(row["avg_q"] or 0.0), 1)
                        library["total_size_mb"] = round(float(row["total_bytes"] or 0) / (1024 * 1024), 1)

                    frow = db._query_one(
                        "SELECT "
                        "SUM(CASE WHEN person_id IS NOT NULL AND COALESCE(ignored, 0) = 0 THEN 1 ELSE 0 END) AS named_c, "
                        "SUM(CASE WHEN person_id IS NULL AND COALESCE(ignored, 0) = 0 THEN 1 ELSE 0 END) AS un_c "
                        "FROM faces"
                    )
                    if frow:
                        library["named_faces"] = int(frow["named_c"] or 0)
                        library["unassigned_faces"] = int(frow["un_c"] or 0)

                    prow = db._query_one("SELECT COUNT(*) AS c FROM persons")
                    if prow:
                        library["persons"] = int(prow["c"] or 0)

                    brow = db._query_one("SELECT COUNT(*) AS c FROM bursts")
                    if brow:
                        library["bursts"] = int(brow["c"] or 0)

                    fmt_rows = db._query_all(
                        "SELECT COALESCE(NULLIF(UPPER(format), ''), 'UNKNOWN') AS fmt, COUNT(*) AS c "
                        "FROM images GROUP BY fmt ORDER BY c DESC LIMIT 8"
                    )
                    library["formats"] = [{"label": r["fmt"], "count": int(r["c"])} for r in fmt_rows]
                except Exception:
                    pass

        return {
            "range": range_key,
            "connected": ctx.engine is not None,
            "uptime_seconds": ctx.observability.uptime_seconds,
            "library": library,
            "rpc": rpc_summary,
            "errors": {
                "unresolved_count": err_summary["unresolved_count"],
                "recovery_attempts": err_summary["recovery_attempts"],
                "recovery_succeeded": err_summary["recovery_succeeded"],
                "recovery_rate": err_summary["recovery_rate"],
                "by_origin": err_summary["by_origin"],
                "by_severity": err_summary["by_severity"],
            },
        }

    def analytics_activity(params: dict[str, Any]) -> dict[str, Any]:
        range_key = str(params.get("range") or "all")
        cutoff = _cutoff_date_prefix(range_key)
        photos_by_month: list[dict[str, Any]] = []
        photos_by_hour: list[dict[str, Any]] = []
        top_people: list[dict[str, Any]] = []
        top_tags: list[dict[str, Any]] = []

        if ctx.engine is not None and hasattr(ctx.engine, "db") and ctx.engine.db is not None:
            with ctx.lock:
                db = ctx.engine.db
                try:
                    eff = "COALESCE(o.override_ts, i.exif_ts)"
                    join_sql = "FROM images i LEFT JOIN date_overrides o ON o.image_id = i.id"
                    where_ts = f"WHERE {eff} IS NOT NULL AND length({eff}) >= 10"
                    q_params: tuple[Any, ...] = ()
                    if cutoff:
                        where_ts += f" AND substr({eff}, 1, 10) >= ?"
                        q_params = (cutoff,)

                    m_rows = db._query_all(
                        f"SELECT substr({eff}, 1, 7) AS ym, COUNT(*) AS c "
                        f"{join_sql} {where_ts} GROUP BY ym ORDER BY ym ASC LIMIT 48",
                        q_params,
                    )
                    photos_by_month = [{"label": r["ym"], "count": int(r["c"])} for r in m_rows]

                    h_rows = db._query_all(
                        f"SELECT CAST(substr({eff}, 12, 2) AS INTEGER) AS hr, COUNT(*) AS c "
                        f"{join_sql} {where_ts} AND length({eff}) >= 13 GROUP BY hr ORDER BY hr ASC",
                        q_params,
                    )
                    photos_by_hour = [
                        {"hour": int(r["hr"]), "count": int(r["c"])}
                        for r in h_rows
                        if r["hr"] is not None and 0 <= int(r["hr"]) <= 23
                    ]

                    p_rows = db._query_all(
                        "SELECT name, image_count FROM persons ORDER BY image_count DESC LIMIT 10"
                    )
                    top_people = [{"label": r["name"], "count": int(r["image_count"] or 0)} for r in p_rows]

                    t_rows = db._query_all(
                        "SELECT label, COUNT(*) AS c FROM tags GROUP BY label ORDER BY c DESC LIMIT 10"
                    )
                    top_tags = [{"label": r["label"], "count": int(r["c"])} for r in t_rows]
                except Exception:
                    pass

        perf = ctx.observability.get_performance_analytics(range_key)
        return {
            "range": range_key,
            "photos_by_month": photos_by_month,
            "photos_by_hour": photos_by_hour,
            "top_people": top_people,
            "top_tags": top_tags,
            "rpc_by_hour": perf["rpc_by_hour"],
        }

    def analytics_errors(params: dict[str, Any]) -> dict[str, Any]:
        range_key = str(params.get("range") or "all")
        return ctx.observability.get_error_analytics(range_key)

    def analytics_performance(params: dict[str, Any]) -> dict[str, Any]:
        range_key = str(params.get("range") or "all")
        return ctx.observability.get_performance_analytics(range_key)

    def analytics_export(params: dict[str, Any]) -> dict[str, Any]:
        fmt = str(params.get("format") or "json").lower()
        range_key = str(params.get("range") or "all")
        payload = {
            "overview": analytics_overview({"range": range_key}),
            "activity": analytics_activity({"range": range_key}),
            "errors": analytics_errors({"range": range_key}),
            "performance": analytics_performance({"range": range_key}),
        }
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["section", "metric", "value"])
            for k, v in payload["overview"]["library"].items():
                if not isinstance(v, list):
                    writer.writerow(["library", k, v])
            for k, v in payload["overview"]["rpc"].items():
                writer.writerow(["rpc", k, v])
            for row in payload["performance"]["by_method"]:
                writer.writerow(["rpc_method", row["method"], f"count={row['count']};avg_ms={row['avg_ms']};errors={row['errors']}"])
            return {"format": "csv", "filename": f"memoframe-analytics-{range_key}.csv", "content": buf.getvalue()}
        return {
            "format": "json",
            "filename": f"memoframe-analytics-{range_key}.json",
            "content": json.dumps(payload, indent=2),
        }

    registry.update(
        {
            "analytics.overview": analytics_overview,
            "analytics.activity": analytics_activity,
            "analytics.errors": analytics_errors,
            "analytics.performance": analytics_performance,
            "analytics.export": analytics_export,
        }
    )
