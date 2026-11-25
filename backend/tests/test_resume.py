"""Pipeline end to end with a fake detector: batching, failures, resume, interruption."""
from __future__ import annotations

import hashlib
import os
import shutil

import pytest

from models import FaceBox
from database import DatabaseManager
from services.pipeline import orchestrator as pipeline
from services.pipeline.orchestrator import process_pending, scan_directory, update_duplicates, update_groups


class FakeDetector:
    """Always finds two faces. Optionally raises KeyboardInterrupt on call N."""

    def __init__(self, interrupt_on: int | None = None):
        self.calls = 0
        self.interrupt_on = interrupt_on

    def detect(self, loaded):
        self.calls += 1
        if self.interrupt_on == self.calls:
            raise KeyboardInterrupt
        return [FaceBox(10, 10, 40, 40, 0.9), FaceBox(100, 20, 40, 40, 0.8)]

    def close(self):
        pass


@pytest.fixture
def use_detector(monkeypatch):
    """Install a fake detector; no model download, no network."""
    def install(detector):
        monkeypatch.setattr(pipeline, "create_detector", lambda settings: detector)
        monkeypatch.setattr(pipeline, "ensure_model", lambda path: path)
        return detector
    return install


@pytest.fixture
def photos(tmp_path, make_image):
    root = tmp_path / "photos"
    for i in range(1, 4):
        make_image(root / f"p{i}.jpg", seed=i)
    (root / "bad.jpg").write_bytes(b"not an image")
    return root


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_processes_good_files_and_records_failure(settings, photos, use_detector):
    use_detector(FakeDetector())
    with DatabaseManager(settings.db_path) as db:
        assert scan_directory(settings, db, photos).new == 4
        summary = process_pending(settings, db, show_progress=False)
        assert (summary.processed, summary.failed, summary.remaining, summary.interrupted) == (3, 1, 0, False)
        stats = db.report_stats()
        assert (stats["processed"], stats["failed"], stats["total_faces"], stats["multi_face_images"]) == (3, 1, 6, 3)
        faces = db.get_faces(db.search_images()[0]["id"])
        assert [f["label"] for f in faces] == ["Face 001", "Face 002"]
        assert all(os.path.isfile(f["crop_path"]) for f in faces)
        assert "bad.jpg" in db.failed_images()[0]["path"]


def test_second_run_does_nothing(settings, photos, use_detector):
    detector = use_detector(FakeDetector())
    with DatabaseManager(settings.db_path) as db:
        scan_directory(settings, db, photos)
        process_pending(settings, db, show_progress=False)
        calls = detector.calls
        stats = scan_directory(settings, db, photos)
        assert (stats.new, stats.changed, stats.unchanged) == (0, 0, 4)
        summary = process_pending(settings, db, show_progress=False)
        assert (summary.processed, summary.failed, summary.remaining) == (0, 0, 0)
        assert detector.calls == calls                      # nothing was re-detected


def test_interrupt_then_resume(settings, tmp_path, make_image, use_detector):
    root = tmp_path / "photos"
    for i in range(1, 6):
        make_image(root / f"p{i}.jpg", seed=i)
    with DatabaseManager(settings.db_path) as db:
        scan_directory(settings, db, root)

        use_detector(FakeDetector(interrupt_on=4))          # Ctrl+C during the 4th image
        first = process_pending(settings, db, show_progress=False)
        assert first.interrupted
        assert (first.processed, first.remaining) == (3, 2)  # batch 1 + the image finished before the interrupt

        use_detector(FakeDetector())
        second = process_pending(settings, db, show_progress=False)
        assert (second.processed, second.remaining, second.interrupted) == (2, 0, False)

        stats = db.report_stats()
        assert (stats["processed"], stats["pending"]) == (5, 0)
        assert stats["total_faces"] == 10                   # no duplicate face rows after resume


def test_changed_file_is_reprocessed(settings, photos, make_image, use_detector):
    use_detector(FakeDetector())
    with DatabaseManager(settings.db_path) as db:
        scan_directory(settings, db, photos)
        process_pending(settings, db, show_progress=False)
        target = photos / "p1.jpg"
        make_image(target, seed=99, size=(400, 300))
        stat = target.stat()
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        assert scan_directory(settings, db, photos).changed == 1
        assert db.count_pending() == 1
        assert process_pending(settings, db, show_progress=False).processed == 1


def test_failed_files_need_retry_flag(settings, photos, make_image, use_detector):
    use_detector(FakeDetector())
    with DatabaseManager(settings.db_path) as db:
        scan_directory(settings, db, photos)
        process_pending(settings, db, show_progress=False)
        assert db.count_pending() == 0                      # failed file is not retried by default

        make_image(photos / "bad.jpg", seed=50)             # "fix" the file without rescanning
        summary = process_pending(settings, db, retry_failed=True, show_progress=False)
        assert (summary.processed, summary.failed) == (1, 0)


def test_originals_are_never_modified(settings, photos, use_detector):
    use_detector(FakeDetector())
    before = {p.name: _sha(p) for p in photos.glob("*.jpg")}
    with DatabaseManager(settings.db_path) as db:
        scan_directory(settings, db, photos)
        process_pending(settings, db, show_progress=False)
        update_duplicates(settings, db)
        update_groups(settings, db)
    assert {p.name: _sha(p) for p in photos.glob("*.jpg")} == before
    assert sorted(p.name for p in photos.iterdir()) == sorted(before)   # no extra files beside them


def test_duplicates_and_groups_after_processing(settings, photos, use_detector):
    use_detector(FakeDetector())
    shutil.copy(photos / "p1.jpg", photos / "p1_copy.jpg")
    with DatabaseManager(settings.db_path) as db:
        scan_directory(settings, db, photos)
        process_pending(settings, db, show_progress=False)
        assert update_duplicates(settings, db) == 1
        assert update_groups(settings, db) >= 1
        stats = db.report_stats()
        assert (stats["duplicate_clusters"], stats["duplicate_images"]) == (1, 1)
        assert (settings.grouped_dir / "groups.csv").is_file()


def test_workspace_inside_photo_folder_is_not_scanned(settings, tmp_path, photos, use_detector):
    use_detector(FakeDetector())
    with DatabaseManager(settings.db_path) as db:
        scan_directory(settings, db, tmp_path)              # root contains both photos/ and ws/
        process_pending(settings, db, show_progress=False)
        again = scan_directory(settings, db, tmp_path)      # thumbnails now exist in ws/
        assert (again.new, again.changed) == (0, 0)
        assert again.total == 4