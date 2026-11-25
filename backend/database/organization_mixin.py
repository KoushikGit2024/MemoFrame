"""Database mixin for duplicate clusters, image groupings, and facial lookups."""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Mapping, Sequence


class OrganizationDbMixin:
    """Methods for duplicates, groups, and photo lookups."""

    def fetch_hash_records(self) -> list[sqlite3.Row]:
        """``id, sha256, phash, dhash`` of every successfully processed image."""
        return self._query(
            "SELECT id, sha256, phash, dhash FROM images WHERE status = 'done' AND state != 'missing' AND kind = 'photo' ORDER BY id"
        )

    def replace_duplicates(self, rows: Iterable[tuple[int, int, str]]) -> int:
        """Replace all duplicate data with ``(image_id, cluster_id, kind)`` rows."""
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
        """Replace all groups."""
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

    def get_image(self, image_id: int) -> sqlite3.Row | None:
        """One image row, or None."""
        rows = self._query("SELECT * FROM images WHERE id = ?", (image_id,))
        return rows[0] if rows else None

    def get_faces(self, image_id: int) -> list[sqlite3.Row]:
        """Face boxes for one image, with the owning person's name."""
        return self._query(
            "SELECT f.*, p.name AS person_name FROM faces f "
            "LEFT JOIN persons p ON p.id = f.person_id "
            "WHERE f.image_id = ? ORDER BY f.id", (image_id,))

    def faces_for_images(self, image_ids: Iterable[int],
                         chunk_size: int = 500) -> dict[int, list[sqlite3.Row]]:
        """Faces of many images in a few queries (no embeddings)."""
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
        """Search processed images."""
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
