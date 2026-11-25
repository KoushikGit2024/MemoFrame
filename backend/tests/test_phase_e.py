"""Phase E: combined search, FTS, saved searches, timeline, marks restore, move detection."""
from __future__ import annotations

import sqlite3

import pytest

from database import DatabaseManager
from database.db_manager import fts_query
from database.migrations import MIGRATIONS
from engine import Engine, EngineError, ErrorCode
from services.pipeline import orchestrator as pipeline


def _face():
    return {"x": 1, "y": 1, "w": 5, "h": 5, "confidence": 0.9}


def _setup(db):
    db.register_files([("/p/holiday/a.jpg", 1, 1), ("/p/holiday/b.heic", 1, 2),
                       ("/p/work/c.png", 1, 3), ("/p/work/d.jpg", 1, 4)])
    db.save_results([
        {"image_id": 1, "exif_ts": "2024-06-01T10:00:00", "ts_source": "exif_original",
         "quality": 80.0, "format": "JPEG", "faces": [_face(), _face()]},
        {"image_id": 2, "exif_ts": "2024-06-02T10:00:00", "ts_source": "exif_original",
         "quality": 40.0, "format": "HEIF"},
        {"image_id": 3, "exif_ts": "2023-01-05T09:00:00", "ts_source": "exif_original",
         "content_type": "screenshot", "format": "PNG"},
        {"image_id": 4, "ts_source": "none", "format": "JPEG"},
    ])
    db.set_places([(1, "Imphal, IN"), (2, "")])
    db.rebuild_fts()


def ids(db, **kw):
    return [r["id"] for r in db.find_images(**kw)]


# ---- search -----------------------------------------------------------------------
def test_fts_query_is_sanitised():
    assert fts_query('a"b* c_d') == '"a"* "b"* "c"* "d"*'
    assert fts_query('"; DROP TABLE images; --') == '"DROP"* "TABLE"* "images"*'


def test_text_search_words_places_and_dates(db):
    _setup(db)
    if not db.ensure_fts():
        pytest.skip("SQLite without FTS5")
    assert ids(db, text="holiday") == [1, 2]
    assert ids(db, text="imphal june") == [1]
    assert ids(db, text="hol") == [1, 2]                          # prefix
    assert ids(db, text="heif") == [2]
    assert ids(db, text='"; DROP TABLE images; --') == []         # no error, no damage
    assert db.report_stats()["total_images"] == 4


def test_text_search_falls_back_without_fts(db):
    _setup(db)
    db._fts = False
    assert ids(db, text="holiday") == [1, 2]


def test_filters_sorting_and_counts(db):
    _setup(db)
    assert ids(db) == [3, 1, 2, 4]                                # undated last
    assert ids(db, sort="date_desc") == [2, 1, 3, 4]
    assert ids(db, min_faces=1) == [1]
    assert ids(db, format="heif") == [2]
    assert ids(db, content_type="screenshot") == [3]
    assert ids(db, min_quality=50) == [1]
    assert ids(db, sort="quality") == [1, 2, 3, 4]
    assert ids(db, limit=2, offset=1) == [1, 2]
    assert db.count_images(path_contains="work") == 2
    assert db.count_images() == 4


def test_unknown_filter_and_sort_rejected(db):
    _setup(db)
    with pytest.raises(ValueError):
        db.find_images(bogus=1)
    with pytest.raises(ValueError):
        db.find_images(sort="random")
    with pytest.raises(ValueError):
        db.find_images(duplicate="maybe")
    with pytest.raises(ValueError):
        db.find_images(mark="delete")


def test_date_override_affects_sort_and_filter(db):
    _setup(db)
    db.set_date_override(3, "2025-01-01T00:00:00")
    assert ids(db) == [1, 2, 3, 4]
    assert ids(db, taken_from="2025-01-01") == [3]
    assert db.find_images(taken_from="2025-01-01")[0]["effective_ts"] == "2025-01-01T00:00:00"


def test_marks_and_hidden(db):
    _setup(db)
    db.set_mark(2, "hidden")
    db.set_mark(1, "keep")
    assert ids(db) == [3, 1, 4]                                   # hidden photos left out
    assert ids(db, mark="hidden") == [2]
    assert 2 in ids(db, include_hidden=True)
    assert ids(db, mark="keep") == [1]
    assert 1 not in ids(db, no_mark="keep")


def test_duplicate_and_burst_filters(db):
    _setup(db)
    db.replace_duplicates([(1, 1, "exact"), (2, 1, "exact")])
    assert ids(db, duplicate="any") == [1, 2]
    assert ids(db, duplicate="none") == [3, 4]
    assert ids(db, duplicate="near") == []
    db.replace_bursts([{"image_ids": [3, 4], "best_id": 3}])
    assert ids(db, in_burst=True) == [3, 4]
    assert ids(db, in_burst=False) == [1, 2]


def test_timeline(db):
    _setup(db)
    assert db.timeline("month") == [{"period": "2023-01", "count": 1},
                                    {"period": "2024-06", "count": 2},
                                    {"period": None, "count": 1}]
    assert db.timeline("year")[0] == {"period": "2023", "count": 1}
    with pytest.raises(ValueError):
        db.timeline("week")


