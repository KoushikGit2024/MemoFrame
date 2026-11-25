"""Face detection: shared box handling (no model needed) and real YuNet (skips without model)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from config import YUNET_FILENAME, Settings
from services.face.detector import (
    DetectorUnavailableError,
    FaceDetector,
    YuNetDetector,
    create_detector,
)
from services.vision.loader import LoadedImage, load_image
from services.face.processor import assign_labels, expand_box

ROOT = Path(__file__).resolve().parent.parent
MODEL = Path(os.environ.get("PHOTO_ORGANIZER_MODEL", ROOT / "workspace" / "models" / YUNET_FILENAME))
FACE_PHOTO = os.environ.get("PHOTO_ORGANIZER_TEST_IMAGE")
EXPECTED_FACES = int(os.environ.get("PHOTO_ORGANIZER_TEST_FACES", "1"))

needs_model = pytest.mark.skipif(not MODEL.is_file(), reason=f"YuNet model not found at {MODEL}")
needs_photo = pytest.mark.skipif(
    not (FACE_PHOTO and Path(FACE_PHOTO).is_file()),
    reason="set PHOTO_ORGANIZER_TEST_IMAGE to a photo containing faces",
)


class FakeDetector(FaceDetector):
    """Returns preset raw boxes so the shared post-processing can be tested."""

    name = "fake"

    def __init__(self, raw):
        super().__init__(confidence_threshold=0.7, min_face_px=20)
        self.raw = raw

    def _detect_bgr(self, bgr):
        return self.raw


def _loaded() -> LoadedImage:
    """Full image 200x100, analysed at half size (scale 2)."""
    return LoadedImage(pil=Image.new("RGB", (100, 50)), width=200, height=100,
                       scale=2.0, exif=Image.Exif())


def test_zero_faces():
    assert FakeDetector([]).detect(_loaded()) == []


def test_single_face_scaled_to_full_resolution():
    faces = FakeDetector([(10, 10, 20, 20, 0.9)]).detect(_loaded())
    assert [(f.x, f.y, f.w, f.h, f.confidence) for f in faces] == [(20, 20, 40, 40, 0.9)]


def test_multiple_faces_filtered_clipped_and_ordered():
    raw = [
        (90, 40, 30, 30, 0.80),    # runs past the right/bottom edge -> clipped to 20x20
        (10, 10, 20, 20, 0.90),    # normal
        (50, 5, 10, 10, 0.50),     # below confidence threshold -> dropped
        (80, 10, 5, 5, 0.90),      # 10 px at full resolution -> dropped (min_face_px=20)
        (-5, -5, 30, 30, 0.95),    # starts outside the image -> clipped at 0,0
    ]
    faces = FakeDetector(raw).detect(_loaded())
    assert [(f.x, f.y, f.w, f.h) for f in faces] == [(0, 0, 50, 50), (20, 20, 40, 40), (180, 80, 20, 20)]
    for f in faces:
        assert f.x + f.w <= 200 and f.y + f.h <= 100


def test_labels_are_anonymous_and_positional():
    faces = FakeDetector([(10, 10, 20, 20, 0.9), (60, 10, 20, 20, 0.9)]).detect(_loaded())
    labelled = assign_labels(faces)
    assert [f.label for f in labelled] == ["Face 001", "Face 002"]
    assert all(f.crop_path is None for f in labelled)


def test_expand_box_clips_to_image():
    from models import FaceBox
    box = FaceBox(5, 5, 100, 100, 0.9)
    assert expand_box(box, 120, 120, 0.25) == (0, 0, 120, 120)


def test_unknown_backend_rejected(tmp_path):
    with pytest.raises(DetectorUnavailableError):
        create_detector(Settings(workspace=tmp_path, detector_backend="nope"))


def test_missing_model_file_reported(tmp_path):
    with pytest.raises(DetectorUnavailableError):
        YuNetDetector(tmp_path / "missing.onnx")


# ---- real detector (skipped unless the model / a face photo is available) ----
@needs_model
def test_yunet_blank_image_has_no_faces(tmp_path):
    p = tmp_path / "blank.jpg"
    Image.new("RGB", (640, 480), "white").save(p)
    detector = YuNetDetector(MODEL)
    assert detector.detect(load_image(p, 1280)) == []


@needs_model
@needs_photo
def test_yunet_finds_faces_in_real_photo():
    settings = Settings()
    li = load_image(Path(FACE_PHOTO), settings.max_detect_side)
    faces = YuNetDetector(MODEL).detect(li)
    assert len(faces) >= EXPECTED_FACES
    xs = [f.x for f in faces]
    assert xs == sorted(xs)                              # left-to-right order
    for f in faces:
        assert 0.7 <= f.confidence <= 1.0
        assert 0 <= f.x and f.x + f.w <= li.width
        assert 0 <= f.y and f.y + f.h <= li.height