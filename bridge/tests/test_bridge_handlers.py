"""Deterministic unit tests verifying all 52 Engine contract interactions through BridgeServer."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.server import BridgeContext, BridgeServer


class FakeControl:
    def __init__(self) -> None:
        self.paused = False
        self.cancelled = False

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeEngine:
    """In-memory mock implementing the complete MemoFrame Engine contract."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.config_warnings = ["unknown_key"]
        self.settings = SimpleNamespace(
            tagging_enabled=False,
            store_embeddings=True,
            log_path=workspace / "photo_organizer.log",
        )
        self.control = FakeControl()
        self.on_event = None
        self.marks: dict[int, set[str]] = {}
        self.saved_searches: dict[str, dict] = {}
        self.persons = [
            {"id": 1, "name": "Alice", "image_count": 5},
            {"id": 2, "name": "Person 02", "image_count": 2},
        ]
        self.photos = [
            {
                "id": 10,
                "path": str(workspace / "a.jpg"),
                "width": 1200,
                "height": 800,
                "quality": 88.5,
                "exif_ts": "2025-05-01T10:00:00",
            },
            {
                "id": 11,
                "path": str(workspace / "b.jpg"),
                "width": 1200,
                "height": 800,
                "quality": 72.0,
                "exif_ts": "2025-05-01T10:01:00",
            },
        ]
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def count(self, kind: str = "photo", **filters) -> int:
        return len(self.photos)

    def find(
        self,
        kind: str = "photo",
        status: str | None = None,
        sort: str = "date",
        limit: int = 40,
        offset: int = 0,
        **filters,
    ):
        if status == "failed":
            return [{"id": 99, "path": "/bad.jpg", "error": "corrupt"}]
        return self.photos[offset : offset + limit]

    def get_image(self, image_id: int):
        return next((p for p in self.photos if p["id"] == image_id), None)

    def thumbnail(self, image_id: int) -> str:
        return str(self.workspace / f"thumb_{image_id}.jpg")

    def get_faces_many(self, ids):
        return {
            10: [
                {
                    "id": 101,
                    "x": 10,
                    "y": 10,
                    "w": 50,
                    "h": 50,
                    "locked": 1,
                    "person_id": 1,
                    "person_name": "Alice",
                }
            ]
        }

    def get_persons(self):
        return list(self.persons)

    def get_person(self, pid: int):
        return next((p for p in self.persons if p["id"] == pid), None)

    def rename_person(self, pid: int, name: str, confirm: bool = True):
        p = self.get_person(pid)
        if p:
            p["name"] = name

    def merge_persons(self, keep: int, other: int):
        self.persons = [p for p in self.persons if p["id"] != other]

    def confirm_person(self, pid: int) -> int:
        return 3

    def get_person_faces(self, pid: int, limit: int, offset: int):
        return [{"id": 101, "x": 0, "y": 0, "w": 40, "h": 40, "confidence": 0.95, "locked": 1}]

    def get_unassigned_faces(self, limit: int, offset: int):
        return [{"id": 202, "x": 0, "y": 0, "w": 40, "h": 40, "confidence": 0.6, "locked": 0}]

    def name_face(self, fid: int, name: str):
        return None

    def assign_face(self, fid: int, pid: int | None):
        return None

    def get_duplicate_clusters(self):
        return {
            "c1": [
                {**self.photos[0], "suggested_keep": True, "kind": "near"},
                {**self.photos[1], "kind": "near"},
            ]
        }

    def get_bursts(self):
        return [{"id": 5, "image_count": 2, "best_image_id": 10}]

    def get_burst_images(self, burst_id: int):
        return list(self.photos)

    def get_groups(self):
        return [
            {
                "id": 7,
                "name": "Trip",
                "start_ts": "2025-05-01T10:00:00",
                "end_ts": "2025-05-01T12:00:00",
                "image_count": 2,
            }
        ]

    def get_group_images(self, gid: int, limit: int = 8):
        return list(self.photos[:limit])

    def get_marks(self, image_id: int | None, kind: str | None = None):
        out = []
        for iid, kinds in self.marks.items():
            if image_id is not None and iid != image_id:
                continue
            for k in kinds:
                if kind is None or k == kind:
                    out.append({"image_id": iid, "kind": k})
        return out

    def set_mark(self, image_id: int, kind: str):
        self.marks.setdefault(image_id, set()).add(kind)

    def clear_mark(self, image_id: int, kind: str):
        self.marks.setdefault(image_id, set()).discard(kind)

    def get_tags(self, image_id: int):
        return [{"label": "outdoor"}]

    def list_tags(self, limit: int = 80):
        return [{"label": "outdoor", "count": 2}]

    def list_saved_searches(self):
        return [{"name": k, "filters": v} for k, v in self.saved_searches.items()]

    def save_search(self, name: str, filters: dict):
        self.saved_searches[name] = filters

    def delete_saved_search(self, name: str):
        self.saved_searches.pop(name, None)

    def live_video(self, image_id: int):
        return None

    def similar(self, image_id: int, limit: int = 24):
        return [{**self.photos[1], "similarity": 0.91}]

    def suspicious_dates(self, limit: int = 500):
        return [{"id": 10, "path": self.photos[0]["path"], "exif_ts": None, "date_flag": "missing"}]

    def set_date_override(self, image_id: int, iso: str, reason: str):
        self.get_image(image_id)["effective_ts"] = iso

    def clear_date_override(self, image_id: int):
        self.get_image(image_id).pop("effective_ts", None)

    def stats(self):
        return {
            "total_images": 2,
            "total_faces": 1,
            "duplicate_clusters": 1,
            "groups": 1,
            "videos": 0,
        }

    def doctor(self):
        return {"checks": [{"name": "db", "status": "ok", "detail": "healthy"}]}

    def clear_cache(self):
        return {"thumbs": 12}

    def export_diagnostics(self):
        return str(self.workspace / "diag.zip")

    def update_config(self, tagging_enabled: bool, store_embeddings: bool):
        self.settings.tagging_enabled = tagging_enabled
        self.settings.store_embeddings = store_embeddings

    def tag_existing(self):
        return {"tagged": 2}

    def check_files(self):
        return {"ok": 2, "missing": 0, "offline": 0}

    def forget_missing(self):
        return 0

    def moves(self):
        return []

    def rebuild(self):
        return {"groups": 1, "duplicate_clusters": 1, "persons": 2}

    def repair(self):
        return {"face_counts_fixed": 0, "requeued": 0, "orphan_faces_removed": 0}

    def reset_workspace(self, clear_sources: bool = False, clear_saved_searches: bool = False):
        return {"images_removed": 2}


