"""Database mixin for tag classification and embedding persistence."""
from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence


class TagDbMixin:
    """Methods for scene tags, whole-image embeddings, and face embedding backfilling."""

    _TAGGABLE = "status = 'done' AND kind = 'photo' AND state = 'ok'"

    @staticmethod
    def _write_tags(conn: sqlite3.Connection, image_id: int, res: Mapping[str, Any]) -> None:
        conn.execute("DELETE FROM tags WHERE image_id = ? AND source = 'scene'", (image_id,))
        conn.executemany(
            "INSERT OR REPLACE INTO tags (image_id, label, score) VALUES (?, ?, ?)",
            [(image_id, str(l), float(s)) for l, s in res.get("tags", [])],
        )
        conn.execute("UPDATE images SET tagged_with = ? WHERE id = ?", (res.get("tag_model"), image_id))
        emb = res.get("embedding")
        if emb is None:
            conn.execute("DELETE FROM embeddings WHERE image_id = ?", (image_id,))
        else:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (image_id, model, vec) VALUES (?, ?, ?)",
                (image_id, res.get("tag_model") or "", emb),
            )

    def save_tags(self, updates: Sequence[tuple[int, Mapping[str, Any]]]) -> None:
        """Store (image_id, {"tags", "tag_model", "embedding"?}) pairs in one transaction."""
        if not updates:
            return
        with self._tx() as conn:
            for image_id, res in updates:
                self._write_tags(conn, int(image_id), res)
            self._bump(conn)

    def count_untagged(self, model_sig: str) -> int:
        return self._scalar(
            f"SELECT COUNT(*) FROM images WHERE {self._TAGGABLE} "
            "AND (tagged_with IS NULL OR tagged_with != ?)",
            (model_sig,),
        )

    def fetch_untagged(self, model_sig: str, after_id: int, limit: int) -> list[sqlite3.Row]:
        return self._query(
            f"SELECT id, path FROM images WHERE {self._TAGGABLE} "
            "AND (tagged_with IS NULL OR tagged_with != ?) AND id > ? "
            "ORDER BY id LIMIT ?",
            (model_sig, after_id, limit),
        )

    def get_tags(self, image_id: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT label, score, source FROM tags WHERE image_id = ? "
            "ORDER BY score DESC, label",
            (image_id,),
        )

    def list_tag_counts(self, limit: int = 100) -> list[sqlite3.Row]:
        return self._query(
            "SELECT t.label AS label, COUNT(*) AS n FROM tags t JOIN images i ON i.id = t.image_id "
            "WHERE i.state != 'missing' GROUP BY t.label ORDER BY n DESC, t.label LIMIT ?",
            (limit,),
        )

    def clear_tags(self) -> None:
        """Remove all tags and embeddings."""
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
            "ORDER BY e.image_id LIMIT ?",
            (model, after_id, limit),
        )

    def list_fingerprints(self) -> list[sqlite3.Row]:
        return self._query("SELECT path, size, mtime_ns FROM images")

    def requeue_faces_without_embeddings(self) -> int:
        """Reset status to 'pending' on done photos that have faces without embeddings."""
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