def test_saved_searches(db):
    _setup(db)
    db.save_search("faces", {"min_faces": 1, "sort": "quality"})
    db.save_search("faces", {"min_faces": 2})                     # overwrite
    assert db.list_saved_searches() == [{"name": "faces", "filters": {"min_faces": 2}}]
    assert ids(db, **db.get_saved_search("faces")) == [1]
    with pytest.raises(ValueError):
        db.save_search("bad", {"nonsense": 1})
    with pytest.raises(ValueError):
        db.save_search("  ", {})
    assert db.delete_saved_search("faces") is True
    assert db.get_saved_search("faces") is None


def test_index_rebuild_skipped_when_unchanged(db, settings, monkeypatch):
    _setup(db)
    calls = []
    real = db.rebuild_fts
    monkeypatch.setattr(db, "rebuild_fts", lambda: calls.append(1) or real())
    pipeline.update_search_index(settings, db)
    pipeline.update_search_index(settings, db)
    assert len(calls) == 1
    db.set_places([(1, "Elsewhere")])                             # bumps the revision
    pipeline.update_search_index(settings, db)
    assert len(calls) == 2


# ---- marks that survive reset / moves ----------------------------------------------------
def _one(db, path, sha):
    db.register_files([(path, 1, 1)])
    image_id = db._query("SELECT id FROM images WHERE path = ?", (path,))[0]["id"]
    db.save_results([{"image_id": image_id, "sha256": sha}])
    return image_id


def test_marks_survive_reset(db):
    first = _one(db, "a.jpg", "S")
    db.set_mark(first, "keep", "best")
    db.reset()
    assert db.get_marks() == []
    second = _one(db, "a.jpg", "S")
    assert db.restore_marks() == 1
    assert [(m["kind"], m["note"]) for m in db.get_marks(second)] == [("keep", "best")]
    assert db.restore_marks() == 0                                # idempotent


def test_marks_follow_a_moved_file(db):
    old = _one(db, "old/a.jpg", "S")
    db.set_mark(old, "favourite")
    new = _one(db, "new/a.jpg", "S")
    db.set_states([(old, "missing")])
    assert [r["new_id"] for r in db.find_moves()] == [new]
    assert db.restore_marks() == 1
    assert [m["kind"] for m in db.get_marks(new)] == ["favourite"]


def test_identical_copies_do_not_share_marks(db):
    a = _one(db, "a.jpg", "S")
    b = _one(db, "b.jpg", "S")
    db.set_mark(a, "keep")
    assert db.restore_marks() == 0 and db.get_marks(b) == []      # A still exists: B gets nothing
    c = _one(db, "c.jpg", "S")
    db.set_states([(a, "missing")])
    assert db.restore_marks() == 0                                # two candidates: ambiguous
    assert db.find_moves() == []
    assert db.get_marks(b) == [] and db.get_marks(c) == []


def test_clear_mark_also_clears_archive(db):
    a = _one(db, "a.jpg", "S")
    db.set_mark(a, "keep")
    assert db.clear_mark(a, "keep") is True
    db.reset()
    _one(db, "a.jpg", "S")
    assert db.restore_marks() == 0


# ---- migration -----------------------------------------------------------------------------
def test_v5_database_upgrades_to_v6_and_archives_marks(tmp_path):
    path = tmp_path / "photos.db"
    conn = sqlite3.connect(path)
    for _, sql in MIGRATIONS[:5]:
        conn.executescript(sql(conn))
    conn.execute("PRAGMA user_version = 5")
    conn.execute("INSERT INTO images (path, size, mtime_ns, sha256, status) "
                 "VALUES ('a.jpg', 1, 1, 'S', 'done')")
    conn.execute("INSERT INTO marks (image_id, kind) VALUES (1, 'keep')")
    conn.commit()
    conn.close()
    with DatabaseManager(path) as db:
        assert db._scalar("SELECT COUNT(*) FROM marks_archive") == 1
        assert db.list_saved_searches() == []
    assert (tmp_path / "photos.db.bak-v5").is_file()


# ---- engine -------------------------------------------------------------------------------------
def test_engine_find_saved_timeline_and_errors(settings):
    with Engine(settings.workspace, settings=settings) as eng:
        _setup(eng.db)
        rows = eng.find(text="holiday") if eng.db.ensure_fts() else eng.find(path_contains="holiday")
        assert [r["id"] for r in rows] == [1, 2] and "features" not in rows[0]
        eng.save_search("faces", {"min_faces": 1})
        assert [r["id"] for r in eng.run_saved_search("faces")] == [1]
        assert eng.count(min_faces=1) == 1
        assert eng.timeline("year")[-1]["period"] is None
        with pytest.raises(EngineError) as bad:
            eng.find(bogus=1)
        assert bad.value.code == ErrorCode.INVALID_INPUT
        with pytest.raises(EngineError):
            eng.run_saved_search("missing")
