"""Phase D: quality, dHash, content type, dates, bursts, refinement, places, tiling, migration."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter

from memoframe.core.analysis import classify_content, compute_dhash, date_flag, quality_metrics
from memoframe.core.duplicate_detector import choose_keeper, find_duplicates
from memoframe.core.face_detector import FaceDetector, merge_faces
from memoframe.core.geo import PlaceIndex, load_place_index
from memoframe.core.image_loader import LoadedImage, load_image
from memoframe.core.image_similarity import hamming
from memoframe.core.models import FaceBox
from memoframe.database import DatabaseManager
from memoframe.database.migrations import MIGRATIONS
from memoframe.processing import pipeline
from memoframe.processing.bursts import detect_bursts
from memoframe.processing.enrich import enrich_existing
from memoframe.processing.image_grouper import group_images, name_groups, refine_events
from memoframe.processing.pipeline import process_pending, scan_directory, update_bursts, update_places


def checker(size=(800, 600), cell=20) -> Image.Image:
    a = np.indices((size[1], size[0])).sum(axis=0) // cell % 2 * 255
    return Image.fromarray(a.astype(np.uint8)).convert("RGB")


# ---- quality / hashes --------------------------------------------------------------
def test_sharp_beats_blurred_and_black():
    sharp = checker()
    assert quality_metrics(sharp, 480000)["quality"] > quality_metrics(
        sharp.filter(ImageFilter.GaussianBlur(10)), 480000)["quality"]
    assert quality_metrics(Image.new("RGB", (800, 600), "black"), 480000)["quality"] < 30


def test_dhash_stable_under_resize_and_differs_between_images(tmp_path, make_image):
    a = Image.open(make_image(tmp_path / "a.png", 1, (800, 600)))
    b = a.resize((400, 300))
    c = Image.open(make_image(tmp_path / "c.png", 2, (800, 600)))
    assert hamming(compute_dhash(a), compute_dhash(b)) <= 6
    assert hamming(compute_dhash(a), compute_dhash(c)) > 10


# ---- content type / dates ----------------------------------------------------------
def _loaded(path):
    return load_image(path, 1280)


def test_content_types(tmp_path, make_image):
    Image.new("RGB", (1080, 2340), (20, 80, 200)).save(tmp_path / "ui.png")
    Image.new("RGB", (1000, 1400), "white").save(tmp_path / "scan.png")
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    Image.new("RGB", (800, 600), (20, 80, 200)).save(tmp_path / "cam.jpg", exif=exif)
    photo = make_image(tmp_path / "noise.jpg", 3, (800, 600))
    assert classify_content(_loaded(tmp_path / "ui.png"), "ui.png") == "screenshot"
    assert classify_content(_loaded(tmp_path / "scan.png"), "scan.png") == "document"
    assert classify_content(_loaded(tmp_path / "cam.jpg"), "cam.jpg") == "photo"      # camera EXIF wins
    assert classify_content(_loaded(photo), "noise.jpg") == "photo"
    assert classify_content(_loaded(photo), "Screenshot_2024.jpg") == "screenshot"


def test_date_flags():
    now = datetime(2026, 6, 1)
    assert date_flag(None, "none", now) == "none"
    assert date_flag("2030-01-01T00:00:00", "exif_original", now) == "future"
    assert date_flag("1970-01-01T00:00:00", "exif_original", now) == "implausible"
    assert date_flag("2024-06-01T10:00:00", "file_mtime", now) == "mtime_only"
    assert date_flag("2024-06-01T10:00:00", "exif_original", now) is None


# ---- duplicates with dHash vote and quality keeper ----------------------------------
def test_dhash_vetoes_flat_phash_match():
    same = "0123456789abcdef"
    rows = [(1, "a", same, "0" * 16), (2, "b", same, "f" * 16)]
    assert find_duplicates(rows, 6, 12) == []
    assert find_duplicates(rows, 6, 64) != []
    assert find_duplicates(rows) != []
    assert find_duplicates([(1, "a", same), (2, "b", same)], 6, 12) != []     # no dHash: no veto


def test_keeper_prefers_quality():
    members = [{"id": 1, "width": 4000, "height": 3000, "size": 9, "quality": 40.0},
               {"id": 2, "width": 2000, "height": 1500, "size": 5, "quality": 80.0}]
    assert choose_keeper(members) == 2


# ---- bursts -------------------------------------------------------------------------
def _b(i, ts, ph="0123456789abcdef", q=None):
    return {"id": i, "exif_ts": ts, "phash": ph, "quality": q}


def test_burst_detection_and_best_frame():
    rows = [_b(1, "2024-06-01T10:00:00", q=50), _b(2, "2024-06-01T10:00:01", q=90),
            _b(3, "2024-06-01T10:00:01", q=70), _b(4, "2024-06-01T10:05:00"),
            _b(5, "2024-06-01T10:05:01", ph="ffffffffffffffff"), _b(6, "2024-06-01T10:05:02")]
    bursts = detect_bursts(rows, gap_seconds=2, hash_threshold=14, min_size=3)
    assert bursts == [{"image_ids": [1, 2, 3], "best_id": 2}]


def test_bursts_in_database_and_stage_skips_when_unchanged(db, settings):
    db.register_files([(f"{i}.jpg", 1, i) for i in range(1, 5)])
    db.save_results([{"image_id": i, "phash": "0123456789abcdef", "quality": 10.0 * i,
                      "exif_ts": f"2024-06-01T10:00:0{i}", "ts_source": "exif_original"}
                     for i in range(1, 5)])
    assert update_bursts(settings, db) == 1
    burst = db.get_bursts()[0]
    assert (burst["best_image_id"], burst["image_count"]) == (4, 4)
    assert [r["id"] for r in db.get_burst_images(burst["id"])] == [1, 2, 3, 4]
    assert update_bursts(settings, db) == 1
    assert db.search_images(burst_id=burst["id"], limit=10)[0]["id"] == 1


# ---- refinement and naming ----------------------------------------------------------
def _row(i, ts, **kw):
    return {"id": i, "exif_ts": ts, "ts_source": "exif_original", "gps_lat": kw.get("lat"),
            "gps_lon": kw.get("lon"), "features": None}


def test_tiny_event_merges_into_neighbour_and_long_event_splits():
    rows = [_row(i, f"2024-06-01T10:{i:02d}:00") for i in range(5)]
    rows += [_row(10, "2024-06-01T15:00:00")]                         # alone, 5h after the last
    groups = group_images(rows, event_gap_hours=3, gps_split_km=0)
    assert len(groups) == 2
    times = {r["id"]: datetime.strptime(r["exif_ts"], "%Y-%m-%dT%H:%M:%S") for r in rows}
    merged = refine_events(groups, times, min_size=3, merge_gap_hours=6, max_hours=36)
    assert [g["image_ids"] for g in merged] == [[0, 1, 2, 3, 4, 10]]

    long_rows = [_row(1, "2024-06-01T00:00:00"), _row(2, "2024-06-01T02:00:00"),
                 _row(3, "2024-06-02T20:00:00"), _row(4, "2024-06-02T22:00:00")]
    long_groups = group_images(long_rows, event_gap_hours=45, gps_split_km=0)
    assert len(long_groups) == 1
    times = {r["id"]: datetime.strptime(r["exif_ts"], "%Y-%m-%dT%H:%M:%S") for r in long_rows}
    split = refine_events(long_groups, times, min_size=1, merge_gap_hours=0, max_hours=36)
    assert [g["image_ids"] for g in split] == [[1, 2], [3, 4]]


def test_name_groups_uses_majority_place():
    groups = [{"kind": "event", "name": "Event 2024-06-01 10:00", "start_ts": "2024-06-01T10:00:00",
               "end_ts": "2024-06-01T11:00:00", "image_ids": [1, 2, 3]}]
    name_groups(groups, {1: "Imphal, IN", 2: "Imphal, IN", 3: ""})
    assert groups[0]["name"] == "Imphal, IN, 01 Jun 2024"


# ---- places -------------------------------------------------------------------------
def test_builtin_and_file_place_index(tmp_path):
    pts = np.array([[24.82, 93.94], [0.0, -30.0]])
    assert PlaceIndex.builtin().lookup_many(pts, 50) == ["Imphal, IN", None]
    line = "\t".join(["1", "Testville", "Testville", "", "10.0", "20.0", "P", "PPL", "XX"] + [""] * 6)
    (tmp_path / "cities15000.txt").write_text(line + "\n", encoding="utf-8")
    assert load_place_index(tmp_path).lookup_many(np.array([[10.01, 20.01]]), 50) == ["Testville, XX"]


def test_update_places_marks_unmatched_and_does_not_retry(db, settings):
    db.register_files([("a.jpg", 1, 1), ("b.jpg", 1, 2), ("c.jpg", 1, 3)])
    db.save_results([{"image_id": 1, "gps_lat": 24.817, "gps_lon": 93.937},
                     {"image_id": 2, "gps_lat": 0.5, "gps_lon": -30.0}, {"image_id": 3}])
    assert update_places(settings, db) == 1
    assert (db.get_image(1)["place"], db.get_image(2)["place"], db.get_image(3)["place"]) == (
        "Imphal, IN", "", None)
    assert update_places(settings, db) == 0


# ---- tiled detection ------------------------------------------------------------------
class SquareFinder(FaceDetector):
    name = "squares"

    def __init__(self):
        super().__init__(0.7, 20)

    def _detect_bgr(self, bgr):
        ys, xs = np.nonzero(bgr[:, :, 0] == 255)
        if len(xs) < 500:
            return []
        return [(float(xs.min()), float(ys.min()), float(xs.max() - xs.min() + 1),
                 float(ys.max() - ys.min() + 1), 0.9)]


def test_tiled_detection_maps_back_and_merges_duplicates():
    arr = np.zeros((1600, 2400, 3), dtype=np.uint8)
    arr[900:960, 1500:1560] = 255
    big = LoadedImage(pil=Image.fromarray(arr), width=2400, height=1600, scale=1.0, exif=Image.Exif())
    faces = SquareFinder().detect_tiled(big, tile=960)
    assert [(f.x, f.y, f.w, f.h) for f in faces] == [(1500, 900, 60, 60)]


def test_merge_faces_keeps_higher_confidence():
    kept = merge_faces([FaceBox(10, 10, 50, 50, 0.8), FaceBox(12, 12, 50, 50, 0.95),
                        FaceBox(300, 10, 50, 50, 0.9)])
    assert [(f.x, f.confidence) for f in kept] == [(12, 0.95), (300, 0.9)]


# ---- pipeline, enrich, overrides, review -----------------------------------------------
class FakeDetector:
    def detect(self, loaded):
        return [FaceBox(10, 10, 40, 40, 0.9), FaceBox(100, 20, 40, 40, 0.75)]

    def close(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(pipeline, "create_detector", lambda s: FakeDetector())
    monkeypatch.setattr(pipeline, "ensure_model", lambda p: p)


def test_pipeline_stores_analysis_and_enrich_backfills(settings, tmp_path, make_image, fake):
    root = tmp_path / "p"
    for i in (1, 2, 3):
        make_image(root / f"p{i}.jpg", i)
    with DatabaseManager(settings.db_path) as db:
        scan_directory(settings, db, root)
        process_pending(settings, db, show_progress=False)
        row = db.search_images()[0]
        assert row["quality"] is not None and row["dhash"] and row["content_type"] == "photo"
        assert row["date_flag"] == "mtime_only"
        assert len(db.low_confidence_faces(0.8)) == 3

        db._db.execute("UPDATE images SET quality = NULL, dhash = NULL")
        (root / "p3.jpg").unlink()
        assert enrich_existing(settings, db) == 2                       # missing file is skipped
        assert db.count_unanalyzed() == 1


def test_date_override_changes_grouping_input(db):
    db.register_files([("a.jpg", 1, 1)])
    db.save_results([{"image_id": 1, "exif_ts": "2030-01-01T00:00:00", "ts_source": "exif_original",
                      "date_flag": "future"}])
    assert db.suspicious_dates()[0]["date_flag"] == "future"
    db.set_date_override(1, "2024-06-01T10:00:00", "camera clock was wrong")
    assert db.fetch_grouping_rows()[0]["exif_ts"] == "2024-06-01T10:00:00"
    assert db.clear_date_override(1) is True
    assert db.fetch_grouping_rows()[0]["exif_ts"] == "2030-01-01T00:00:00"


def test_screenshots_are_left_out_of_groups_by_default(db):
    db.register_files([("a.jpg", 1, 1), ("b.png", 1, 2)])
    db.save_results([{"image_id": 1, "exif_ts": "2024-06-01T10:00:00", "ts_source": "exif_original"},
                     {"image_id": 2, "exif_ts": "2024-06-01T10:01:00", "ts_source": "exif_original",
                      "content_type": "screenshot"}])
    assert [r["id"] for r in db.fetch_grouping_rows()] == [1]
    assert len(db.fetch_grouping_rows(include_junk=True)) == 2
    assert [r["id"] for r in db.search_images(content_type="screenshot")] == [2]


# ---- migration ---------------------------------------------------------------------------
def test_v4_database_upgrades_to_v5(tmp_path):
    path = tmp_path / "photos.db"
    conn = sqlite3.connect(path)
    for _, sql in MIGRATIONS[:4]:
        conn.executescript(sql(conn))
    conn.execute("PRAGMA user_version = 4")
    conn.execute("INSERT INTO images (path, size, mtime_ns) VALUES ('a.jpg', 1, 1)")
    conn.commit()
    conn.close()
    with DatabaseManager(path) as db:
        row = db.get_image(1)
        assert (row["content_type"], row["quality"], row["place"], row["burst_id"]) == ("photo", None, None, None)
        assert db.get_bursts() == []
    assert (tmp_path / "photos.db.bak-v4").is_file()
