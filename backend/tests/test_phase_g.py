"""Phase G: watch mode (debounce, settling, offline folders, cancel, battery, read-only)."""
from __future__ import annotations

import hashlib
import time

import pytest

from models import FaceBox
from database import DatabaseManager
from engine import Engine, EngineError, ErrorCode
from services.pipeline import orchestrator as pipeline
from services.pipeline.control import RunControl
from services.pipeline.watcher import FolderWatcher


class FakeDetector:
    def __init__(self):
        self.calls = 0

    def detect(self, loaded):
        self.calls += 1
        return [FaceBox(10, 10, 40, 40, 0.9)]

    def close(self):
        pass


@pytest.fixture
def det(monkeypatch):
    d = FakeDetector()
    monkeypatch.setattr(pipeline, "create_detector", lambda s: d)
    monkeypatch.setattr(pipeline, "ensure_model", lambda *args, **kwargs: None)
    monkeypatch.setitem(FolderWatcher.__init__.__kwdefaults__, "battery", lambda: False)
    return d


def make_watcher(settings, db, roots, **kw):
    kw.setdefault("interval_s", 0)
    kw.setdefault("settle_s", 0)
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("battery", lambda: False)
    return FolderWatcher(settings, db, roots, RunControl(), **kw)


@pytest.fixture
def root(tmp_path, make_image):
    r = tmp_path / "watched"
    make_image(r / "a.jpg", 1)
    make_image(r / "b.jpg", 2)
    return r


def test_new_files_processed_once_stable(settings, root, det):
    with DatabaseManager(settings.db_path) as db:
        w = make_watcher(settings, db, [root])
        assert w.run(max_cycles=1)["processed"] == 0          # first sighting only
        assert w.run(max_cycles=1)["processed"] == 2          # stable on the second poll
        assert db.report_stats()["processed"] == 2
        assert db.list_sources() == [str(root)]


def test_photo_added_later_is_picked_up_and_old_ones_are_not_redone(settings, root, make_image, det):
    with DatabaseManager(settings.db_path) as db:
        w = make_watcher(settings, db, [root])
        w.run(max_cycles=2)
        calls = det.calls
        w.run(max_cycles=2)
        assert det.calls == calls                              # nothing changed, nothing redone
        make_image(root / "c.jpg", 3)
        assert w.run(max_cycles=2)["processed"] == 1
        assert det.calls == calls + 1


def test_file_still_being_written_waits(settings, tmp_path, det):
    root = tmp_path / "w"
    root.mkdir()
    f = root / "x.jpg"
    f.write_bytes(b"1")
    with DatabaseManager(settings.db_path) as db:
        w = make_watcher(settings, db, [root])
        assert w.poll_once() == []                             # first sighting
        f.write_bytes(b"12")                                   # still growing
        assert w.poll_once() == []
        assert [p.name for p, _, _ in w.poll_once()] == ["x.jpg"]


def test_recent_files_wait_for_settle_time(settings, root, det):
    with DatabaseManager(settings.db_path) as db:
        w = make_watcher(settings, db, [root], settle_s=3600)
        w.poll_once()
        assert w.poll_once() == []                             # too new
        w._now = lambda: time.time() + 7200
        assert len(w.poll_once()) == 2


def test_offline_folder_is_skipped_then_recovers(settings, root, tmp_path, det):
    with DatabaseManager(settings.db_path) as db:
        w = make_watcher(settings, db, [root])
        w.run(max_cycles=2)
        root.rename(tmp_path / "unplugged")
        assert w.run(max_cycles=2)["processed"] == 0           # no error, nothing marked missing
        assert db.state_counts() == {"ok": 2, "offline": 0, "missing": 0}
        (tmp_path / "unplugged").rename(root)
        assert w.run(max_cycles=2)["processed"] == 0           # known files are unchanged


def test_cancel_stops_the_loop(settings, root, det):
    control = RunControl()
    with DatabaseManager(settings.db_path) as db:
        w = FolderWatcher(settings, db, [root], control, interval_s=1, settle_s=0,
                          sleep=lambda s: control.cancel(), battery=lambda: False)
        assert w.run()["cycles"] == 1


def test_battery_pauses_unless_allowed(settings, root, det):
    with DatabaseManager(settings.db_path) as db:
        w = make_watcher(settings, db, [root], battery=lambda: True)
        assert w.run(max_cycles=3)["processed"] == 0
        w2 = make_watcher(settings, db, [root], battery=lambda: True, pause_on_battery=False)
        assert w2.run(max_cycles=2)["processed"] == 2


def test_photos_are_never_modified(settings, root, tmp_path, det):
    snap = lambda: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    before = snap()
    with DatabaseManager(settings.db_path) as db:
        make_watcher(settings, db, [root]).run(max_cycles=3)
    assert snap() == before
    assert sorted(p.name for p in root.iterdir()) == sorted(before)


def test_engine_watch(settings, root, tmp_path, det):
    with Engine(settings.workspace, settings=settings) as eng:
        with pytest.raises(EngineError) as err:
            eng.watch()                                        # no folders known yet
        assert err.value.code == ErrorCode.INVALID_INPUT
        result = eng.watch([root], interval_s=1, settle_s=0, max_cycles=2)
        assert result["processed"] == 2
        assert eng.stats()["processed"] == 2
