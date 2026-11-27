from __future__ import annotations

from pathlib import Path

from memoframe_engine.api import Engine
from memoframe_engine.core.models import FaceBox


def _face():
    return {"x": 1, "y": 1, "w": 50, "h": 50, "confidence": 0.9}


def test_rename_person_locks_only_when_asked(settings):
    with Engine(settings.workspace, settings=settings) as eng:
        eng.db.register_files([("a.jpg", 1, 1), ("b.jpg", 1, 2)])
        eng.db.save_results([{"image_id": i, "faces": [_face()]} for i in (1, 2)])
        ids = [eng.get_faces(i)[0]["id"] for i in (1, 2)]
        eng.db.replace_person_clusters({1: ids})
        pid = eng.get_persons()[0]["id"]
        eng.rename_person(pid, "Alice")
        assert eng.get_faces(1)[0]["locked"] == 0
        eng.rename_person(pid, "Alice", confirm_faces=True)
        assert eng.get_faces(1)[0]["locked"] == 1


def test_reset_keeps_sources_and_searches_unless_asked(settings):
    with Engine(settings.workspace, settings=settings) as eng:
        eng.db.add_source("/x")
        eng.save_search("s", {"min_faces": 1})
        eng.reset_workspace()
        assert eng.db.list_sources() == ["/x"] and len(eng.list_saved_searches()) == 1
        eng.reset_workspace(clear_sources=True, clear_saved_searches=True)
        assert eng.db.list_sources() == [] and eng.list_saved_searches() == []


def test_process_faces_does_not_reread_the_file(settings, tmp_path, make_image, monkeypatch):
    from memoframe_engine.domains.face import processor

    p = make_image(tmp_path / "a.jpg", 1)
    data = p.read_bytes()
    p.unlink()

    def boom(*a, **k):
        raise AssertionError("re-read from disk")

    monkeypatch.setattr(processor, "load_image", boom)
    out = processor.process_faces(1, p, [FaceBox(10, 10, 40, 40, 0.9)], settings, data=data)
    assert out[0].crop_path and Path(out[0].crop_path).is_file()


def test_recognize_existing_runs_once_per_signature(settings):
    settings.ensure_dirs()
    settings.sface_path.write_bytes(b"x" * 100)
    with Engine(settings.workspace, settings=settings) as eng:
        eng.db.set_meta("recog_backfill", eng._recog_sig())
        assert eng.recognize_existing() == {"requeued": 0, "processed": 0}
