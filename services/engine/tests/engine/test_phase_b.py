"""Phase B: single-read loader, states, rebuild skipping, cache, repair, backup, migration."""

from __future__ import annotations

import os
import sqlite3

import pytest

from memoframe_engine.domains.media.loader import ImageLoadError, load_image, load_image_bytes
from memoframe_engine.db import DatabaseManager
from memoframe_engine.db.migrations import MIGRATIONS
from memoframe_engine.domains.pipeline import orchestrator as pipeline
from memoframe_engine.domains.pipeline.maintenance import (
    clear_cache,
    enforce_cache_cap,
    forget_missing,
    get_thumbnail,
    refresh_states,
    run_maintenance,
)
from memoframe_engine.domains.pipeline.orchestrator import update_duplicates
from memoframe_engine.domains.media.thumbnails import shard_dir


def _face():
    return {"x": 1, "y": 1, "w": 5, "h": 5, "confidence": 0.9}


# ---- single-read loader ---------------------------------------------------------
def test_bytes_and_path_loading_agree(tmp_path, make_image):
    p = make_image(tmp_path / "a.jpg", size=(2000, 1500))
    a, b = load_image(p, 800), load_image_bytes(p.read_bytes(), p.name, 800)
    assert (a.width, a.height, a.pil.size) == (b.width, b.height, b.pil.size)
    assert list(a.pil.getdata())[:50] == list(b.pil.getdata())[:50]


def test_error_codes(tmp_path):
    with pytest.raises(ImageLoadError, match="FILE_MISSING"):
        load_image(tmp_path / "nope.jpg")
    with pytest.raises(ImageLoadError, match="CORRUPT_IMAGE"):
        load_image_bytes(b"garbage", "x.jpg")


# ---- states ---------------------------------------------------------------------
def test_offline_vs_missing_and_recovery(db, tmp_path, make_image):
    root = tmp_path / "drive"
    a, b = make_image(root / "a.jpg", 1), make_image(root / "b.jpg", 2)
    db.add_source(str(root))
    db.register_files([(str(a), 1, 1), (str(b), 1, 2)])
    db.save_results([{"image_id": 1}, {"image_id": 2}])

    b.unlink()
    assert refresh_states(db) == {"ok": 1, "offline": 0, "missing": 1}

    root.rename(tmp_path / "unplugged")  # simulate a disconnected drive
    assert refresh_states(db) == {"ok": 0, "offline": 2, "missing": 0}
    assert db.fetch_pending(10) == [] and db.count_pending() == 0

    (tmp_path / "unplugged").rename(root)  # reconnect
    assert refresh_states(db) == {"ok": 1, "offline": 0, "missing": 1}
    assert len(db.search_images()) == 1  # missing hidden by default
    assert len(db.search_images(include_missing=True)) == 2


def test_offline_pending_images_are_not_processed(db):
    db.register_files([("a.jpg", 1, 1)])
    db.set_states([(1, "offline")])
    assert db.fetch_pending(10) == []
    db.register_files([("a.jpg", 1, 1)])  # seen again by a scan
    assert [r["id"] for r in db.fetch_pending(10)] == [1]


def test_forget_missing_only_removes_missing(db, settings, tmp_path, make_image):
    root = tmp_path / "d"
    a, b = make_image(root / "a.jpg", 1), make_image(root / "b.jpg", 2)
    db.add_source(str(root))
    db.register_files([(str(a), 1, 1), (str(b), 1, 2)])
    db.save_results([{"image_id": 1, "faces": [_face()]}, {"image_id": 2, "faces": [_face()]}])
    b.unlink()
    refresh_states(db)
    assert forget_missing(settings, db) == 1
    assert db.get_image(2) is None and db.get_image(1) is not None
    assert a.exists()


