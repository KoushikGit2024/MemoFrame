"""SQLite access layer for the photo organizer.

One connection is shared behind a lock, and every write goes through
:meth:`DatabaseManager._tx` so a batch is committed atomically. The database
stores metadata only; original photographs are never touched.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from utils.logger import get_logger

log = get_logger("database")

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

# Per-image columns written by save_results() (face_count is derived).
RESULT_COLUMNS: tuple[str, ...] = (
    "width", "height", "sha256", "phash", "exif_ts", "ts_source",
    "gps_lat", "gps_lon", "features", "thumb_path",
)


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

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            conn.close()
            raise DatabaseError(
                f"Database schema v{version} is newer than this program (v{SCHEMA_VERSION})."
            )
        if version < SCHEMA_VERSION:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
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

        * unknown path      -> inserted as ``pending``
        * changed size/mtime -> reset to ``pending`` (old faces/duplicate rows removed)
        * unchanged          -> left alone (this is what makes runs resumable)

        ``files`` may be a lazy generator; it is committed every ``chunk_size``
        items so a crash during a huge scan keeps the earlier progress.
        """
        known = {
            r["path"]: (r["id"], r["size"], r["mtime_ns"])
            for r in self._query("SELECT id, path, size, mtime_ns FROM images")
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
                        known[path] = (int(cur.lastrowid), size, mtime_ns)
                        new += 1
                    elif (old[1], old[2]) != (size, mtime_ns):
                        self._reset_image(conn, old[0], size, mtime_ns)
                        known[path] = (old[0], size, mtime_ns)
                        changed += 1
                    else:
                        unchanged += 1
        stats = ScanStats(new, changed, unchanged)
        log.info("Registered files: %d new, %d changed, %d unchanged",
                 stats.new, stats.changed, stats.unchanged)
        return stats

    @staticmethod
    def _reset_image(conn: sqlite3.Connection, image_id: int, size: int, mtime_ns: int) -> None:
        conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))
        conn.execute("DELETE FROM duplicates WHERE image_id = ?", (image_id,))
        conn.execute(
            """UPDATE images SET
                   size = ?, mtime_ns = ?, width = NULL, height = NULL,
                   sha256 = NULL, phash = NULL, exif_ts = NULL, ts_source = NULL,
                   gps_lat = NULL, gps_lon = NULL, features = NULL, thumb_path = NULL,
                   face_count = 0, status = 'pending', error = NULL,
                   group_id = NULL, processed_at = NULL
               WHERE id = ?""",
            (size, mtime_ns, image_id),
        )

    def fetch_pending(self, limit: int, include_failed: bool = False) -> list[sqlite3.Row]:
        """Next batch of images to process (``id, path, size, mtime_ns``)."""
        statuses = (STATUS_PENDING, STATUS_FAILED) if include_failed else (STATUS_PENDING,)
        marks = ",".join("?" for _ in statuses)
        return self._query(
            f"SELECT id, path, size, mtime_ns FROM images "
            f"WHERE status IN ({marks}) ORDER BY id LIMIT ?",
            (*statuses, limit),
        )

    def count_pending(self, include_failed: bool = False) -> int:
        """Number of images still waiting for processing."""
        if include_failed:
            return self._scalar("SELECT COUNT(*) FROM images WHERE status IN ('pending','failed')")
        return self._scalar("SELECT COUNT(*) FROM images WHERE status = 'pending'")

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
                params.update(face_count=len(faces), image_id=image_id)
                conn.execute(update_sql, params)
                conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))
                conn.executemany(
                    "INSERT INTO faces (image_id, label, x, y, w, h, confidence, crop_path) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            image_id,
                            f.get("label") or f"Face {i:03d}",
                            int(f["x"]), int(f["y"]), int(f["w"]), int(f["h"]),
                            float(f["confidence"]),
                            f.get("crop_path"),
                        )
                        for i, f in enumerate(faces, start=1)
                    ],
                )

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
        """``id, sha256, phash`` of every successfully processed image."""
        return self._query(
            "SELECT id, sha256, phash FROM images WHERE status = 'done' ORDER BY id"
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
        """``cluster_id -> member images`` (``id, path, size, width, height, kind``)."""
        rows = self._query(
            """SELECT d.cluster_id, d.kind, i.id, i.path, i.size, i.width, i.height
                 FROM duplicates d JOIN images i ON i.id = d.image_id
                ORDER BY d.cluster_id, i.id"""
        )
        clusters: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            clusters.setdefault(row["cluster_id"], []).append(row)
        return clusters

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------
    def fetch_grouping_rows(self) -> list[sqlite3.Row]:
        """Inputs for the grouper (processed images only)."""
        return self._query(
            """SELECT id, path, exif_ts, ts_source, gps_lat, gps_lon, phash, features
                 FROM images WHERE status = 'done' ORDER BY id"""
        )

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
        """Images in a group, in timestamp order."""
        return self._query(
            "SELECT * FROM images WHERE group_id = ? ORDER BY exif_ts, id", (group_id,)
        )

    # ------------------------------------------------------------------
    # Search / lookup
    # ------------------------------------------------------------------
    def get_image(self, image_id: int) -> sqlite3.Row | None:
        """One image row, or ``None``."""
        rows = self._query("SELECT * FROM images WHERE id = ?", (image_id,))
        return rows[0] if rows else None

    def get_faces(self, image_id: int) -> list[sqlite3.Row]:
        """Face boxes for one image (labels are local to that image)."""
        return self._query("SELECT * FROM faces WHERE image_id = ? ORDER BY id", (image_id,))

    def search_images(
        self,
        *,
        min_faces: int | None = None,
        max_faces: int | None = None,
        taken_from: str | None = None,
        taken_until: str | None = None,
        group_id: int | None = None,
        path_contains: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        """Search processed images. All filters are optional and combined with AND.

        ``taken_from`` / ``taken_until`` are ISO strings (``'2024-06-01'`` works,
        because ISO timestamps sort as text).
        """
        clauses = ["status = 'done'"]
        params: list[Any] = []
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
        }

    def failed_images(self) -> list[sqlite3.Row]:
        """``path, error`` for every failed image."""
        return self._query("SELECT path, error FROM images WHERE status = 'failed' ORDER BY path")

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Delete all rows (database only; the CLI decides about output files)."""
        with self._tx() as conn:
            conn.execute("DELETE FROM faces")
            conn.execute("DELETE FROM duplicates")
            conn.execute("DELETE FROM images")
            conn.execute("DELETE FROM groups")
        with self._lock:
            self._db.execute("VACUUM")
        log.info("Database reset.")

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------
    def list_image_paths(self) -> list[sqlite3.Row]:
        """``id, path`` of every registered image."""
        return self._query("SELECT id, path FROM images ORDER BY id")

    def delete_images(self, image_ids: Iterable[int], chunk_size: int = 500) -> int:
        """Delete image rows (faces and duplicate entries cascade). Returns the count."""
        ids = [int(i) for i in image_ids]
        removed = 0
        with self._tx() as conn:
            for start in range(0, len(ids), chunk_size):
                part = ids[start:start + chunk_size]
                marks = ",".join("?" for _ in part)
                removed += conn.execute(
                    f"DELETE FROM images WHERE id IN ({marks})", part).rowcount
        return removed