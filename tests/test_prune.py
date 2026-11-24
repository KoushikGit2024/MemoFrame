"""Pruning records of deleted photos."""
from __future__ import annotations

import pytest

from processing.pipeline import PipelineError, find_missing_images, remove_images
from processing.thumbnail_generator import shard_dir


def _face():
    return {"x": 1, "y": 1, "w": 5, "h": 5, "confidence": 0.9}


def _setup(db, tmp_path, make_image):
    root = tmp_path / "photos"
    a = make_image(root / "a.jpg", seed=1)
    b = make_image(root / "b.jpg", seed=2)
    other = make_image(tmp_path / "elsewhere" / "c.jpg", seed=3)
    db.register_files([(str(a), 1, 1), (str(b), 1, 2), (str(other), 1, 3)])
    db.save_results([{"image_id": i, "sha256": "same", "phash": "0" * 16,
                      "width": 10, "height": 10, "faces": [_face()]} for i in (1, 2, 3)])
    return root, a, b, other


def test_finds_only_missing_files(db, tmp_path, make_image):
    root, a, b, other = _setup(db, tmp_path, make_image)
    assert find_missing_images(db) == (3, [])
    b.unlink()
    assert find_missing_images(db) == (3, [(2, str(b))])


def test_root_limits_the_check(db, tmp_path, make_image):
    root, a, b, other = _setup(db, tmp_path, make_image)
    b.unlink()
    other.unlink()
    checked, missing = find_missing_images(db, root)
    assert checked == 2 and missing == [(2, str(b))]          # c.jpg is outside the root


def test_missing_root_is_refused(db, tmp_path):
    with pytest.raises(PipelineError):
        find_missing_images(db, tmp_path / "unplugged_drive")


def test_remove_deletes_records_outputs_and_rebuilds_duplicates(db, settings, tmp_path, make_image):
    root, a, b, other = _setup(db, tmp_path, make_image)
    thumb = shard_dir(settings.thumbnails_dir, 2) / "00000002_b.jpg"
    crop = shard_dir(settings.face_crops_dir, 2) / "00000002_b_f001.jpg"
    keep = shard_dir(settings.thumbnails_dir, 1) / "00000001_a.jpg"
    for f in (thumb, crop, keep):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")

    from processing.pipeline import update_duplicates
    assert update_duplicates(settings, db) == 1               # all three share one SHA-256

    b.unlink()
    assert remove_images(settings, db, [2]) == 1
    assert db.get_image(2) is None and db.get_faces(2) == []
    assert not thumb.exists() and not crop.exists()
    assert keep.exists()                                       # other images' files stay
    assert a.exists() and other.exists()                       # photos are never touched
    assert db.report_stats()["duplicate_images"] == 1          # cluster of 3 -> cluster of 2


def test_remove_nothing_is_a_no_op(db, settings, tmp_path, make_image):
    _setup(db, tmp_path, make_image)
    assert remove_images(settings, db, []) == 0
    assert db.report_stats()["total_images"] == 3