# ---- rebuild skipping -------------------------------------------------------------
def test_unchanged_data_skips_rebuild(db, settings, monkeypatch):
    calls = []
    real = pipeline.find_duplicates
    monkeypatch.setattr(
        pipeline, "find_duplicates", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    db.register_files([("a.jpg", 1, 1), ("b.jpg", 1, 2)])
    db.save_results(
        [
            {"image_id": 1, "sha256": "x", "phash": "0" * 16},
            {"image_id": 2, "sha256": "x", "phash": "0" * 16},
        ]
    )
    assert update_duplicates(settings, db) == 1
    assert update_duplicates(settings, db) == 1 and len(calls) == 1  # skipped
    assert update_duplicates(settings, db, force=True) == 1 and len(calls) == 2
    db.register_files([("a.jpg", 9, 1)])  # file changed
    db.save_results([{"image_id": 1, "sha256": "y", "phash": "f" * 16}])
    assert update_duplicates(settings, db) == 0 and len(calls) == 3  # recomputed


# ---- cache ------------------------------------------------------------------------
def _fake_thumbs(settings, db, n=3):
    rows = []
    for i in range(1, n + 1):
        f = shard_dir(settings.thumbnails_dir, i) / f"{i:08d}_x.jpg"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * 600_000)
        os.utime(f, (i * 1000, i * 1000))
        rows.append({"image_id": i, "thumb_path": str(f)})
    db.register_files([(f"{i}.jpg", 1, i) for i in range(1, n + 1)])
    db.save_results(rows)


def test_cache_cap_removes_oldest_first(db, settings):
    _fake_thumbs(settings, db)
    assert enforce_cache_cap(settings, db, 1) == 2  # 1.8 MB -> under 1 MiB
    assert db.get_image(1)["thumb_path"] is None and db.get_image(2)["thumb_path"] is None
    assert db.get_image(3)["thumb_path"] is not None


def test_clear_cache(db, settings):
    _fake_thumbs(settings, db)
    assert clear_cache(settings, db)["thumbnails"] >= 1
    assert not any(settings.thumbnails_dir.rglob("*.jpg"))
    assert db.get_image(1)["thumb_path"] is None
    with pytest.raises(ValueError):
        clear_cache(settings, db, ["photos"])


def test_thumbnail_regenerated_from_original(db, settings, tmp_path, make_image):
    p = make_image(tmp_path / "p.jpg", 1, size=(1200, 800))
    db.register_files([(str(p), 1, 1)])
    db.save_results([{"image_id": 1}])
    t = get_thumbnail(settings, db, 1)
    assert t.is_file() and max(__import__("PIL.Image", fromlist=["x"]).open(t).size) <= 256
    assert db.get_image(1)["thumb_path"] == str(t)
    p.unlink()
    t.unlink()
    with pytest.raises(FileNotFoundError):
        get_thumbnail(settings, db, 1)
    with pytest.raises(ValueError):
        get_thumbnail(settings, db, 999)


# ---- health -----------------------------------------------------------------------
def test_repair_fixes_counts_and_requeues(db):
    db.register_files([("a.jpg", 1, 1), ("b.jpg", 1, 2)])
    db.save_results(
        [
            {"image_id": 1, "width": 5, "height": 5, "sha256": "s", "faces": [_face()]},
            {"image_id": 2, "faces": []},
        ]
    )  # 2: no hash/size = incomplete
    db._db.execute("UPDATE images SET face_count = 9 WHERE id = 1")
    result = db.repair()
    assert result["face_counts_fixed"] == 1 and result["requeued"] == 1
    assert db.get_image(1)["face_count"] == 1
    assert db.get_image(2)["status"] == "pending"


def test_backup_and_maintenance(settings, tmp_path):
    with DatabaseManager(settings.db_path) as db:
        db.register_files([("a.jpg", 1, 1)])
        result = run_maintenance(settings, db)
        assert result["integrity_problems"] == []
    conn = sqlite3.connect(result["backup"])
    assert conn.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 1
    conn.close()


def test_v2_database_upgrades_to_v3(tmp_path):
    path = tmp_path / "photos.db"
    conn = sqlite3.connect(path)
    for _, sql in MIGRATIONS[:2]:
        conn.executescript(sql(conn))
    conn.execute("PRAGMA user_version = 2")
    conn.execute("INSERT INTO images (path, size, mtime_ns) VALUES ('a.jpg', 1, 1)")
    conn.commit()
    conn.close()
    with DatabaseManager(path) as db:
        assert db.get_image(1)["state"] == "ok"
        assert db.list_sources() == []
    assert (tmp_path / "photos.db.bak-v2").is_file()
