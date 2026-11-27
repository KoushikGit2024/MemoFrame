"""Database operations: registration, results, failures, search, duplicates, groups."""

from __future__ import annotations

import pytest

from memoframe_engine.db import STATUS_DONE, STATUS_FAILED, STATUS_PENDING, DatabaseManager, ScanStats


def _face(x=1, y=1, w=5, h=5, c=0.9):
    return {"x": x, "y": y, "w": w, "h": h, "confidence": c}


def test_register_new_changed_unchanged(db):
    assert db.register_files([("a.jpg", 10, 1), ("b.jpg", 20, 2)]) == ScanStats(2, 0, 0)
    stats = db.register_files([("a.jpg", 10, 1), ("b.jpg", 21, 2), ("c.jpg", 5, 5)])
    assert (stats.new, stats.changed, stats.unchanged) == (1, 1, 1)
    assert db.report_stats()["total_images"] == 3


def test_changed_file_is_reset_to_pending(db):
    db.register_files([("a.jpg", 10, 1)])
    db.save_results([{"image_id": 1, "width": 9, "height": 9, "faces": [_face(), _face(x=20)]}])
    assert db.count_pending() == 0
    db.register_files([("a.jpg", 99, 1)])
    row = db.get_image(1)
    assert row["status"] == STATUS_PENDING and row["face_count"] == 0 and row["width"] is None
    assert db.get_faces(1) == []


def test_unchanged_file_keeps_results(db):
    db.register_files([("a.jpg", 10, 1)])
    db.save_results([{"image_id": 1, "faces": [_face()]}])
    db.register_files([("a.jpg", 10, 1)])
    assert db.get_image(1)["status"] == STATUS_DONE
    assert len(db.get_faces(1)) == 1


def test_save_results_labels_and_counts(db):
    db.register_files([("a.jpg", 10, 1), ("b.jpg", 10, 2)])
    db.save_results(
        [
            {
                "image_id": 1,
                "width": 100,
                "height": 50,
                "sha256": "s",
                "phash": "0" * 16,
                "exif_ts": "2024-06-01T10:00:00",
                "ts_source": "exif_original",
                "faces": [_face(), _face(x=30, c=0.8)],
            }
        ]
    )
    img = db.get_image(1)
    assert (img["status"], img["face_count"], img["width"]) == (STATUS_DONE, 2, 100)
    assert [f["label"] for f in db.get_faces(1)] == ["Face 001", "Face 002"]
    assert [r["id"] for r in db.fetch_pending(10)] == [2]


def test_save_results_is_atomic(db):
    db.register_files([("a.jpg", 1, 1), ("b.jpg", 1, 2)])
    with pytest.raises(KeyError):
        db.save_results(
            [{"image_id": 1, "faces": [_face()]}, {"image_id": 2, "faces": [{"y": 1}]}]
        )  # missing keys
    assert db.count_pending() == 2
    assert db.report_stats()["total_faces"] == 0


def test_failures_and_retry(db):
    db.register_files([("a.jpg", 1, 1), ("b.jpg", 1, 2)])
    db.save_failures([(1, "corrupt " + "x" * 1000)])
    assert db.get_image(1)["status"] == STATUS_FAILED
    assert len(db.get_image(1)["error"]) <= 500
    assert [r["id"] for r in db.fetch_pending(10)] == [2]
    assert [r["id"] for r in db.fetch_pending(10, include_failed=True)] == [1, 2]
    assert db.retry_failed() == 1
    assert db.count_pending() == 2


def test_fetch_pending_respects_limit(db):
    db.register_files([(f"{i}.jpg", 1, i) for i in range(5)])
    assert len(db.fetch_pending(3)) == 3


def test_search_filters(db):
    db.register_files([("/p/a_b.jpg", 1, 1), ("/p/aXb.jpg", 1, 2), ("/p/c.jpg", 1, 3)])
    db.save_results(
        [
            {"image_id": 1, "exif_ts": "2024-06-01T10:00:00", "faces": [_face(), _face(x=9)]},
            {"image_id": 2, "exif_ts": "2024-06-02T10:00:00", "faces": []},
            {"image_id": 3, "exif_ts": "2024-07-01T10:00:00", "faces": [_face()]},
        ]
    )
    ids = lambda **kw: [r["id"] for r in db.search_images(**kw)]
    assert ids(min_faces=2) == [1]
    assert ids(max_faces=0) == [2]
    assert ids(taken_from="2024-06-02", taken_until="2024-06-30") == [2]
    assert ids(taken_until="2024-06-01") == [1]  # date-only 'until' includes that day
    assert ids(path_contains="_") == [1]  # underscore is literal, not a wildcard
    assert ids(limit=2) == [1, 2]


def test_duplicates_roundtrip_and_stats(db):
    db.register_files([(f"{i}.jpg", 1, i) for i in range(1, 5)])
    db.save_results([{"image_id": i, "width": 10, "height": 10} for i in range(1, 5)])
    assert db.replace_duplicates([(1, 1, "exact"), (2, 1, "exact"), (3, 1, "exact")]) == 3
    stats = db.report_stats()
    assert (stats["duplicate_clusters"], stats["duplicate_images"]) == (1, 2)
    assert [m["id"] for m in db.get_duplicate_clusters()[1]] == [1, 2, 3]
    db.replace_duplicates([])
    assert db.report_stats()["duplicate_clusters"] == 0


def test_groups_replace_and_assign(db):
    db.register_files([(f"{i}.jpg", 1, i) for i in range(1, 4)])
    db.save_results([{"image_id": i, "exif_ts": f"2024-06-0{i}T10:00:00"} for i in range(1, 4)])
    db.replace_groups(
        [
            {"kind": "event", "name": "E1", "image_ids": [1, 2]},
            {"kind": "visual", "name": "V1", "image_ids": [3]},
        ]
    )
    groups = db.get_groups()
    assert [g["image_count"] for g in groups] == [2, 1]
    assert db.get_image(3)["group_id"] == groups[1]["id"]
    assert [r["id"] for r in db.get_group_images(groups[0]["id"])] == [1, 2]
    db.replace_groups([{"kind": "event", "name": "only", "image_ids": [1]}])
    assert db.report_stats()["groups"] == 1
    assert db.get_image(2)["group_id"] is None


def test_report_stats_counts_faces(db):
    db.register_files([("a.jpg", 1, 1), ("b.jpg", 1, 2), ("c.jpg", 1, 3), ("d.jpg", 1, 4)])
    db.save_results(
        [
            {"image_id": 1, "faces": []},
            {"image_id": 2, "faces": [_face()]},
            {"image_id": 3, "faces": [_face(), _face(x=9), _face(x=20)]},
        ]
    )
    db.save_failures([(4, "bad")])
    s = db.report_stats()
    assert (s["total_images"], s["processed"], s["failed"], s["pending"]) == (4, 3, 1, 0)
    assert (s["total_faces"], s["images_with_faces"], s["multi_face_images"]) == (4, 2, 1)


def test_reset_clears_everything(db):
    db.register_files([("a.jpg", 1, 1)])
    db.save_results([{"image_id": 1, "faces": [_face()]}])
    db.reset()
    s = db.report_stats()
    assert all(v == 0 for v in s.values())


def test_persists_across_connections(tmp_path):
    path = tmp_path / "sub" / "photos.db"
    with DatabaseManager(path) as first:
        first.register_files([("a.jpg", 1, 1)])
    with DatabaseManager(path) as second:
        assert second.report_stats()["total_images"] == 1
