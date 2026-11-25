"""SQLite access layer for the photo organizer.

One connection is shared behind a lock, and every write goes through
:meth:`DatabaseManager._tx` so a batch is committed atomically. The database
stores metadata only; original photographs are never touched.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from utils.logger import get_logger
from database.migrations import LATEST_VERSION, MigrationError, migrate

log = get_logger("database")

SCHEMA_VERSION = LATEST_VERSION
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

# Per-image columns written by save_results() (face_count is derived).
RESULT_COLUMNS: tuple[str, ...] = (
    "width", "height", "sha256", "phash", "exif_ts", "ts_source",
    "gps_lat", "gps_lon", "features", "thumb_path",
    "kind", "duration_s", "format",
    "quality", "sharpness", "brightness", "dhash", "content_type", "date_flag",
)

FIND_FILTERS = frozenset({
    "text", "min_faces", "max_faces", "taken_from", "taken_until", "group_id",
    "path_contains", "place_contains", "content_type", "kind", "format", "min_quality",
    "burst_id", "in_burst", "duplicate", "mark", "no_mark",
    "include_missing", "include_live_video", "include_hidden", "tag", "person_id",
})
MARK_KINDS = ("keep", "reviewed", "favourite", "hidden")
_EFF = "COALESCE(o.exif_ts, i.exif_ts)"          # date overrides apply
_SORTS = {
    "date": f"{_EFF} IS NULL, {_EFF}, i.id",
    "date_desc": f"{_EFF} IS NULL, {_EFF} DESC, i.id DESC",
    "quality": "i.quality IS NULL, i.quality DESC, i.id",
    "path": "i.path COLLATE NOCASE, i.id",
    "size": "i.size DESC, i.id",
}
_MONTHS = ("January February March April May June July August "
           "September October November December").split()


def fts_query(text: str) -> str:
    """Safe FTS5 query: every word becomes a quoted prefix term, all must match."""
    return " ".join(f'"{t}"*' for t in re.findall(r"[^\W_]+", text))


def _date_words(ts: str | None) -> str:
    try:
        year, month = int(ts[:4]), int(ts[5:7])        # type: ignore[index]
        return f"{year} {_MONTHS[month - 1]} {_MONTHS[month - 1][:3]}"
    except (TypeError, ValueError, IndexError):
        return ""


class DatabaseError(RuntimeError):
    """Raised for unrecoverable database problems."""


@dataclass(frozen=True)
class ScanStats:
    """Outcome of :meth:`DatabaseManager.register_files`."""

    new: int
    changed: int
    unchanged: int

    @property
    def total(self) -> int:
        return self.new + self.changed + self.unchanged


class DatabaseManager:
    """Thin, explicit wrapper around the project's SQLite database.

    Usage::

        with DatabaseManager(settings.db_path) as db:
            db.register_files(...)
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = db_path if isinstance(db_path, str) else Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._fts: bool | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def open(self) -> "DatabaseManager":
        """Connect, apply pragmas, and create the schema if needed."""
        if self._conn is not None:
            return self
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30,
                isolation_level=None,        # we manage transactions explicitly
                check_same_thread=False,     # access is serialised by self._lock
            )
        except sqlite3.Error as exc:
            raise DatabaseError(f"Cannot open database {self.db_path}: {exc}") from exc

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")

        prefix = str(self.db_path) if isinstance(self.db_path, Path) else None
        try:
            migrate(conn, prefix)          # backs up first when upgrading an existing DB
        except MigrationError as exc:
            conn.close()
            raise DatabaseError(str(exc)) from exc
        self._conn = conn
        return self

    def close(self) -> None:
        """Close the connection (safe to call repeatedly)."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "DatabaseManager":
        return self.open()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DatabaseError("Database is not open. Call open() or use a 'with' block.")
        return self._conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """Atomic write transaction (commit on success, rollback on any error)."""
        with self._lock:
            conn = self._db
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    def _query(self, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def _scalar(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self._lock:
            row = self._db.execute(sql, params).fetchone()
        return int(row[0] or 0)

    # ------------------------------------------------------------------
    # Scanning / resume
    # ------------------------------------------------------------------
    def register_files(
        self,
        files: Iterable[tuple[Path | str, int, int]],
        chunk_size: int = 1000,
    ) -> ScanStats:
        """Record discovered files as ``(path, size, mtime_ns)`` tuples.

        * unknown path       -> inserted as ``pending``
        * changed size/mtime -> reset to ``pending`` (old faces/duplicate rows removed)
        * unchanged          -> left alone (resumable); if it was offline/missing it is ``ok`` again
        """
        known = {
            r["path"]: (r["id"], r["size"], r["mtime_ns"], r["state"])
            for r in self._query("SELECT id, path, size, mtime_ns, state FROM images")
        }
        new = changed = unchanged = 0
        iterator = iter(files)
        while True:
            chunk = list(islice(iterator, chunk_size))
            if not chunk:
                break
            with self._tx() as conn:
                for raw_path, size, mtime_ns in chunk:
                    path = str(raw_path)
                    old = known.get(path)
                    if old is None:
                        cur = conn.execute(
                            "INSERT INTO images (path, size, mtime_ns) VALUES (?, ?, ?)",
                            (path, size, mtime_ns),
                        )
                        known[path] = (int(cur.lastrowid), size, mtime_ns, "ok")
                        new += 1
                    elif (old[1], old[2]) != (size, mtime_ns):
                        self._reset_image(conn, old[0], size, mtime_ns)
                        known[path] = (old[0], size, mtime_ns, "ok")
                        changed += 1
                    else:
                        if old[3] != "ok":
                            conn.execute("UPDATE images SET state = 'ok' WHERE id = ?", (old[0],))
                            self._bump(conn)
                        unchanged += 1
        stats = ScanStats(new, changed, unchanged)
        log.info("Registered files: %d new, %d changed, %d unchanged",
                 stats.new, stats.changed, stats.unchanged)
        return stats

    @staticmethod
    def _reset_image(conn: sqlite3.Connection, image_id: int, size: int, mtime_ns: int) -> None:
        conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))
        conn.execute("DELETE FROM duplicates WHERE image_id = ?", (image_id,))
        conn.execute("DELETE FROM tags WHERE image_id = ?", (image_id,))
        conn.execute("DELETE FROM embeddings WHERE image_id = ?", (image_id,))
        conn.execute(
            """UPDATE images SET
                   size = ?, mtime_ns = ?, width = NULL, height = NULL,
                   sha256 = NULL, phash = NULL, exif_ts = NULL, ts_source = NULL,
                   gps_lat = NULL, gps_lon = NULL, features = NULL, thumb_path = NULL,
                   face_count = 0, status = 'pending',
                   tagged_with = NULL,
                   quality = NULL, sharpness = NULL, brightness = NULL, dhash = NULL, content_type = 'photo', place = NULL, burst_id = NULL, date_flag = NULL,
                   kind = 'photo', format = NULL, duration_s = NULL, pair_id = NULL,
                   state = 'ok', error = NULL,
                   group_id = NULL, processed_at = NULL
               WHERE id = ?""",
            (size, mtime_ns, image_id),
        )
        DatabaseManager._bump(conn)

    def fetch_pending(self, limit: int, include_failed: bool = False) -> list[sqlite3.Row]:
        """Next batch of images to process (``id, path, size, mtime_ns``)."""
        statuses = (STATUS_PENDING, STATUS_FAILED) if include_failed else (STATUS_PENDING,)
        marks = ",".join("?" for _ in statuses)
        return self._query(
            f"SELECT id, path, size, mtime_ns FROM images "
            f"WHERE status IN ({marks}) AND state = 'ok' ORDER BY id LIMIT ?",
            (*statuses, limit),
        )

    def count_pending(self, include_failed: bool = False) -> int:
        """Number of images still waiting for processing."""
        if include_failed:
            return self._scalar("SELECT COUNT(*) FROM images WHERE status IN ('pending','failed') AND state = 'ok'")
        return self._scalar("SELECT COUNT(*) FROM images WHERE status = 'pending' AND state = 'ok'")

    def retry_failed(self) -> int:
        """Put every failed image back to ``pending``. Returns how many."""
        with self._tx() as conn:
            return conn.execute(
                "UPDATE images SET status = 'pending', error = NULL WHERE status = 'failed'"
            ).rowcount

    # ------------------------------------------------------------------
    # Saving results
    # ------------------------------------------------------------------
    def save_results(self, results: Sequence[Mapping[str, Any]]) -> None:
        """Store one processed batch atomically and mark the images ``done``.

        Each mapping needs ``image_id`` and may contain any key in
        :data:`RESULT_COLUMNS` plus ``faces``: a list of mappings with
        ``x, y, w, h, confidence`` and optionally ``label`` / ``crop_path``.
        Missing labels become ``Face 001``, ``Face 002`` ... in list order.
        """
        if not results:
            return
        assignments = ", ".join(f"{c} = :{c}" for c in RESULT_COLUMNS)
        update_sql = (
            f"UPDATE images SET {assignments}, face_count = :face_count, "
            "status = 'done', error = NULL, processed_at = datetime('now') "
            "WHERE id = :image_id"
        )
        with self._tx() as conn:
            for res in results:
                image_id = int(res["image_id"])
                faces = list(res.get("faces") or ())
                params: dict[str, Any] = {c: res.get(c) for c in RESULT_COLUMNS}
                params["kind"] = res.get("kind") or "photo"
                params["content_type"] = res.get("content_type") or "photo"
                params.update(face_count=len(faces), image_id=image_id)
                conn.execute(update_sql, params)
                kept = conn.execute(
                    "SELECT x, y, w, h, person_id FROM faces WHERE image_id = ? AND locked = 1",
                    (image_id,)).fetchall()
                conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))
                conn.executemany(
                    "INSERT INTO faces (image_id, label, x, y, w, h, confidence, crop_path, embedding, person_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            image_id,
                            f.get("label") or f"Face {i:03d}",
                            int(f["x"]), int(f["y"]), int(f["w"]), int(f["h"]),
                            float(f["confidence"]),
                            f.get("crop_path"),
                            f.get("embedding"),
                            f.get("person_id"),
                        )
                        for i, f in enumerate(faces, start=1)
                    ],
                )
                if kept:
                    self._restore_locked(conn, image_id, kept)
                if "tags" in res:
                    self._write_tags(conn, image_id, res)
            self._bump(conn)

    def save_failures(self, failures: Sequence[tuple[int, str]]) -> None:
        """Mark ``(image_id, error_message)`` pairs as ``failed`` in one transaction."""
        if not failures:
            return
        with self._tx() as conn:
            conn.executemany(
                "UPDATE images SET status = 'failed', error = ?, "
                "processed_at = datetime('now') WHERE id = ?",
                [(msg[:500], image_id) for image_id, msg in failures],
            )

    # ------------------------------------------------------------------
    # Duplicates
    # ------------------------------------------------------------------
    def fetch_hash_records(self) -> list[sqlite3.Row]:
        """``id, sha256, phash, dhash`` of every successfully processed image."""
        return self._query(
            "SELECT id, sha256, phash, dhash FROM images WHERE status = 'done' AND state != 'missing' AND kind = 'photo' ORDER BY id"
        )

    def replace_duplicates(self, rows: Iterable[tuple[int, int, str]]) -> int:
        """Replace all duplicate data with ``(image_id, cluster_id, kind)`` rows.

        ``kind`` is ``'exact'`` or ``'near'``. Returns the number of rows stored.
        """
        data = list(rows)
        with self._tx() as conn:
            conn.execute("DELETE FROM duplicates")
            conn.executemany(
                "INSERT INTO duplicates (image_id, cluster_id, kind) VALUES (?, ?, ?)", data
            )
        return len(data)

    def get_duplicate_clusters(self) -> dict[int, list[sqlite3.Row]]:
        """``cluster_id -> member images`` (``id, path, size, width, height, kind, quality``)."""
        rows = self._query(
            """SELECT d.cluster_id, d.kind, i.id, i.path, i.size, i.width, i.height, i.quality
                 FROM duplicates d JOIN images i ON i.id = d.image_id
                WHERE i.state != 'missing'
                  AND NOT EXISTS (SELECT 1 FROM marks h
                                   WHERE h.image_id = i.id AND h.kind = 'hidden')
                ORDER BY d.cluster_id, i.id"""
        )
        clusters: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            clusters.setdefault(row["cluster_id"], []).append(row)
        return {k: v for k, v in clusters.items() if len(v) > 1}

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------
    def fetch_grouping_rows(self, include_junk: bool = False) -> list[sqlite3.Row]:
        """Inputs for the grouper. Date overrides apply."""
        junk = "" if include_junk else " AND i.content_type = 'photo'"
        return self._query(
            "SELECT i.id, i.path, COALESCE(o.exif_ts, i.exif_ts) AS exif_ts, "
            "CASE WHEN o.exif_ts IS NOT NULL THEN 'exif_original' ELSE i.ts_source END AS ts_source, "
            "i.gps_lat, i.gps_lon, i.phash, i.features, i.place "
            "FROM images i LEFT JOIN date_overrides o ON o.image_id = i.id "
            "WHERE i.status = 'done' AND i.state != 'missing' AND i.pair_id IS NULL"
            + junk + " ORDER BY i.id")

    def replace_groups(self, groups: Sequence[Mapping[str, Any]]) -> int:
        """Replace all groups.

        Each mapping: ``kind`` ('event'|'visual'), ``image_ids`` (list[int]) and
        optional ``name``, ``start_ts``, ``end_ts``. Returns the group count.
        """
        with self._tx() as conn:
            conn.execute("UPDATE images SET group_id = NULL")
            conn.execute("DELETE FROM groups")
            for g in groups:
                ids = [int(i) for i in g["image_ids"]]
                cur = conn.execute(
                    "INSERT INTO groups (kind, name, start_ts, end_ts, image_count) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (g["kind"], g.get("name"), g.get("start_ts"), g.get("end_ts"), len(ids)),
                )
                gid = int(cur.lastrowid)
                conn.executemany(
                    "UPDATE images SET group_id = ? WHERE id = ?", [(gid, i) for i in ids]
                )
        return len(groups)

    def get_groups(self) -> list[sqlite3.Row]:
        """All groups ordered by start time."""
        return self._query("SELECT * FROM groups ORDER BY start_ts, id")

    def get_group_images(self, group_id: int) -> list[sqlite3.Row]:
        """Images in a group (photos only), in timestamp order."""
        return self._query(
            "SELECT * FROM images WHERE group_id = ? AND kind != 'video' ORDER BY exif_ts, id", (group_id,)
        )

    # ------------------------------------------------------------------
    # Search / lookup
    # ------------------------------------------------------------------
    def get_image(self, image_id: int) -> sqlite3.Row | None:
        """One image row, or ``None``."""
        rows = self._query("SELECT * FROM images WHERE id = ?", (image_id,))
        return rows[0] if rows else None

    def get_faces(self, image_id: int) -> list[sqlite3.Row]:
        """Face boxes for one image, with the owning person's name (labels are local to the image)."""
        return self._query(
            "SELECT f.*, p.name AS person_name FROM faces f "
            "LEFT JOIN persons p ON p.id = f.person_id "
            "WHERE f.image_id = ? ORDER BY f.id", (image_id,))

    def faces_for_images(self, image_ids: Iterable[int],
                         chunk_size: int = 500) -> dict[int, list[sqlite3.Row]]:
        """Faces of many images in a few queries (no embeddings). Fixes the N+1 in the GUI."""
        ids = [int(i) for i in image_ids]
        out: dict[int, list[sqlite3.Row]] = {i: [] for i in ids}
        for start in range(0, len(ids), chunk_size):
            part = ids[start:start + chunk_size]
            marks = ",".join("?" for _ in part)
            rows = self._query(
                "SELECT f.id, f.image_id, f.person_id, f.label, f.x, f.y, f.w, f.h, "
                "f.confidence, f.crop_path, f.locked, p.name AS person_name "
                "FROM faces f LEFT JOIN persons p ON p.id = f.person_id "
                f"WHERE f.image_id IN ({marks}) ORDER BY f.image_id, f.id", part)
            for r in rows:
                out[int(r["image_id"])].append(r)
        return out

    def search_images(
        self,
        *,
        min_faces: int | None = None,
        max_faces: int | None = None,
        taken_from: str | None = None,
        taken_until: str | None = None,
        group_id: int | None = None,
        path_contains: str | None = None,
        include_missing: bool = False,
        kind: str | None = None,
        include_live_video: bool = False,
        content_type: str | None = None,
        min_quality: float | None = None,
        burst_id: int | None = None,
        person_id: int | None = None,
        place_contains: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        """Search processed images. All filters are optional and combined with AND.

        ``taken_from`` / ``taken_until`` are ISO strings (``'2024-06-01'`` works,
        because ISO timestamps sort as text).
        """
        clauses = ["status = 'done'"]
        if not include_missing:
            clauses.append("state != 'missing'")
        if not include_live_video:
            clauses.append("pair_id IS NULL")
        params: list[Any] = []
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        elif not include_live_video:
            clauses.append("kind != 'video'")
        if content_type is not None:
            clauses.append("content_type = ?")
            params.append(content_type)
        if min_quality is not None:
            clauses.append("quality >= ?")
            params.append(min_quality)
        if burst_id is not None:
            clauses.append("burst_id = ?")
            params.append(burst_id)
        if person_id is not None:
            clauses.append("id IN (SELECT image_id FROM faces WHERE person_id = ?)")
            params.append(person_id)
        if place_contains:
            esc = place_contains.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("place LIKE ? ESCAPE '\\'")
            params.append(f"%{esc}%")
        if min_faces is not None:
            clauses.append("face_count >= ?")
            params.append(min_faces)
        if max_faces is not None:
            clauses.append("face_count <= ?")
            params.append(max_faces)
        if taken_from is not None:
            clauses.append("exif_ts >= ?")
            params.append(taken_from)
        if taken_until is not None:
            clauses.append("exif_ts <= ?")
            params.append(taken_until + "~" if len(taken_until) <= 10 else taken_until)
        if group_id is not None:
            clauses.append("group_id = ?")
            params.append(group_id)
        if path_contains:
            escaped = (
                path_contains.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            clauses.append("path LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")
        sql = (
            "SELECT * FROM images WHERE " + " AND ".join(clauses)
            + " ORDER BY exif_ts, id LIMIT ? OFFSET ?"
        )
        return self._query(sql, (*params, limit, offset))

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def report_stats(self) -> dict[str, int]:
        """Counters for the report.

        ``duplicate_images`` counts redundant copies: for a cluster of 3 files
        it adds 2 (one original is kept).
        """
        dup_rows = self._scalar("SELECT COUNT(*) FROM duplicates")
        dup_clusters = self._scalar("SELECT COUNT(DISTINCT cluster_id) FROM duplicates")
        return {
            "total_images": self._scalar("SELECT COUNT(*) FROM images"),
            "processed": self._scalar("SELECT COUNT(*) FROM images WHERE status = 'done'"),
            "failed": self._scalar("SELECT COUNT(*) FROM images WHERE status = 'failed'"),
            "pending": self._scalar("SELECT COUNT(*) FROM images WHERE status = 'pending'"),
            "total_faces": self._scalar("SELECT COUNT(*) FROM faces"),
            "images_with_faces": self._scalar(
                "SELECT COUNT(*) FROM images WHERE status = 'done' AND face_count >= 1"
            ),
            "multi_face_images": self._scalar(
                "SELECT COUNT(*) FROM images WHERE status = 'done' AND face_count >= 2"
            ),
            "duplicate_clusters": dup_clusters,
            "duplicate_images": dup_rows - dup_clusters,
            "exact_duplicate_rows": self._scalar(
                "SELECT COUNT(*) FROM duplicates WHERE kind = 'exact'"
            ),
            "groups": self._scalar("SELECT COUNT(*) FROM groups"),
            "videos": self._scalar("SELECT COUNT(*) FROM images WHERE status = 'done' AND kind = 'video'"),
            "live_pairs": self._scalar("SELECT COUNT(*) FROM images WHERE pair_id IS NOT NULL"),
            "bursts": self._scalar("SELECT COUNT(*) FROM bursts"),
            "tagged": self._scalar("SELECT COUNT(*) FROM images WHERE tagged_with IS NOT NULL"),
            "screenshots": self._scalar("SELECT COUNT(*) FROM images WHERE content_type = 'screenshot'"),
            "documents": self._scalar("SELECT COUNT(*) FROM images WHERE content_type = 'document'"),
            "date_issues": self._scalar("SELECT COUNT(*) FROM images WHERE date_flag IN ('future','implausible','none')"),
            "offline_images": self._scalar("SELECT COUNT(*) FROM images WHERE state = 'offline'"),
            "missing_images": self._scalar("SELECT COUNT(*) FROM images WHERE state = 'missing'"),
        }

    def failed_images(self) -> list[sqlite3.Row]:
        """``path, error`` for every failed image."""
        return self._query("SELECT path, error FROM images WHERE status = 'failed' ORDER BY path")

    # ------------------------------------------------------------------
    # Persons & Face Embeddings
    # ------------------------------------------------------------------
    def fetch_faces_with_embeddings(self) -> list[sqlite3.Row]:
        """Faces with an embedding on photos that still exist (not missing / Live video)."""
        return self._query(
            "SELECT f.id, f.image_id, f.w, f.h, f.confidence, f.embedding, f.person_id, f.locked "
            "FROM faces f JOIN images i ON i.id = f.image_id "
            "WHERE f.embedding IS NOT NULL AND i.state != 'missing' AND i.pair_id IS NULL "
            "ORDER BY f.id")

    @staticmethod
    def _refresh_person_stats(conn: sqlite3.Connection) -> None:
        """Recompute cover face and photo count; drop people that have no faces left."""
        conn.execute(
            "UPDATE persons SET "
            "cover_face_id = (SELECT f.id FROM faces f WHERE f.person_id = persons.id "
            "                 ORDER BY f.confidence * f.w * f.h DESC, f.id LIMIT 1), "
            "image_count = (SELECT COUNT(DISTINCT image_id) FROM faces "
            "               WHERE person_id = persons.id)")
        conn.execute("DELETE FROM persons WHERE NOT EXISTS "
                     "(SELECT 1 FROM faces WHERE faces.person_id = persons.id)")

    def replace_person_clusters(self, clusters: dict[int, list[int]],
                                custom_names: dict[int, str] | None = None,
                                fixed: dict[int, list[int]] | None = None) -> int:
        """Rebuild people from automatic clusters while honouring user decisions.

        * Locked faces keep their person; people owning a locked face are never deleted.
        * ``fixed`` (person_id -> face_ids) attaches free faces to such people.
        * Other clusters inherit the old person with the largest overlap (ids/names stay stable).
        Returns the number of people afterwards.
        """
        fixed = fixed or {}
        with self._tx() as conn:
            old_names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM persons")}
            anchored = {r[0] for r in conn.execute(
                "SELECT DISTINCT person_id FROM faces WHERE locked = 1 AND person_id IS NOT NULL")}
            old_of_face = {r["id"]: r["person_id"] for r in conn.execute(
                "SELECT id, person_id FROM faces WHERE person_id IS NOT NULL AND locked = 0")}
            overlaps = []
            for key, fids in clusters.items():
                for pid, n in Counter(old_of_face[f] for f in fids if f in old_of_face).items():
                    if pid not in anchored:
                        overlaps.append((n, key, pid))
            overlaps.sort(key=lambda t: (-t[0], t[1], t[2]))
            assigned: dict[int, int] = {}
            used: set[int] = set()
            for _, key, pid in overlaps:
                if key not in assigned and pid not in used:
                    assigned[key] = pid
                    used.add(pid)
            next_id = max([0, *old_names, *assigned.values()]) + 1

            conn.execute("UPDATE faces SET person_id = NULL WHERE locked = 0")
            conn.execute("DELETE FROM persons WHERE id NOT IN "
                         "(SELECT DISTINCT person_id FROM faces WHERE locked = 1 AND person_id IS NOT NULL)")
            for pid, fids in fixed.items():
                if pid in anchored:
                    conn.executemany("UPDATE faces SET person_id = ? WHERE id = ? AND locked = 0",
                                     [(pid, f) for f in fids])
            for key, fids in clusters.items():
                if not fids:
                    continue
                pid = assigned.get(key)
                if pid is None:
                    pid, next_id = next_id, next_id + 1
                name = (custom_names or {}).get(key) or old_names.get(pid) or f"Person {pid:02d}"
                conn.execute("INSERT INTO persons (id, name) VALUES (?, ?)", (pid, name))
                conn.executemany("UPDATE faces SET person_id = ? WHERE id = ?",
                                 [(pid, f) for f in fids])
            self._refresh_person_stats(conn)
            self._bump_persons(conn)
            return int(conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0])

    def list_persons(self) -> list[sqlite3.Row]:
        """Return all person groups ordered by photo count descending."""
        return self._query(
            "SELECT p.id, p.name, p.cover_face_id, p.image_count, f.crop_path AS cover_crop_path, "
            "f.image_id AS cover_image_id, f.x, f.y, f.w, f.h, img.path AS image_path "
            "FROM persons p "
            "LEFT JOIN faces f ON f.id = p.cover_face_id "
            "LEFT JOIN images img ON img.id = f.image_id "
            "ORDER BY p.image_count DESC, p.id ASC"
        )

    def rename_person(self, person_id: int, new_name: str) -> bool:
        """Rename a person cluster."""
        with self._tx() as conn:
            res = conn.execute("UPDATE persons SET name = ? WHERE id = ?", (new_name.strip(), person_id))
            self._bump_persons(conn)
            return res.rowcount > 0

    def assign_face(self, face_id: int, person_id: int | None) -> None:
        """Pin a face to a person, or to nobody (``None`` = 'not a person I care about').
        Locked, so re-clustering never moves it."""
        with self._tx() as conn:
            if conn.execute("SELECT 1 FROM faces WHERE id = ?", (face_id,)).fetchone() is None:
                raise ValueError(f"No face with id {face_id}.")
            if person_id is not None and conn.execute(
                    "SELECT 1 FROM persons WHERE id = ?", (person_id,)).fetchone() is None:
                raise ValueError(f"No person with id {person_id}.")
            conn.execute("UPDATE faces SET person_id = ?, locked = 1 WHERE id = ?",
                         (person_id, face_id))
            self._refresh_person_stats(conn)
            self._bump_persons(conn)

    def create_person(self, name: str, face_ids: Sequence[int]) -> int:
        """New person from the given faces (e.g. split a wrong face out). Returns its id."""
        name, ids = name.strip(), sorted({int(i) for i in face_ids})
        if not name or not ids:
            raise ValueError("Give a name and at least one face.")
        with self._tx() as conn:
            found = conn.execute(
                f"SELECT COUNT(*) FROM faces WHERE id IN ({','.join('?' * len(ids))})", ids).fetchone()[0]
            if found != len(ids):
                raise ValueError("One or more face ids do not exist.")
            pid = int(conn.execute("INSERT INTO persons (name) VALUES (?)", (name,)).lastrowid)
            conn.executemany("UPDATE faces SET person_id = ?, locked = 1 WHERE id = ?",
                             [(pid, i) for i in ids])
            self._refresh_person_stats(conn)
            self._bump_persons(conn)
            return pid

    def merge_persons(self, keep_id: int, merge_id: int) -> None:
        """Move every face of ``merge_id`` into ``keep_id`` and lock them all."""
        if keep_id == merge_id:
            raise ValueError("Cannot merge a person into itself.")
        with self._tx() as conn:
            names = {r["id"]: r["name"] for r in conn.execute(
                "SELECT id, name FROM persons WHERE id IN (?, ?)", (keep_id, merge_id))}
            if len(names) != 2:
                raise ValueError("Both people must exist.")
            default = lambda n: re.fullmatch(r"Person \d+", n) is not None
            if default(names[keep_id]) and not default(names[merge_id]):
                conn.execute("UPDATE persons SET name = ? WHERE id = ?", (names[merge_id], keep_id))
            conn.execute("UPDATE faces SET person_id = ? WHERE person_id = ?", (keep_id, merge_id))
            conn.execute("UPDATE faces SET locked = 1 WHERE person_id = ?", (keep_id,))
            conn.execute("DELETE FROM persons WHERE id = ?", (merge_id,))
            self._refresh_person_stats(conn)
            self._bump_persons(conn)

    def confirm_person(self, person_id: int) -> int:
        """Lock every face currently in the person ("this cluster is right"). Returns count."""
        with self._tx() as conn:
            if conn.execute("SELECT 1 FROM persons WHERE id = ?", (person_id,)).fetchone() is None:
                raise ValueError(f"No person with id {person_id}.")
            n = conn.execute("UPDATE faces SET locked = 1 WHERE person_id = ?", (person_id,)).rowcount
            self._bump_persons(conn)
            return n

    def set_face_locked(self, face_id: int, locked: bool = True) -> bool:
        """Explicitly set the locked flag on a face."""
        with self._tx() as conn:
            changed = conn.execute("UPDATE faces SET locked = ? WHERE id = ?",
                                   (1 if locked else 0, face_id)).rowcount > 0
            if changed:
                self._bump_persons(conn)
            return changed

    def unlock_face(self, face_id: int) -> bool:
        """Hand a face back to automatic clustering (applies on the next people rebuild)."""
        with self._tx() as conn:
            changed = conn.execute("UPDATE faces SET locked = 0 WHERE id = ? AND locked = 1",
                                   (face_id,)).rowcount > 0
            if changed:
                self._bump_persons(conn)
            return changed

    def person_faces(self, person_id: int, limit: int = 200, offset: int = 0) -> list[sqlite3.Row]:
        """Face boxes of one person (for a review screen). No embeddings."""
        return self._query(
            "SELECT f.id, f.image_id, f.person_id, f.x, f.y, f.w, f.h, f.confidence, "
            "f.crop_path, f.locked, i.path FROM faces f JOIN images i ON i.id = f.image_id "
            "WHERE f.person_id = ? AND i.state != 'missing' "
            "ORDER BY f.confidence * f.w * f.h DESC, f.id LIMIT ? OFFSET ?",
            (person_id, limit, offset))

    def unassigned_faces(self, limit: int = 200, offset: int = 0) -> list[sqlite3.Row]:
        """Faces not in any person (loners and ones the user removed)."""
        return self._query(
            "SELECT f.id, f.image_id, f.person_id, f.x, f.y, f.w, f.h, f.confidence, "
            "f.crop_path, f.locked, i.path FROM faces f JOIN images i ON i.id = f.image_id "
            "WHERE f.person_id IS NULL AND i.state != 'missing' "
            "ORDER BY f.locked DESC, f.confidence * f.w * f.h DESC, f.id LIMIT ? OFFSET ?",
            (limit, offset))

    def get_person(self, person_id: int) -> sqlite3.Row | None:
        """Get one person row."""
        rows = self._query(
            "SELECT p.*, f.crop_path AS cover_crop_path, f.image_id AS cover_image_id "
            "FROM persons p "
            "LEFT JOIN faces f ON f.id = p.cover_face_id WHERE p.id = ?",
            (person_id,),
        )
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # Marks (stored in the database only; photos are never touched)
    # ------------------------------------------------------------------
    def set_mark(self, image_id: int, kind: str, note: str | None = None) -> None:
        """Add or update a mark (also archived by content hash so it can be restored)."""
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO marks (image_id, kind, note) VALUES (?, ?, ?) "
                "ON CONFLICT(image_id, kind) DO UPDATE SET "
                "note = excluded.note, created_at = datetime('now')",
                (image_id, kind, note))
            conn.execute(
                "INSERT INTO marks_archive (sha256, kind, note, path) "
                "SELECT sha256, ?, ?, path FROM images WHERE id = ? AND sha256 IS NOT NULL "
                "ON CONFLICT(sha256, kind, path) DO UPDATE SET "
                "note = excluded.note, created_at = datetime('now')",
                (kind, note, image_id))

    def clear_mark(self, image_id: int, kind: str) -> bool:
        """Remove a mark and its archive entry. Returns True if the mark existed."""
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM marks_archive WHERE kind = ? AND path = "
                "(SELECT path FROM images WHERE id = ?)", (kind, image_id))
            return conn.execute(
                "DELETE FROM marks WHERE image_id = ? AND kind = ?", (image_id, kind)
            ).rowcount > 0

    def get_marks(self, image_id: int | None = None, kind: str | None = None) -> list[sqlite3.Row]:
        """Marks, optionally filtered by image and/or kind."""
        clauses, params = [], []
        if image_id is not None:
            clauses.append("image_id = ?")
            params.append(image_id)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._query(f"SELECT * FROM marks{where} ORDER BY image_id, kind", params)

    # ------------------------------------------------------------------
    # Meta / revision (lets rebuilds be skipped when nothing changed)
    # ------------------------------------------------------------------
    @staticmethod
    def _bump(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('revision', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1")

    @staticmethod
    def _bump_persons(conn: sqlite3.Connection) -> None:
        """People changes must not invalidate duplicate/burst/group caches (they use 'revision')."""
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('persons_rev', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1")

    @staticmethod
    def _iou(a: Sequence[int], b: Sequence[int]) -> float:
        iw = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
        ih = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
        inter = max(0, iw) * max(0, ih)
        union = a[2] * a[3] + b[2] * b[3] - inter
        return inter / union if union else 0.0

    @staticmethod
    def _restore_locked(conn: sqlite3.Connection, image_id: int, kept: list[sqlite3.Row]) -> None:
        """Re-apply user decisions to the freshly detected faces of one photo (IoU >= 0.5)."""
        new = conn.execute("SELECT id, x, y, w, h FROM faces WHERE image_id = ? ORDER BY id",
                           (image_id,)).fetchall()
        taken: set[int] = set()
        for old in kept:
            best, best_iou = None, 0.5
            for n in new:
                if n["id"] in taken:
                    continue
                v = DatabaseManager._iou((old["x"], old["y"], old["w"], old["h"]),
                                         (n["x"], n["y"], n["w"], n["h"]))
                if v >= best_iou:
                    best, best_iou = n["id"], v
            if best is not None:
                taken.add(best)
                conn.execute("UPDATE faces SET person_id = ?, locked = 1 WHERE id = ?",
                             (old["person_id"], best))

    def revision(self) -> int:
        """Counter that changes whenever processed results change."""
        value = self.get_meta("revision")
        return int(value) if value else 0

    def get_meta(self, key: str) -> str | None:
        rows = self._query("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    # ------------------------------------------------------------------
    # Sources and file states (ok / offline / missing)
    # ------------------------------------------------------------------
    def add_source(self, path: str) -> None:
        """Remember a scanned root folder (used to tell 'drive unplugged' from 'file deleted')."""
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO sources (path) VALUES (?) "
                "ON CONFLICT(path) DO UPDATE SET last_seen = datetime('now')", (path,))

    def list_sources(self) -> list[str]:
        return [r["path"] for r in self._query("SELECT path FROM sources ORDER BY path")]

    def list_image_states(self) -> list[sqlite3.Row]:
        """``id, path, state`` of every image."""
        return self._query("SELECT id, path, state FROM images ORDER BY id")

    def image_ids_in_state(self, state: str) -> list[int]:
        return [int(r["id"]) for r in self._query("SELECT id FROM images WHERE state = ?", (state,))]

    def state_counts(self) -> dict[str, int]:
        counts = {"ok": 0, "offline": 0, "missing": 0}
        for r in self._query("SELECT state, COUNT(*) AS n FROM images GROUP BY state"):
            counts[r["state"]] = int(r["n"])
        return counts

    def set_states(self, updates: Iterable[tuple[int, str]]) -> int:
        """Apply ``(image_id, state)`` pairs. Returns how many were applied."""
        data = [(state, int(i)) for i, state in updates]
        if not data:
            return 0
        with self._tx() as conn:
            conn.executemany("UPDATE images SET state = ? WHERE id = ?", data)
            self._bump(conn)
        return len(data)

    # ------------------------------------------------------------------
    # Thumbnail bookkeeping
    # ------------------------------------------------------------------
    def set_thumb_path(self, image_id: int, path: str | None) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE images SET thumb_path = ? WHERE id = ?", (path, image_id))

    def unset_thumbs(self, image_ids: Iterable[int]) -> None:
        data = [(int(i),) for i in image_ids]
        if data:
            with self._tx() as conn:
                conn.executemany("UPDATE images SET thumb_path = NULL WHERE id = ?", data)

    def clear_thumb_paths(self) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE images SET thumb_path = NULL")

    def clear_crop_paths(self) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE faces SET crop_path = NULL")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def integrity_check(self) -> list[str]:
        """Problems reported by SQLite (empty list = healthy)."""
        return [r[0] for r in self._query("PRAGMA integrity_check") if r[0] != "ok"]

    def repair(self) -> dict[str, int]:
        """Fix inconsistencies left by crashes. Changes metadata only."""
        with self._tx() as conn:
            count_sql = "(SELECT COUNT(*) FROM faces WHERE faces.image_id = images.id)"
            fixed = conn.execute(
                f"UPDATE images SET face_count = {count_sql} "
                f"WHERE status = 'done' AND face_count != {count_sql}").rowcount
            requeued = conn.execute(
                "UPDATE images SET status = 'pending', error = NULL "
                "WHERE status = 'done' AND kind = 'photo' AND (sha256 IS NULL OR width IS NULL)").rowcount
            orphans = conn.execute(
                "DELETE FROM faces WHERE image_id NOT IN (SELECT id FROM images)").rowcount
            conn.execute("UPDATE images SET group_id = NULL WHERE group_id IS NOT NULL "
                         "AND group_id NOT IN (SELECT id FROM groups)")
            empty = conn.execute(
                "DELETE FROM groups WHERE id NOT IN "
                "(SELECT DISTINCT group_id FROM images WHERE group_id IS NOT NULL)").rowcount
            conn.execute("UPDATE groups SET image_count = "
                         "(SELECT COUNT(*) FROM images WHERE images.group_id = groups.id)")
            if fixed or requeued or orphans:
                self._bump(conn)
        return {"face_counts_fixed": fixed, "requeued": requeued,
                "orphan_faces_removed": orphans, "empty_groups_removed": empty}

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

    # ------------------------------------------------------------------
    # Phase D: analysis, bursts, places, date overrides, face review
    # ------------------------------------------------------------------
    def count_unanalyzed(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM images WHERE status = 'done' AND kind = 'photo' "
                            "AND state = 'ok' AND quality IS NULL")

    def fetch_unanalyzed(self, after_id: int, limit: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT id, path, exif_ts, ts_source FROM images WHERE status = 'done' AND kind = 'photo' "
            "AND state = 'ok' AND quality IS NULL AND id > ? ORDER BY id LIMIT ?", (after_id, limit))

    def save_analysis(self, updates: Sequence[tuple[int, Mapping[str, Any]]]) -> None:
        if not updates:
            return
        with self._tx() as conn:
            for image_id, a in updates:
                conn.execute(
                    "UPDATE images SET quality = ?, sharpness = ?, brightness = ?, dhash = ?, "
                    "content_type = ?, date_flag = ? WHERE id = ?",
                    (a.get("quality"), a.get("sharpness"), a.get("brightness"), a.get("dhash"),
                     a.get("content_type") or "photo", a.get("date_flag"), int(image_id)))
            self._bump(conn)

    def fetch_burst_rows(self) -> list[sqlite3.Row]:
        return self._query(
            "SELECT i.id, COALESCE(o.exif_ts, i.exif_ts) AS exif_ts, i.phash, i.quality "
            "FROM images i LEFT JOIN date_overrides o ON o.image_id = i.id "
            "WHERE i.status = 'done' AND i.state != 'missing' AND i.kind = 'photo' "
            "AND i.pair_id IS NULL AND i.phash IS NOT NULL "
            "AND COALESCE(o.exif_ts, i.exif_ts) IS NOT NULL "
            "AND (o.exif_ts IS NOT NULL OR i.ts_source IN ('exif_original', 'exif_datetime')) "
            "ORDER BY COALESCE(o.exif_ts, i.exif_ts), i.id")

    def replace_bursts(self, bursts: Sequence[Mapping[str, Any]]) -> int:
        with self._tx() as conn:
            conn.execute("UPDATE images SET burst_id = NULL")
            conn.execute("DELETE FROM bursts")
            for b in bursts:
                cur = conn.execute("INSERT INTO bursts (best_image_id, image_count) VALUES (?, ?)",
                                   (b["best_id"], len(b["image_ids"])))
                conn.executemany("UPDATE images SET burst_id = ? WHERE id = ?",
                                 [(int(cur.lastrowid), int(i)) for i in b["image_ids"]])
        return len(bursts)

    def get_bursts(self) -> list[sqlite3.Row]:
        return self._query("SELECT * FROM bursts ORDER BY id")

    def get_burst_images(self, burst_id: int) -> list[sqlite3.Row]:
        return self._query("SELECT * FROM images WHERE burst_id = ? ORDER BY exif_ts, id", (burst_id,))

    def fetch_gps_without_place(self, limit: int) -> list[sqlite3.Row]:
        return self._query("SELECT id, gps_lat, gps_lon FROM images WHERE status = 'done' "
                           "AND gps_lat IS NOT NULL AND place IS NULL ORDER BY id LIMIT ?", (limit,))

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
                (image_id, exif_ts, note))
            self._bump(conn)

    def clear_date_override(self, image_id: int) -> bool:
        with self._tx() as conn:
            removed = conn.execute("DELETE FROM date_overrides WHERE image_id = ?", (image_id,)).rowcount > 0
            if removed:
                self._bump(conn)
        return removed

    def suspicious_dates(self, limit: int = 500) -> list[sqlite3.Row]:
        return self._query(
            "SELECT i.id, i.path, i.exif_ts, i.ts_source, i.date_flag, "
            "o.exif_ts AS override_ts FROM images i LEFT JOIN date_overrides o ON o.image_id = i.id "
            "WHERE i.status = 'done' AND i.date_flag IS NOT NULL AND i.date_flag != 'mtime_only' "
            "ORDER BY i.date_flag, i.id LIMIT ?", (limit,))

    def low_confidence_faces(self, below: float = 0.8, limit: int = 500) -> list[sqlite3.Row]:
        return self._query(
            "SELECT f.*, i.path FROM faces f JOIN images i ON i.id = f.image_id "
            "WHERE f.confidence < ? ORDER BY f.confidence LIMIT ?", (below, limit))

    # ------------------------------------------------------------------
    # Phase E: marks restore, move detection
    # ------------------------------------------------------------------
    def restore_marks(self) -> int:
        """Re-apply archived marks to photos with the same content.

        Restored when the photo is at the archived path (after a reset), or when the
        archived file is gone and exactly one photo with that content exists.
        Returns the number of marks restored.
        """
        rows = self._query(
            "SELECT a.sha256, a.kind, a.note, a.path AS old_path, i.id AS image_id, "
            "i.path AS new_path FROM marks_archive a JOIN images i ON i.sha256 = a.sha256 "
            "WHERE i.status = 'done' AND i.state != 'missing' "
            "AND NOT EXISTS (SELECT 1 FROM marks m WHERE m.image_id = i.id AND m.kind = a.kind) "
            "AND (i.path = a.path OR NOT EXISTS "
            "(SELECT 1 FROM images o WHERE o.path = a.path AND o.state != 'missing'))")
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
                    (r["image_id"], r["kind"], r["note"])).rowcount
        return restored

    def find_moves(self) -> list[sqlite3.Row]:
        """Missing photos whose content now exists at exactly one other path.

        Run file-state checking first. Rows: ``old_id, old_path, new_id, new_path``.
        """
        return self._query(
            "SELECT o.id AS old_id, o.path AS old_path, n.id AS new_id, n.path AS new_path "
            "FROM images o JOIN images n ON n.sha256 = o.sha256 AND n.id != o.id "
            "WHERE o.state = 'missing' AND o.sha256 IS NOT NULL "
            "AND n.state = 'ok' AND n.status = 'done' "
            "AND (SELECT COUNT(*) FROM images x WHERE x.sha256 = o.sha256 "
            "     AND x.state = 'ok' AND x.id != o.id) = 1 "
            "AND (SELECT COUNT(*) FROM images y WHERE y.sha256 = o.sha256 "
            "     AND y.state = 'missing') = 1")

    # ------------------------------------------------------------------
    # Phase E: full-text index
    # ------------------------------------------------------------------
    def ensure_fts(self) -> bool:
        """Create the FTS5 table if this SQLite supports it. Cached."""
        if self._fts is None:
            try:
                with self._lock:
                    self._db.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS fts_images USING fts5("
                        "name, folder, place, event, kind, date, "
                        "tokenize = 'unicode61 remove_diacritics 2')")
                self._fts = True
            except sqlite3.Error:
                self._fts = False
        return self._fts

    def rebuild_fts(self) -> int:
        """Rebuild the text index from scratch. Returns rows indexed (0 if unsupported)."""
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
            "WHERE i.status = 'done' AND i.state != 'missing'")
        data = [(r["id"], os.path.basename(r["path"]), os.path.dirname(r["path"]),
                 r["place"] or "", r["event"] or "",
                 " ".join(x for x in (r["content_type"], r["kind"], r["format"], r["tags"], r["people"]) if x),
                 _date_words(r["ts"])) for r in rows]
        with self._tx() as conn:
            conn.execute("DELETE FROM fts_images")
            conn.executemany(
                "INSERT INTO fts_images (rowid, name, folder, place, event, kind, date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", data)
        return len(data)

    # ------------------------------------------------------------------
    # Phase E: combined search
    # ------------------------------------------------------------------
    def _find_where(self, f: Mapping[str, Any]) -> tuple[str, list[Any]]:
        unknown = set(f) - FIND_FILTERS
        if unknown:
            raise ValueError(f"Unknown filter(s): {', '.join(sorted(unknown))}")
        if f.get("duplicate") not in (None, "none", "any", "exact", "near"):
            raise ValueError("duplicate must be one of: none, any, exact, near")
        for key in ("mark", "no_mark"):
            if f.get(key) not in (None, *MARK_KINDS):
                raise ValueError(f"{key} must be one of: {', '.join(MARK_KINDS)}")
        c: list[str] = ["i.status = 'done'"]
        p: list[Any] = []

        def add(cond: str, *vals: Any) -> None:
            c.append(cond)
            p.extend(vals)

        if not f.get("include_missing"):
            add("i.state != 'missing'")
        if not f.get("include_live_video"):
            add("i.pair_id IS NULL")
        if not (f.get("include_hidden") or f.get("mark") == "hidden"):
            add("NOT EXISTS (SELECT 1 FROM marks h WHERE h.image_id = i.id AND h.kind = 'hidden')")
        text = (f.get("text") or "").strip()
        if text:
            if self.ensure_fts():
                query = fts_query(text)
                if query:
                    add("i.id IN (SELECT rowid FROM fts_images WHERE fts_images MATCH ?)", query)
            else:
                for term in re.findall(r"[^\W_]+", text):
                    add("(i.path LIKE ? OR i.place LIKE ?)", f"%{term}%", f"%{term}%")
        if f.get("min_faces") is not None:
            add("i.face_count >= ?", f["min_faces"])
        if f.get("max_faces") is not None:
            add("i.face_count <= ?", f["max_faces"])
        if f.get("taken_from") is not None:
            add(f"{_EFF} >= ?", f["taken_from"])
        if f.get("taken_until") is not None:
            until = f["taken_until"]
            add(f"{_EFF} <= ?", until + "~" if len(until) <= 10 else until)
        if f.get("group_id") is not None:
            add("i.group_id = ?", f["group_id"])
        for key, column in (("path_contains", "i.path"), ("place_contains", "i.place")):
            if f.get(key):
                esc = f[key].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                add(f"{column} LIKE ? ESCAPE '\\'", f"%{esc}%")
        if f.get("content_type") is not None:
            add("i.content_type = ?", f["content_type"])
        if f.get("kind") is not None:
            add("i.kind = ?", f["kind"])
        if f.get("format") is not None:
            add("i.format = ? COLLATE NOCASE", f["format"])
        if f.get("tag"):
            add("EXISTS (SELECT 1 FROM tags t WHERE t.image_id = i.id AND t.label = ? COLLATE NOCASE)",
                f["tag"])
        if f.get("min_quality") is not None:
            add("i.quality >= ?", f["min_quality"])
        if f.get("burst_id") is not None:
            add("i.burst_id = ?", f["burst_id"])
        if f.get("person_id") is not None:
            add("EXISTS (SELECT 1 FROM faces fc WHERE fc.image_id = i.id AND fc.person_id = ?)", f["person_id"])
        if f.get("in_burst") is not None:
            add("i.burst_id IS NOT NULL" if f["in_burst"] else "i.burst_id IS NULL")
        dup = f.get("duplicate")
        if dup == "none":
            add("NOT EXISTS (SELECT 1 FROM duplicates d WHERE d.image_id = i.id)")
        elif dup == "any":
            add("EXISTS (SELECT 1 FROM duplicates d WHERE d.image_id = i.id)")
        elif dup in ("exact", "near"):
            add("EXISTS (SELECT 1 FROM duplicates d WHERE d.image_id = i.id AND d.kind = ?)", dup)
        if f.get("mark"):
            add("EXISTS (SELECT 1 FROM marks m WHERE m.image_id = i.id AND m.kind = ?)", f["mark"])
        if f.get("no_mark"):
            add("NOT EXISTS (SELECT 1 FROM marks m WHERE m.image_id = i.id AND m.kind = ?)",
                f["no_mark"])
        return " WHERE " + " AND ".join(c), p

    _FROM = " FROM images i LEFT JOIN date_overrides o ON o.image_id = i.id"

    def find_images(self, *, sort: str = "date", limit: int = 100, offset: int = 0,
                    **filters: Any) -> list[sqlite3.Row]:
        """Search with any combination of :data:`FIND_FILTERS`.

        ``sort``: date, date_desc, quality, path or size (undated photos sort last by date).
        Rows include ``effective_ts`` (the date after overrides).
        """
        if sort not in _SORTS:
            raise ValueError(f"sort must be one of: {', '.join(_SORTS)}")
        where, params = self._find_where(filters)
        return self._query(
            f"SELECT i.*, {_EFF} AS effective_ts{self._FROM}{where} "
            f"ORDER BY {_SORTS[sort]} LIMIT ? OFFSET ?", (*params, int(limit), int(offset)))

    def count_images(self, **filters: Any) -> int:
        where, params = self._find_where(filters)
        return self._scalar(f"SELECT COUNT(*){self._FROM}{where}", params)

    def timeline(self, granularity: str = "month") -> list[dict[str, Any]]:
        """Photos per period, by effective date. Undated photos come last with period None."""
        widths = {"year": 4, "month": 7, "day": 10}
        if granularity not in widths:
            raise ValueError("granularity must be year, month or day")
        rows = self._query(
            f"SELECT substr({_EFF}, 1, {widths[granularity]}) AS period, COUNT(*) AS n"
            f"{self._FROM} WHERE i.status = 'done' AND i.state != 'missing' AND i.pair_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM marks h WHERE h.image_id = i.id AND h.kind = 'hidden') "
            "GROUP BY period ORDER BY period IS NULL, period")
        return [{"period": r["period"], "count": int(r["n"])} for r in rows]

    # ------------------------------------------------------------------
    # Phase E: saved searches
    # ------------------------------------------------------------------
    def save_search(self, name: str, filters: Mapping[str, Any]) -> None:
        """Store filters (any :data:`FIND_FILTERS` key, plus ``sort``) under ``name``."""
        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError("Name must be 1-100 characters.")
        bad = set(filters) - FIND_FILTERS - {"sort"}
        if bad:
            raise ValueError(f"Unknown filter(s): {', '.join(sorted(bad))}")
        if filters.get("sort", "date") not in _SORTS:
            raise ValueError(f"sort must be one of: {', '.join(_SORTS)}")
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO saved_searches (name, filters) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET filters = excluded.filters",
                (name, json.dumps(dict(filters), sort_keys=True)))

    def list_saved_searches(self) -> list[dict[str, Any]]:
        return [{"name": r["name"], "filters": json.loads(r["filters"])}
                for r in self._query("SELECT name, filters FROM saved_searches ORDER BY name")]

    def get_saved_search(self, name: str) -> dict[str, Any] | None:
        rows = self._query("SELECT filters FROM saved_searches WHERE name = ?", (name,))
        return json.loads(rows[0]["filters"]) if rows else None

    def delete_saved_search(self, name: str) -> bool:
        with self._tx() as conn:
            return conn.execute("DELETE FROM saved_searches WHERE name = ?", (name,)).rowcount > 0

    # ------------------------------------------------------------------
    # Phase F: tags and embeddings
    # ------------------------------------------------------------------
    @staticmethod
    def _write_tags(conn: sqlite3.Connection, image_id: int, res: Mapping[str, Any]) -> None:
        conn.execute("DELETE FROM tags WHERE image_id = ? AND source = 'scene'", (image_id,))
        conn.executemany(
            "INSERT OR REPLACE INTO tags (image_id, label, score) VALUES (?, ?, ?)",
            [(image_id, str(l), float(s)) for l, s in res.get("tags", [])])
        conn.execute("UPDATE images SET tagged_with = ? WHERE id = ?", (res.get("tag_model"), image_id))
        emb = res.get("embedding")
        if emb is None:
            conn.execute("DELETE FROM embeddings WHERE image_id = ?", (image_id,))
        else:
            conn.execute("INSERT OR REPLACE INTO embeddings (image_id, model, vec) VALUES (?, ?, ?)",
                         (image_id, res.get("tag_model") or "", emb))

    def save_tags(self, updates: Sequence[tuple[int, Mapping[str, Any]]]) -> None:
        """Store ``(image_id, {"tags", "tag_model", "embedding"?})`` pairs in one transaction."""
        if not updates:
            return
        with self._tx() as conn:
            for image_id, res in updates:
                self._write_tags(conn, int(image_id), res)
            self._bump(conn)

    _TAGGABLE = "status = 'done' AND kind = 'photo' AND state = 'ok'"

    def count_untagged(self, model_sig: str) -> int:
        return self._scalar(f"SELECT COUNT(*) FROM images WHERE {self._TAGGABLE} "
                            "AND (tagged_with IS NULL OR tagged_with != ?)", (model_sig,))

    def fetch_untagged(self, model_sig: str, after_id: int, limit: int) -> list[sqlite3.Row]:
        return self._query(f"SELECT id, path FROM images WHERE {self._TAGGABLE} "
                           "AND (tagged_with IS NULL OR tagged_with != ?) AND id > ? "
                           "ORDER BY id LIMIT ?", (model_sig, after_id, limit))

    def get_tags(self, image_id: int) -> list[sqlite3.Row]:
        return self._query("SELECT label, score, source FROM tags WHERE image_id = ? "
                           "ORDER BY score DESC, label", (image_id,))

    def list_tag_counts(self, limit: int = 100) -> list[sqlite3.Row]:
        return self._query(
            "SELECT t.label AS label, COUNT(*) AS n FROM tags t JOIN images i ON i.id = t.image_id "
            "WHERE i.state != 'missing' GROUP BY t.label ORDER BY n DESC, t.label LIMIT ?", (limit,))

    def clear_tags(self) -> None:
        """Remove all tags and embeddings (use before re-tagging with a different model)."""
        with self._tx() as conn:
            conn.execute("DELETE FROM tags")
            conn.execute("DELETE FROM embeddings")
            conn.execute("UPDATE images SET tagged_with = NULL")
            self._bump(conn)

    def get_embedding(self, image_id: int) -> sqlite3.Row | None:
        rows = self._query("SELECT model, vec FROM embeddings WHERE image_id = ?", (image_id,))
        return rows[0] if rows else None

    def embedding_rows(self, model: str, after_id: int, limit: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT e.image_id, e.vec FROM embeddings e JOIN images i ON i.id = e.image_id "
            "WHERE e.model = ? AND e.image_id > ? AND i.state != 'missing' AND i.pair_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM marks h WHERE h.image_id = i.id AND h.kind = 'hidden') "
            "ORDER BY e.image_id LIMIT ?", (model, after_id, limit))

    def list_fingerprints(self) -> list[sqlite3.Row]:
        """``path, size, mtime_ns`` of every registered file (for change detection)."""
        return self._query("SELECT path, size, mtime_ns FROM images")

    def requeue_faces_without_embeddings(self) -> int:
        """Reset status to 'pending' on done photos that have faces without embeddings.

        Called when SFace becomes available so existing libraries get backfilled.
        Returns the number of photos re-queued.
        """
        with self._tx() as conn:
            cur = conn.execute(
                "UPDATE images SET status = 'pending' "
                "WHERE status = 'done' AND kind = 'photo' AND id IN ("
                "   SELECT DISTINCT image_id FROM faces WHERE embedding IS NULL"
                ")"
            )
            count = cur.rowcount
            if count:
                self._bump(conn)
            return count

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Delete all rows (database only; the CLI decides about output files)."""
        with self._tx() as conn:
            conn.execute("DELETE FROM faces")
            conn.execute("DELETE FROM persons")
            conn.execute("DELETE FROM duplicates")
            conn.execute("DELETE FROM bursts")
            conn.execute("DELETE FROM images")
            conn.execute("DELETE FROM groups")
            conn.execute("DELETE FROM meta")
        with self._lock:
            self._db.execute("VACUUM")
        log.info("Database reset.")

    def clear_sources(self) -> None:
        """Forget scanned root folders (the 'rescan all known sources' list)."""
        with self._tx() as conn:
            conn.execute("DELETE FROM sources")

    def clear_saved_searches(self) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM saved_searches")

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------
    def list_image_paths(self) -> list[sqlite3.Row]:
        """``id, path`` of every registered image."""
        return self._query("SELECT id, path FROM images ORDER BY id")

    def delete_images(self, image_ids: Iterable[int], chunk_size: int = 500) -> int:
        """Delete image rows (faces, duplicates, marks cascade). Returns the count."""
        ids = [int(i) for i in image_ids]
        removed = 0
        with self._tx() as conn:
            for start in range(0, len(ids), chunk_size):
                part = ids[start:start + chunk_size]
                marks = ",".join("?" for _ in part)
                removed += conn.execute(
                    f"DELETE FROM images WHERE id IN ({marks})", part).rowcount
            if removed:
                self._bump(conn)
        return removed

    # ------------------------------------------------------------------
    # Live Photo pairing (C.2)
    # ------------------------------------------------------------------
    def list_pair_candidates(self) -> list[sqlite3.Row]:
        """Images and videos that may form Live Photo pairs."""
        return self._query(
            "SELECT id, path, kind, duration_s, pair_id FROM images "
            "WHERE status = 'done' AND state != 'missing' "
            "ORDER BY path"
        )

    def set_pairs(self, updates: Iterable[tuple[int, int | None]]) -> int:
        """Set or clear pair_id on images. (image_id, pair_id) tuples."""
        data = [(p, i) for i, p in updates]
        if not data:
            return 0
        with self._tx() as conn:
            conn.executemany("UPDATE images SET pair_id = ? WHERE id = ?", data)
            self._bump(conn)
        return len(data)

    def get_paired_video(self, photo_id: int) -> sqlite3.Row | None:
        """The video paired with a photo, if any."""
        rows = self._query(
            "SELECT * FROM images WHERE pair_id = ? AND kind = 'video' LIMIT 1",
            (photo_id,),
        )
        return rows[0] if rows else None
