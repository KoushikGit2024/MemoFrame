"""Database mixin for persons and face clustering persistence."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from typing import Sequence


class PersonDbMixin:
    """Methods for person clusters, face assignments, and locks."""

    def fetch_faces_with_embeddings(self) -> list[sqlite3.Row]:
        """Faces with an embedding on photos that still exist (not missing / Live video)."""
        return self._query(
            "SELECT f.id, f.image_id, f.w, f.h, f.confidence, f.embedding, f.person_id, f.locked "
            "FROM faces f JOIN images i ON i.id = f.image_id "
            "WHERE f.embedding IS NOT NULL AND i.state != 'missing' AND i.pair_id IS NULL "
            "ORDER BY f.id"
        )

    @staticmethod
    def _refresh_person_stats(conn: sqlite3.Connection) -> None:
        """Recompute cover face and photo count; drop people that have no faces left."""
        conn.execute(
            "UPDATE persons SET "
            "cover_face_id = (SELECT f.id FROM faces f WHERE f.person_id = persons.id "
            "                 ORDER BY f.confidence * f.w * f.h DESC, f.id LIMIT 1), "
            "image_count = (SELECT COUNT(DISTINCT image_id) FROM faces "
            "               WHERE person_id = persons.id)"
        )
        conn.execute(
            "DELETE FROM persons WHERE NOT EXISTS "
            "(SELECT 1 FROM faces WHERE faces.person_id = persons.id)"
        )

    def replace_person_clusters(
        self,
        clusters: dict[int, list[int]],
        custom_names: dict[int, str] | None = None,
        fixed: dict[int, list[int]] | None = None,
    ) -> int:
        """Rebuild people from automatic clusters while honouring user decisions."""
        fixed = fixed or {}
        with self._tx() as conn:
            old_names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM persons")}
            anchored = {
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT person_id FROM faces WHERE locked = 1 AND person_id IS NOT NULL"
                )
            }
            old_of_face = {
                r["id"]: r["person_id"]
                for r in conn.execute(
                    "SELECT id, person_id FROM faces WHERE person_id IS NOT NULL AND locked = 0"
                )
            }
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
            conn.execute(
                "DELETE FROM persons WHERE id NOT IN "
                "(SELECT DISTINCT person_id FROM faces WHERE locked = 1 AND person_id IS NOT NULL)"
            )
            for pid, fids in fixed.items():
                if pid in anchored:
                    conn.executemany(
                        "UPDATE faces SET person_id = ? WHERE id = ? AND locked = 0",
                        [(pid, f) for f in fids],
                    )
            for key, fids in clusters.items():
                if not fids:
                    continue
                pid = assigned.get(key)
                if pid is None:
                    pid, next_id = next_id, next_id + 1
                name = (custom_names or {}).get(key) or old_names.get(pid) or f"Person {pid:02d}"
                conn.execute("INSERT INTO persons (id, name) VALUES (?, ?)", (pid, name))
                conn.executemany(
                    "UPDATE faces SET person_id = ? WHERE id = ?",
                    [(pid, f) for f in fids],
                )
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
            res = conn.execute(
                "UPDATE persons SET name = ? WHERE id = ?", (new_name.strip(), person_id)
            )
            self._bump_persons(conn)
            return res.rowcount > 0

    def assign_face(self, face_id: int, person_id: int | None) -> None:
        """Pin a face to a person, or to nobody (``None`` = 'not a person I care about')."""
        with self._tx() as conn:
            if conn.execute("SELECT 1 FROM faces WHERE id = ?", (face_id,)).fetchone() is None:
                raise ValueError(f"No face with id {face_id}.")
            if (
                person_id is not None
                and conn.execute("SELECT 1 FROM persons WHERE id = ?", (person_id,)).fetchone()
                is None
            ):
                raise ValueError(f"No person with id {person_id}.")
            conn.execute(
                "UPDATE faces SET person_id = ?, locked = 1 WHERE id = ?",
                (person_id, face_id),
            )
            self._refresh_person_stats(conn)
            self._bump_persons(conn)

    def create_person(self, name: str, face_ids: Sequence[int]) -> int:
        """New person from the given faces. Returns its id."""
        name, ids = name.strip(), sorted({int(i) for i in face_ids})
        if not name or not ids:
            raise ValueError("Give a name and at least one face.")
        with self._tx() as conn:
            found = conn.execute(
                f"SELECT COUNT(*) FROM faces WHERE id IN ({','.join('?' * len(ids))})", ids
            ).fetchone()[0]
            if found != len(ids):
                raise ValueError("One or more face ids do not exist.")
            pid = int(conn.execute("INSERT INTO persons (name) VALUES (?)", (name,)).lastrowid)
            conn.executemany(
                "UPDATE faces SET person_id = ?, locked = 1 WHERE id = ?",
                [(pid, i) for i in ids],
            )
            self._refresh_person_stats(conn)
            self._bump_persons(conn)
            return pid

    def merge_persons(self, keep_id: int, merge_id: int) -> None:
        """Move every face of ``merge_id`` into ``keep_id`` and lock them all."""
        if keep_id == merge_id:
            raise ValueError("Cannot merge a person into itself.")
        with self._tx() as conn:
            names = {
                r["id"]: r["name"]
                for r in conn.execute(
                    "SELECT id, name FROM persons WHERE id IN (?, ?)", (keep_id, merge_id)
                )
            }
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
        """Lock every face currently in the person. Returns count."""
        with self._tx() as conn:
            if conn.execute("SELECT 1 FROM persons WHERE id = ?", (person_id,)).fetchone() is None:
                raise ValueError(f"No person with id {person_id}.")
            n = conn.execute(
                "UPDATE faces SET locked = 1 WHERE person_id = ?", (person_id,)
            ).rowcount
            self._bump_persons(conn)
            return n

    def set_face_locked(self, face_id: int, locked: bool = True) -> bool:
        """Explicitly set the locked flag on a face."""
        with self._tx() as conn:
            changed = (
                conn.execute(
                    "UPDATE faces SET locked = ? WHERE id = ?",
                    (1 if locked else 0, face_id),
                ).rowcount
                > 0
            )
            if changed:
                self._bump_persons(conn)
            return changed

    def unlock_face(self, face_id: int) -> bool:
        """Hand a face back to automatic clustering."""
        with self._tx() as conn:
            changed = (
                conn.execute(
                    "UPDATE faces SET locked = 0 WHERE id = ? AND locked = 1",
                    (face_id,),
                ).rowcount
                > 0
            )
            if changed:
                self._bump_persons(conn)
            return changed

    def person_faces(self, person_id: int, limit: int = 200, offset: int = 0) -> list[sqlite3.Row]:
        """Face boxes of one person."""
        return self._query(
            "SELECT f.id, f.image_id, f.person_id, f.x, f.y, f.w, f.h, f.confidence, "
            "f.crop_path, f.locked, i.path FROM faces f JOIN images i ON i.id = f.image_id "
            "WHERE f.person_id = ? AND i.state != 'missing' "
            "ORDER BY f.confidence * f.w * f.h DESC, f.id LIMIT ? OFFSET ?",
            (person_id, limit, offset),
        )

    def unassigned_faces(self, limit: int = 200, offset: int = 0) -> list[sqlite3.Row]:
        """Faces not in any person."""
        return self._query(
            "SELECT f.id, f.image_id, f.person_id, f.x, f.y, f.w, f.h, f.confidence, "
            "f.crop_path, f.locked, i.path FROM faces f JOIN images i ON i.id = f.image_id "
            "WHERE f.person_id IS NULL AND i.state != 'missing' "
            "ORDER BY f.locked DESC, f.confidence * f.w * f.h DESC, f.id LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def get_person(self, person_id: int) -> sqlite3.Row | None:
        """Get one person row."""
        rows = self._query(
            "SELECT p.*, f.crop_path AS cover_crop_path, f.image_id AS cover_image_id "
            "FROM persons p "
            "LEFT JOIN faces f ON f.id = p.cover_face_id WHERE p.id = ?",
            (person_id,),
        )
        return rows[0] if rows else None
