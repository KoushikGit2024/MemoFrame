"""Database mixin for user marks (favourite, hidden, reviewed, keep)."""

from __future__ import annotations

import sqlite3


class MarksDbMixin:
    """Methods for setting, clearing, and fetching marks."""

    def set_mark(self, image_id: int, kind: str, note: str | None = None) -> None:
        """Add or update a mark (also archived by content hash so it can be restored)."""
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO marks (image_id, kind, note) VALUES (?, ?, ?) "
                "ON CONFLICT(image_id, kind) DO UPDATE SET "
                "note = excluded.note, created_at = datetime('now')",
                (image_id, kind, note),
            )
            conn.execute(
                "INSERT INTO marks_archive (sha256, kind, note, path) "
                "SELECT sha256, ?, ?, path FROM images WHERE id = ? AND sha256 IS NOT NULL "
                "ON CONFLICT(sha256, kind, path) DO UPDATE SET "
                "note = excluded.note, created_at = datetime('now')",
                (kind, note, image_id),
            )

    def clear_mark(self, image_id: int, kind: str) -> bool:
        """Remove a mark and its archive entry. Returns True if the mark existed."""
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM marks_archive WHERE kind = ? AND path = "
                "(SELECT path FROM images WHERE id = ?)",
                (kind, image_id),
            )
            return (
                conn.execute(
                    "DELETE FROM marks WHERE image_id = ? AND kind = ?", (image_id, kind)
                ).rowcount
                > 0
            )

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
