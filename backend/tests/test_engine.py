"""Engine API: progress, cancel/resume, marks, config, profiles, migrations, doctor."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from models import FaceBox
from database import DatabaseError, DatabaseManager
from database.db_manager import SCHEMA_PATH
from engine import Engine, EngineError, ErrorCode
from engine.settings_file import load_settings
from services.pipeline import orchestrator as pipeline


class FakeDetector:
    def detect(self, loaded):
        return [FaceBox(10, 10, 40, 40, 0.9)]

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_detector(monkeypatch):
    monkeypatch.setattr(pipeline, "create_detector", lambda s: FakeDetector())
    monkeypatch.setattr(pipeline, "ensure_model", lambda p: p)


@pytest.fixture
def photos(tmp_path, make_image):
    root = tmp_path / "photos"
    for i in range(1, 6):
        make_image(root / f"p{i}.jpg", seed=i)
    return root


def _snapshot(root):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}


def test_run_all_reports_progress_and_never_touches_photos(settings, photos):
    before = _snapshot(photos)
    events = []
    with Engine(settings.workspace, settings=settings, on_event=events.append) as eng:
        result = eng.run_all(photos)
        assert (result["processed"], result["failed"], result["remaining"]) == (5, 0, 0)
        assert result["stats"]["total_faces"] == 5
        assert len(eng.search(min_faces=1)) == 5
        assert "features" not in eng.search()[0]  # blobs are not exposed
    stages = {e.stage for e in events}
    assert {"scan", "process", "duplicates", "groups", "done"} <= stages
    assert max(e.done for e in events if e.stage == "process") == 5
    assert _snapshot(photos) == before  # same files, same bytes


def test_cancel_then_resume(settings, photos):
    holder = {}

    def on_event(ev):
        if ev.stage == "process" and ev.done >= 2 and "eng" in holder:
            holder["eng"].cancel()

    with Engine(settings.workspace, settings=settings, on_event=on_event) as eng:
        holder["eng"] = eng
        eng.scan(photos)
        first = eng.process()
        assert first["interrupted"] and (first["processed"], first["remaining"]) == (2, 3)
        holder.clear()
        second = eng.process()
        assert (second["processed"], second["remaining"], second["interrupted"]) == (3, 0, False)
        assert eng.stats()["total_faces"] == 5  # no duplicate rows after resume


def test_marks_roundtrip_and_validation(settings, photos):
    with Engine(settings.workspace, settings=settings) as eng:
        eng.run_all(photos)
        image_id = eng.search()[0]["id"]
        eng.set_mark(image_id, "keep", "best one")
        assert [(m["kind"], m["note"]) for m in eng.get_marks(image_id)] == [("keep", "best one")]
        assert eng.clear_mark(image_id, "keep") is True
        assert eng.get_marks(image_id) == []
        with pytest.raises(EngineError) as bad_kind:
            eng.set_mark(image_id, "delete")
        assert bad_kind.value.code == ErrorCode.INVALID_INPUT
        with pytest.raises(EngineError):
            eng.set_mark(99999, "keep")


def test_missing_folder_is_drive_offline(settings, tmp_path):
    with Engine(settings.workspace, settings=settings) as eng:
        with pytest.raises(EngineError) as err:
            eng.run_all(tmp_path / "unplugged")
        assert err.value.code == ErrorCode.DRIVE_OFFLINE


def test_engine_must_be_open(settings):
    with pytest.raises(EngineError) as err:
        Engine(settings.workspace, settings=settings).stats()
    assert err.value.code == ErrorCode.NOT_OPEN


# ---- config and profiles -------------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "confidence_threshold = 2",
        "workers = 0",
        "cpu_limit = 0",
        'workers = "two"',
        "nonsense_key = 1",
        'detector_backend = "magic"',
        'profile = "turbo"',
    ],
)
def test_invalid_config_rejected(tmp_path, line):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "config.toml").write_text(line + "\n", encoding="utf-8")
    with pytest.raises(EngineError) as err:
        load_settings(ws)
    assert err.value.code == ErrorCode.CONFIG_INVALID


def test_broken_toml_rejected(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "config.toml").write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(EngineError):
        load_settings(ws)


def test_profile_then_explicit_values(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "config.toml").write_text('profile = "gentle"\nbatch_size = 8\n', encoding="utf-8")
    s = load_settings(ws)
    assert (s.workers, s.cpu_limit, s.batch_size) == (1, 0.5, 8)  # file value beats profile
    assert s.save_annotated is False and s.save_face_crops is False
    assert load_settings(ws, profile="fast").cpu_limit == 1.0


def test_missing_config_uses_defaults(tmp_path):
    s = load_settings(tmp_path / "fresh")
    assert s.workers >= 1 and s.save_annotated is False


# ---- migrations ----------------------------------------------------------------
def _make_v1_db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("PRAGMA user_version = 1")
    conn.execute("INSERT INTO images (path, size, mtime_ns) VALUES ('a.jpg', 1, 1)")
    conn.commit()
    conn.close()


def test_v1_database_is_upgraded_with_backup(tmp_path):
    path = tmp_path / "ws" / "photos.db"
    _make_v1_db(path)
    with DatabaseManager(path) as db:
        assert db._scalar("PRAGMA user_version") >= 2
        assert db.report_stats()["total_images"] == 1  # data survived
        db.set_mark(1, "keep")
        assert db.get_marks(1)[0]["kind"] == "keep"
    assert (tmp_path / "ws" / "photos.db.bak-v1").is_file()


def test_newer_database_is_refused(tmp_path):
    path = tmp_path / "photos.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    with pytest.raises(DatabaseError):
        DatabaseManager(path).open()


# ---- doctor ---------------------------------------------------------------------
def test_doctor_flags_unreachable_source(settings, tmp_path):
    with Engine(settings.workspace, settings=settings) as eng:
        report = eng.doctor([tmp_path / "missing_drive"])
    names = {c["name"]: c["status"] for c in report["checks"]}
    assert names["workspace"] == "ok"
    assert any(n.startswith("source") and s == "fail" for n, s in names.items())
    assert report["ok"] is False
