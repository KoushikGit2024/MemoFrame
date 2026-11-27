"""Database mixin for health checks, vacuum, restore, pruning, and reset operations."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from memoframe_engine.db.search_mixin import _EFF

log = logging.getLogger("photo_organizer.database")


def _date_words(ts: str | None) -> str:
    _MONTHS = (
        "January February March April May June July August September October November December"
    ).split()
    try:
        year, month = int(ts[:4]), int(ts[5:7])  # type: ignore[index]
        return f"{year} {_MONTHS[month - 1]} {_MONTHS[month - 1][:3]}"
    except (TypeError, ValueError, IndexError):
        return ""


class MaintenanceDbMixin:
    """Methods for database health, moves, FTS index, reset, and live pairs."""

    def integrity_check(self) -> list[str]:
        """Problems reported by SQLite (empty list = healthy)."""
        return [r[0] for r in self._query("PRAGMA integrity_check") if r[0] != "ok"]

    def repair(self) -> dict[str, int]:
        """Fix inconsistencies left by crashes. Changes metadata only."""
        with self._tx() as conn:
            count_sql = "(SELECT COUNT(*) FROM faces WHERE faces.image_id = images.id)"
            fixed = conn.execute(
                f"UPDATE images SET face_count = {count_sql} "
                f"WHERE status = 'done' AND face_count != {count_sql}"
            ).rowcount
            requeued = conn.execute(
                "UPDATE images SET status = 'pending', error = NULL "
                "WHERE status = 'done' AND kind = 'photo' AND (sha256 IS NULL OR width IS NULL)"
            ).rowcount
            orphans = conn.execute(
                "DELETE FROM faces WHERE image_id NOT IN (SELECT id FROM images)"
            ).rowcount
            conn.execute(
                "UPDATE images SET group_id = NULL WHERE group_id IS NOT NULL "
                "AND group_id NOT IN (SELECT id FROM groups)"
            )
            empty = conn.execute(
                "DELETE FROM groups WHERE id NOT IN "
                "(SELECT DISTINCT group_id FROM images WHERE group_id IS NOT NULL)"
            ).rowcount
            conn.execute(
                "UPDATE groups SET image_count = "
                "(SELECT COUNT(*) FROM images WHERE images.group_id = groups.id)"
            )
            if fixed or requeued or orphans:
                self._bump(conn)
        return {
            "face_counts_fixed": fixed,
            "requeued": requeued,
            "orphan_faces_removed": orphans,
            "empty_groups_removed": empty,
        }

    def backup(self, dest: Path) -> Path:
        """Consistent copy of the database (safe while open)."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(dest))
            try:
                self._db.backup(target)
            finally:
                target.close()
        return dest

    def analyze(self) -> None:
        with self._lock:
            self._db.execute("ANALYZE")
            self._db.execute("PRAGMA optimize")

    def vacuum(self) -> None:
        """Reclaim space (needs free disk equal to the database size)."""
        with self._lock:
            self._db.execute("VACUUM")

    def checkpoint(self) -> None:
        with self._lock:
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def restore_marks(self) -> int:
        """Re-apply archived marks to photos with the same content."""
        rows = self._query(
            "SELECT a.sha256, a.kind, a.note, a.path AS old_path, i.id AS image_id, "
            "i.path AS new_path FROM marks_archive a JOIN images i ON i.sha256 = a.sha256 "
            "WHERE i.status = 'done' AND i.state != 'missing' "
            "AND NOT EXISTS (SELECT 1 FROM marks m WHERE m.image_id = i.id AND m.kind = a.kind) "
            "AND (i.path = a.path OR NOT EXISTS "
            "(SELECT 1 FROM images o WHERE o.path = a.path AND o.state != 'missing'))"
        )
        groups: dict[tuple, list[sqlite3.Row]] = {}
        for r in rows:
            groups.setdefault((r["sha256"], r["kind"], r["old_path"]), []).append(r)
        chosen = []
        for items in groups.values():
            exact = [r for r in items if r["new_path"] == r["old_path"]]
            pick = exact or (items if len(items) == 1 else [])
            chosen.extend(pick[:1])
        if not chosen:
            return 0
        restored = 0
        with self._tx() as conn:
            for r in chosen:
                restored += conn.execute(
                    "INSERT OR IGNORE INTO marks (image_id, kind, note) VALUES (?, ?, ?)",
                    (r["image_id"], r["kind"], r["note"]),
                ).rowcount
        return restored

    def find_moves(self) -> list[sqlite3.Row]:
        """Missing photos whose content now exists at exactly one other path."""
        return self._query(
            "SELECT o.id AS old_id, o.path AS old_path, n.id AS new_id, n.path AS new_path "
            "FROM images o JOIN images n ON n.sha256 = o.sha256 AND n.id != o.id "
            "WHERE o.state = 'missing' AND o.sha256 IS NOT NULL "
            "AND n.state = 'ok' AND n.status = 'done' "
            "AND (SELECT COUNT(*) FROM images x WHERE x.sha256 = o.sha256 "
            "     AND x.state = 'ok' AND x.id != o.id) = 1 "
            "AND (SELECT COUNT(*) FROM images y WHERE y.sha256 = o.sha256 "
            "     AND y.state = 'missing') = 1"
        )

    def ensure_fts(self) -> bool:
        """Create the FTS5 table if this SQLite supports it. Cached."""
        if self._fts is None:
            try:
                with self._lock:
                    self._db.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS fts_images USING fts5("
                        "name, folder, place, event, kind, date, "
                        "tokenize = 'unicode61 remove_diacritics 2')"
                    )
                self._fts = True
            except sqlite3.Error:
                self._fts = False
        return self._fts

    def rebuild_fts(self) -> int:
        """Rebuild the text index from scratch. Returns rows indexed."""
        if not self.ensure_fts():
            return 0
        rows = self._query(
            f"SELECT i.id, i.path, i.place, i.content_type, i.kind, i.format, "
            f"{_EFF} AS ts, g.name AS event, "
            "(SELECT group_concat(label, ' ') FROM tags t WHERE t.image_id = i.id) AS tags, "
            "(SELECT group_concat(p.name, ' ') FROM faces f "
            " JOIN persons p ON p.id = f.person_id WHERE f.image_id = i.id) AS people "
            "FROM images i "
            "LEFT JOIN date_overrides o ON o.image_id = i.id "
            "LEFT JOIN groups g ON g.id = i.group_id "
            "WHERE i.status = 'done' AND i.state != 'missing'"
        )
        data = [
            (
                r["id"],
                os.path.basename(r["path"]),
                os.path.dirname(r["path"]),
                r["place"] or "",
                r["event"] or "",
                " ".join(
                    x
                    for x in (r["content_type"], r["kind"], r["format"], r["tags"], r["people"])
                    if x
                ),
                _date_words(r["ts"]),
            )
            for r in rows
        ]
        with self._tx() as conn:
            conn.execute("DELETE FROM fts_images")
            conn.executemany(
                "INSERT INTO fts_images (rowid, name, folder, place, event, kind, date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                data,
            )
        return len(data)

    def reset(
        self,
        *,
        clear_sources: bool = False,
        clear_saved_searches: bool = False,
        clear_archive: bool = False,
    ) -> None:
        """Delete all metadata rows."""
        with self._tx() as conn:
            conn.execute("DELETE FROM faces")
            conn.execute("DELETE FROM persons")
            conn.execute("DELETE FROM duplicates")
            conn.execute("DELETE FROM bursts")
            conn.execute("DELETE FROM marks")
            conn.execute("DELETE FROM tags")
            conn.execute("DELETE FROM date_overrides")
            conn.execute("DELETE FROM embeddings")
            conn.execute("DELETE FROM images")
            conn.execute("DELETE FROM groups")
            conn.execute("DELETE FROM meta")
            if clear_archive:
                conn.execute("DELETE FROM marks_archive")
            if clear_sources:
                conn.execute("DELETE FROM sources")
            if clear_saved_searches:
                conn.execute("DELETE FROM saved_searches")
            try:
                conn.execute("DELETE FROM fts_images")
            except Exception:
                pass
        with self._lock:
            try:
                self._db.execute("INSERT INTO fts_images(fts_images) VALUES('rebuild')")
            except Exception:
                pass
            self._db.execute("VACUUM")
        log.info("Database reset.")

    def clear_sources(self) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM sources")

    def clear_saved_searches(self) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM saved_searches")

    def list_image_paths(self) -> list[sqlite3.Row]:
        return self._query("SELECT id, path FROM images ORDER BY id")

    def delete_images(self, image_ids: Iterable[int], chunk_size: int = 500) -> int:
        ids = [int(i) for i in image_ids]
        removed = 0
        with self._tx() as conn:
            for start in range(0, len(ids), chunk_size):
                part = ids[start : start + chunk_size]
                marks = ",".join("?" for _ in part)
                removed += conn.execute(f"DELETE FROM images WHERE id IN ({marks})", part).rowcount
            if removed:
                self._bump(conn)
        return removed

    def list_pair_candidates(self) -> list[sqlite3.Row]:
        return self._query(
            "SELECT id, path, kind, duration_s, pair_id FROM images "
            "WHERE status = 'done' AND state != 'missing' "
            "ORDER BY path"
        )

    def set_pairs(self, updates: Iterable[tuple[int, int | None]]) -> int:
        data = [(p, i) for i, p in updates]
        if not data:
            return 0
        with self._tx() as conn:
            conn.executemany("UPDATE images SET pair_id = ? WHERE id = ?", data)
            self._bump(conn)
        return len(data)

    def get_paired_video(self, photo_id: int) -> sqlite3.Row | None:
        rows = self._query(
            "SELECT * FROM images WHERE pair_id = ? AND kind = 'video' LIMIT 1",
            (photo_id,),
        )
        return rows[0] if rows else None
