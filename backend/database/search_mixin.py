"""Database mixin for advanced search, timeline, and saved searches."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Mapping


def fts_query(text: str) -> str:
    """Safe FTS5 query: every word becomes a quoted prefix term, all must match."""
    return " ".join(f'"{t}"*' for t in re.findall(r"[^\W_]+", text))


FIND_FILTERS = frozenset(
    {
        "text",
        "min_faces",
        "max_faces",
        "taken_from",
        "taken_until",
        "group_id",
        "path_contains",
        "place_contains",
        "content_type",
        "kind",
        "format",
        "min_quality",
        "burst_id",
        "in_burst",
        "unassigned_faces",
        "duplicate",
        "mark",
        "no_mark",
        "include_missing",
        "include_live_video",
        "include_hidden",
        "tag",
        "person_id",
        "person_ids",
        "only_selected_persons",
        "any_selected_persons",
    }
)
MARK_KINDS = ("keep", "reviewed", "favourite", "hidden")
_EFF = "COALESCE(o.exif_ts, i.exif_ts)"  # date overrides apply
_SORTS = {
    "date": f"{_EFF} IS NULL, {_EFF}, i.id",
    "date_desc": f"{_EFF} IS NULL, {_EFF} DESC, i.id DESC",
    "quality": "i.quality IS NULL, i.quality DESC, i.id",
    "path": "i.path COLLATE NOCASE, i.id",
    "path_desc": "i.path COLLATE NOCASE DESC, i.id DESC",
    "size": "i.size DESC, i.id",
    "size_asc": "i.size ASC, i.id",
    "faces": "i.face_count DESC, i.id",
}


class SearchDbMixin:
    """Methods for finding images, counting, timeline, and saved searches."""

    _FROM = " FROM images i LEFT JOIN date_overrides o ON o.image_id = i.id"

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
            add(
                "EXISTS (SELECT 1 FROM tags t WHERE t.image_id = i.id AND t.label = ? COLLATE NOCASE)",
                f["tag"],
            )
        if f.get("min_quality") is not None:
            add("i.quality >= ?", f["min_quality"])
        if f.get("burst_id") is not None:
            add("i.burst_id = ?", f["burst_id"])
        if f.get("person_id") is not None:
            add(
                "EXISTS (SELECT 1 FROM faces fc WHERE fc.image_id = i.id AND fc.person_id = ? AND fc.ignored = 0)",
                f["person_id"],
            )
        if f.get("person_ids"):
            pids_list = [int(pid) for pid in f["person_ids"]]
            if f.get("any_selected_persons"):
                marks = ",".join("?" for _ in pids_list)
                add(
                    f"EXISTS (SELECT 1 FROM faces fc WHERE fc.image_id = i.id AND fc.person_id IN ({marks}) AND fc.ignored = 0)",
                    *pids_list,
                )
            else:
                for pid in pids_list:
                    add(
                        "EXISTS (SELECT 1 FROM faces fc WHERE fc.image_id = i.id AND fc.person_id = ? AND fc.ignored = 0)",
                        pid,
                    )
        if f.get("only_selected_persons"):
            pids = [int(pid) for pid in (f.get("person_ids") or [])]
            if f.get("person_id") is not None:
                pids.append(int(f["person_id"]))
            if pids:
                marks = ",".join("?" for _ in pids)
                add(
                    "NOT EXISTS (SELECT 1 FROM faces fc WHERE fc.image_id = i.id "
                    "AND fc.ignored = 0 "
                    "AND NOT (fc.person_id IS NULL AND fc.locked = 1) "
                    f"AND (fc.person_id IS NULL OR fc.person_id NOT IN ({marks})))",
                    *pids,
                )
        if f.get("unassigned_faces"):
            add(
                "EXISTS (SELECT 1 FROM faces fc WHERE fc.image_id = i.id AND fc.person_id IS NULL AND fc.locked = 0 AND fc.ignored = 0)"
            )
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
            add(
                "NOT EXISTS (SELECT 1 FROM marks m WHERE m.image_id = i.id AND m.kind = ?)",
                f["no_mark"],
            )
        return " WHERE " + " AND ".join(c), p

    def find_images(
        self, *, sort: str = "date", limit: int = 100, offset: int = 0, **filters: Any
    ) -> list[sqlite3.Row]:
        """Search with any combination of FIND_FILTERS."""
        if sort not in _SORTS:
            raise ValueError(f"sort must be one of: {', '.join(_SORTS)}")
        where, params = self._find_where(filters)
        return self._query(
            f"SELECT i.*, {_EFF} AS effective_ts, "
            "EXISTS (SELECT 1 FROM marks m WHERE m.image_id = i.id AND m.kind = 'favourite') AS is_favourite"
            f"{self._FROM}{where} "
            f"ORDER BY {_SORTS[sort]} LIMIT ? OFFSET ?",
            (*params, int(limit), int(offset)),
        )

    def count_images(self, **filters: Any) -> int:
        where, params = self._find_where(filters)
        return self._scalar(f"SELECT COUNT(*){self._FROM}{where}", params)

    def timeline(self, granularity: str = "month") -> list[dict[str, Any]]:
        """Photos per period, by effective date."""
        widths = {"year": 4, "month": 7, "day": 10}
        if granularity not in widths:
            raise ValueError("granularity must be year, month or day")
        rows = self._query(
            f"SELECT substr({_EFF}, 1, {widths[granularity]}) AS period, COUNT(*) AS n"
            f"{self._FROM} WHERE i.status = 'done' AND i.state != 'missing' AND i.pair_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM marks h WHERE h.image_id = i.id AND h.kind = 'hidden') "
            "GROUP BY period ORDER BY period IS NULL, period"
        )
        return [{"period": r["period"], "count": int(r["n"])} for r in rows]

    def save_search(self, name: str, filters: Mapping[str, Any]) -> None:
        """Store filters under name."""
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
                (name, json.dumps(dict(filters), sort_keys=True)),
            )

    def list_saved_searches(self) -> list[dict[str, Any]]:
        return [
            {"name": r["name"], "filters": json.loads(r["filters"])}
            for r in self._query("SELECT name, filters FROM saved_searches ORDER BY name")
        ]

    def get_saved_search(self, name: str) -> dict[str, Any] | None:
        rows = self._query("SELECT filters FROM saved_searches WHERE name = ?", (name,))
        return json.loads(rows[0]["filters"]) if rows else None

    def delete_saved_search(self, name: str) -> bool:
        with self._tx() as conn:
            return conn.execute("DELETE FROM saved_searches WHERE name = ?", (name,)).rowcount > 0
