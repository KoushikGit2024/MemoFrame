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
    "width",
    "height",
    "sha256",
    "phash",
    "exif_ts",
    "ts_source",
    "gps_lat",
    "gps_lon",
    "features",
    "thumb_path",
    "kind",
    "duration_s",
    "format",
    "quality",
    "sharpness",
    "brightness",
    "dhash",
    "content_type",
    "date_flag",
)

from database.analysis_mixin import AnalysisDbMixin
from database.maintenance_mixin import MaintenanceDbMixin
from database.marks_mixin import MarksDbMixin
from database.organization_mixin import OrganizationDbMixin
from database.person_mixin import PersonDbMixin
from database.search_mixin import FIND_FILTERS, MARK_KINDS, SearchDbMixin, _EFF, _SORTS
from database.tag_mixin import TagDbMixin

_MONTHS = (
    "January February March April May June July August September October November December"
).split()


def fts_query(text: str) -> str:
    """Safe FTS5 query: every word becomes a quoted prefix term, all must match."""
    return " ".join(f'"{t}"*' for t in re.findall(r"[^\W_]+", text))


def _date_words(ts: str | None) -> str:
    try:
        year, month = int(ts[:4]), int(ts[5:7])  # type: ignore[index]
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


class DatabaseManager(
    PersonDbMixin,
    SearchDbMixin,
    AnalysisDbMixin,
    TagDbMixin,
    MaintenanceDbMixin,
    OrganizationDbMixin,
    MarksDbMixin,
):
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
                isolation_level=None,  # we manage transactions explicitly
                check_same_thread=False,  # access is serialised by self._lock
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
            migrate(conn, prefix)  # backs up first when upgrading an existing DB
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
        log.info(
            "Registered files: %d new, %d changed, %d unchanged",
            stats.new,
            stats.changed,
            stats.unchanged,
        )
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
            return self._scalar(
                "SELECT COUNT(*) FROM images WHERE status IN ('pending','failed') AND state = 'ok'"
            )
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
                    (image_id,),
                ).fetchall()
                conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))
                conn.executemany(
                    "INSERT INTO faces (image_id, label, x, y, w, h, confidence, crop_path, embedding, person_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            image_id,
                            f.get("label") or f"Face {i:03d}",
                            int(f["x"]),
                            int(f["y"]),
                            int(f["w"]),
                            int(f["h"]),
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
            "videos": self._scalar(
                "SELECT COUNT(*) FROM images WHERE status = 'done' AND kind = 'video'"
            ),
            "live_pairs": self._scalar("SELECT COUNT(*) FROM images WHERE pair_id IS NOT NULL"),
            "bursts": self._scalar("SELECT COUNT(*) FROM bursts"),
            "tagged": self._scalar("SELECT COUNT(*) FROM images WHERE tagged_with IS NOT NULL"),
            "screenshots": self._scalar(
                "SELECT COUNT(*) FROM images WHERE content_type = 'screenshot'"
            ),
            "documents": self._scalar(
                "SELECT COUNT(*) FROM images WHERE content_type = 'document'"
            ),
            "date_issues": self._scalar(
                "SELECT COUNT(*) FROM images WHERE date_flag IN ('future','implausible','none')"
            ),
            "offline_images": self._scalar("SELECT COUNT(*) FROM images WHERE state = 'offline'"),
            "missing_images": self._scalar("SELECT COUNT(*) FROM images WHERE state = 'missing'"),
        }

    def failed_images(self) -> list[sqlite3.Row]:
        """``path, error`` for every failed image."""
        return self._query(
            "SELECT id, path, error FROM images WHERE status = 'failed' ORDER BY path"
        )

    # ------------------------------------------------------------------
    # Meta / revision (lets rebuilds be skipped when nothing changed)
    # ------------------------------------------------------------------
    @staticmethod
    def _bump(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('revision', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1"
        )

    @staticmethod
    def _bump_persons(conn: sqlite3.Connection) -> None:
        """People changes must not invalidate duplicate/burst/group caches (they use 'revision')."""
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('persons_rev', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1"
        )

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
        new = conn.execute(
            "SELECT id, x, y, w, h FROM faces WHERE image_id = ? ORDER BY id", (image_id,)
        ).fetchall()
        taken: set[int] = set()
        for old in kept:
            best, best_iou = None, 0.5
            for n in new:
                if n["id"] in taken:
                    continue
                v = DatabaseManager._iou(
                    (old["x"], old["y"], old["w"], old["h"]), (n["x"], n["y"], n["w"], n["h"])
                )
                if v >= best_iou:
                    best, best_iou = n["id"], v
            if best is not None:
                taken.add(best)
                conn.execute(
                    "UPDATE faces SET person_id = ?, locked = 1 WHERE id = ?",
                    (old["person_id"], best),
                )

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
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # ------------------------------------------------------------------
    # Sources and file states (ok / offline / missing)
    # ------------------------------------------------------------------
    def add_source(self, path: str) -> None:
        """Remember a scanned root folder (used to tell 'drive unplugged' from 'file deleted')."""
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO sources (path) VALUES (?) "
                "ON CONFLICT(path) DO UPDATE SET last_seen = datetime('now')",
                (path,),
            )

    def list_sources(self) -> list[str]:
        return [r["path"] for r in self._query("SELECT path FROM sources ORDER BY path")]

    def list_image_states(self) -> list[sqlite3.Row]:
        """``id, path, state`` of every image."""
        return self._query("SELECT id, path, state FROM images ORDER BY id")

    def image_ids_in_state(self, state: str) -> list[int]:
        return [
            int(r["id"]) for r in self._query("SELECT id FROM images WHERE state = ?", (state,))
        ]

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
    # Reporting
    # ------------------------------------------------------------------
