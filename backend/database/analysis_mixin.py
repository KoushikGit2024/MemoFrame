"""Database mixin for image analysis, bursts, places, and date overrides."""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Mapping, Sequence


class AnalysisDbMixin:
    """Methods for analysis metrics, bursts, reverse geocoding, and date overrides."""

    def count_unanalyzed(self) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM images WHERE status = 'done' AND kind = 'photo' "
            "AND state = 'ok' AND quality IS NULL"
        )

    def fetch_unanalyzed(self, after_id: int, limit: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT id, path, exif_ts, ts_source FROM images WHERE status = 'done' AND kind = 'photo' "
            "AND state = 'ok' AND quality IS NULL AND id > ? ORDER BY id LIMIT ?",
            (after_id, limit),
        )

    def save_analysis(self, updates: Sequence[tuple[int, Mapping[str, Any]]]) -> None:
        if not updates:
            return
        with self._tx() as conn:
            for image_id, a in updates:
                conn.execute(
                    "UPDATE images SET quality = ?, sharpness = ?, brightness = ?, dhash = ?, "
                    "content_type = ?, date_flag = ? WHERE id = ?",
                    (
                        a.get("quality"),
                        a.get("sharpness"),
                        a.get("brightness"),
                        a.get("dhash"),
                        a.get("content_type") or "photo",
                        a.get("date_flag"),
                        int(image_id),
                    ),
                )
            self._bump(conn)

    def fetch_burst_rows(self) -> list[sqlite3.Row]:
        return self._query(
            "SELECT i.id, COALESCE(o.exif_ts, i.exif_ts) AS exif_ts, i.phash, i.quality "
            "FROM images i LEFT JOIN date_overrides o ON o.image_id = i.id "
            "WHERE i.status = 'done' AND i.state != 'missing' AND i.kind = 'photo' "
            "AND i.pair_id IS NULL AND i.phash IS NOT NULL "
            "AND COALESCE(o.exif_ts, i.exif_ts) IS NOT NULL "
            "AND (o.exif_ts IS NOT NULL OR i.ts_source IN ('exif_original', 'exif_datetime')) "
            "ORDER BY COALESCE(o.exif_ts, i.exif_ts), i.id"
        )

    def replace_bursts(self, bursts: Sequence[Mapping[str, Any]]) -> int:
        with self._tx() as conn:
            conn.execute("UPDATE images SET burst_id = NULL")
            conn.execute("DELETE FROM bursts")
            for b in bursts:
                cur = conn.execute(
                    "INSERT INTO bursts (best_image_id, image_count) VALUES (?, ?)",
                    (b["best_id"], len(b["image_ids"])),
                )
                conn.executemany(
                    "UPDATE images SET burst_id = ? WHERE id = ?",
                    [(int(cur.lastrowid), int(i)) for i in b["image_ids"]],
                )
        return len(bursts)

    def get_bursts(self) -> list[sqlite3.Row]:
        return self._query("SELECT * FROM bursts ORDER BY id")

    def get_burst_images(self, burst_id: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM images WHERE burst_id = ? ORDER BY exif_ts, id", (burst_id,)
        )

    def fetch_gps_without_place(self, limit: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT id, gps_lat, gps_lon FROM images WHERE status = 'done' "
            "AND gps_lat IS NOT NULL AND place IS NULL ORDER BY id LIMIT ?",
            (limit,),
        )

    def set_places(self, updates: Iterable[tuple[int, str]]) -> None:
        data = [(place, int(i)) for i, place in updates]
        if data:
            with self._tx() as conn:
                conn.executemany("UPDATE images SET place = ? WHERE id = ?", data)
                self._bump(conn)

    def clear_places(self) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE images SET place = NULL")
            self._bump(conn)

    def set_date_override(self, image_id: int, exif_ts: str, note: str | None = None) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO date_overrides (image_id, exif_ts, note) VALUES (?, ?, ?) "
                "ON CONFLICT(image_id) DO UPDATE SET exif_ts = excluded.exif_ts, note = excluded.note",
                (image_id, exif_ts, note),
            )
            self._bump(conn)

    def clear_date_override(self, image_id: int) -> bool:
        with self._tx() as conn:
            removed = (
                conn.execute("DELETE FROM date_overrides WHERE image_id = ?", (image_id,)).rowcount
                > 0
            )
            if removed:
                self._bump(conn)
        return removed

    def suspicious_dates(self, limit: int = 500) -> list[sqlite3.Row]:
        return self._query(
            "SELECT i.id, i.path, i.exif_ts, i.ts_source, i.date_flag, "
            "o.exif_ts AS override_ts FROM images i LEFT JOIN date_overrides o ON o.image_id = i.id "
            "WHERE i.status = 'done' AND i.date_flag IS NOT NULL AND i.date_flag != 'mtime_only' "
            "ORDER BY i.date_flag, i.id LIMIT ?",
            (limit,),
        )

    def low_confidence_faces(self, below: float = 0.8, limit: int = 500) -> list[sqlite3.Row]:
        return self._query(
            "SELECT f.*, i.path FROM faces f JOIN images i ON i.id = f.image_id "
            "WHERE f.confidence < ? ORDER BY f.confidence LIMIT ?",
            (below, limit),
        )