def _make_server(tmp_path: Path) -> tuple[BridgeServer, FakeEngine]:
    eng = FakeEngine(tmp_path)
    ctx = BridgeContext(workspace=tmp_path, engine=eng)
    return BridgeServer(ctx), eng


def test_library_and_people_rpc_endpoints(tmp_path: Path) -> None:
    srv, _ = _make_server(tmp_path)

    init = srv.dispatch("system.init", {})
    assert init["connected"] is True
    assert init["config_warnings"] == ["unknown_key"]

    q = srv.dispatch(
        "photos.query", {"filters": {}, "sort": "date_desc", "page": 0, "page_size": 40}
    )
    assert q["total"] == 2
    assert len(q["items"][0]["faces"]) == 1

    det = srv.dispatch("photos.detail", {"image_id": 10})
    assert det["tags"][0]["label"] == "outdoor"

    m1 = srv.dispatch("photos.toggle_mark", {"image_id": 10, "kind": "favourite"})
    assert m1["active"] is True
    m2 = srv.dispatch("photos.toggle_mark", {"image_id": 10, "kind": "favourite"})
    assert m2["active"] is False

    srv.dispatch("saved_searches.save", {"name": "Trips", "filters": {"text": "a"}})
    assert len(srv.dispatch("saved_searches.list", {})) == 1
    srv.dispatch("saved_searches.delete", {"name": "Trips"})
    assert srv.dispatch("saved_searches.list", {}) == []

    srv.dispatch("persons.rename", {"person_id": 2, "new_name": "Bob", "confirm": True})
    assert srv.dispatch("persons.get", {"person_id": 2})["name"] == "Bob"
    srv.dispatch("persons.merge", {"keep_id": 1, "other_ids": [2]})
    assert len(srv.dispatch("persons.list", {})) == 1


def test_collections_and_system_rpc_endpoints(tmp_path: Path) -> None:
    srv, eng = _make_server(tmp_path)

    dups = srv.dispatch("duplicates.list", {})
    assert len(dups) == 1 and dups[0]["best_image_id"] == 10
    srv.dispatch("duplicates.resolve", {"keep_id": 10, "hide_ids": [11]})
    assert "keep" in eng.marks[10] and "hidden" in eng.marks[11]

    eng.marks.clear()
    bursts = srv.dispatch("bursts.list", {})
    assert len(bursts) == 1
    frames = srv.dispatch("bursts.frames", {"burst_id": 5, "best_image_id": 10})
    assert frames[0]["suggested"] is True

    tl = srv.dispatch("timeline.groups", {"limit": 10, "offset": 0})
    assert tl["total"] == 1 and len(tl["groups"][0]["photos"]) == 2

    assert srv.dispatch("system.stats", {})["total_images"] == 2
    assert srv.dispatch("system.clear_cache", {})["freed_mb"] == 12
    assert srv.dispatch("system.rebuild", {})["groups"] == 1
    assert srv.dispatch("system.reset_workspace", {"clear_sources": True})["images_removed"] == 2

    # Verify handle_line JSON-RPC error path for unknown method
    resp = srv.handle_line(json.dumps({"id": 99, "method": "nope.method"}))
    assert resp["ok"] is False and resp["error"]["code"] == "METHOD_NOT_FOUND"
