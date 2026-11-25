"""Image loading, corrupted-file handling, scanner and metadata extraction."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from services.vision.loader import ImageLoadError, load_image
from services.vision.metadata import extract_metadata, parse_exif_datetime
from models import TS_EXIF_DATETIME, TS_FILE_MTIME, TS_NONE
from services.pipeline.scanner import iter_image_files


def test_loads_and_downscales(tmp_path, make_image):
    p = make_image(tmp_path / "big.jpg", size=(3000, 2000))
    li = load_image(p, 1280)
    assert (li.width, li.height) == (3000, 2000)  # full-resolution size is kept
    assert max(li.pil.size) <= 1280
    assert li.scale == pytest.approx(3000 / li.pil.width)
    assert li.to_bgr().shape == (li.pil.height, li.pil.width, 3)


def test_no_downscale_means_scale_one(tmp_path, make_image):
    li = load_image(make_image(tmp_path / "a.png", size=(120, 80)))
    assert li.pil.size == (120, 80)
    assert li.scale == 1.0


def test_exif_orientation_applied_in_memory(tmp_path):
    p = tmp_path / "rot.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees
    Image.new("RGB", (200, 100), "red").save(p, exif=exif)
    li = load_image(p)
    assert (li.width, li.height) == (100, 200)
    assert li.pil.size == (100, 200)
    with Image.open(p) as original:  # file itself is untouched
        assert original.size == (200, 100)


def test_rgba_png_converted_to_rgb(tmp_path):
    p = tmp_path / "alpha.png"
    Image.new("RGBA", (50, 50), (255, 0, 0, 128)).save(p)
    assert load_image(p).pil.mode == "RGB"


def test_non_ascii_filename(tmp_path, make_image):
    p = make_image(tmp_path / "фото_日本.jpg")
    assert load_image(p).width == 300


def test_garbage_file_raises(tmp_path):
    p = tmp_path / "bad.jpg"
    p.write_bytes(b"definitely not an image")
    with pytest.raises(ImageLoadError):
        load_image(p)


def test_empty_file_raises(tmp_path):
    p = tmp_path / "empty.png"
    p.write_bytes(b"")
    with pytest.raises(ImageLoadError):
        load_image(p)


def test_truncated_jpeg_raises(tmp_path):
    p = tmp_path / "trunc.jpg"
    noise = np.random.default_rng(0).integers(0, 256, (200, 200, 3), dtype=np.uint8)
    Image.fromarray(noise).save(p, quality=95)
    data = p.read_bytes()
    p.write_bytes(data[: len(data) // 2])
    with pytest.raises(ImageLoadError):
        load_image(p)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ImageLoadError):
        load_image(tmp_path / "nope.jpg")


# ---- scanner ---------------------------------------------------------------
def test_scanner_filters_extensions_and_recurses(tmp_path, make_image):
    make_image(tmp_path / "a.JPG")
    make_image(tmp_path / "sub" / "b.png")
    make_image(tmp_path / "sub" / "deep" / "c.webp")
    (tmp_path / "notes.txt").write_text("x")
    found = {p.name: (size, mtime) for p, size, mtime in iter_image_files(tmp_path)}
    assert set(found) == {"a.JPG", "b.png", "c.webp"}
    assert found["a.JPG"][0] == (tmp_path / "a.JPG").stat().st_size


def test_scanner_excludes_workspace(tmp_path, make_image):
    make_image(tmp_path / "photo.jpg")
    make_image(tmp_path / "ws" / "thumbnails" / "t.jpg")
    names = [p.name for p, _, _ in iter_image_files(tmp_path, exclude=[tmp_path / "ws"])]
    assert names == ["photo.jpg"]


def test_scanner_is_deterministic(tmp_path, make_image):
    for name in ("b.jpg", "A.jpg", "c.jpg"):
        make_image(tmp_path / name)
    first = [p.name for p, _, _ in iter_image_files(tmp_path)]
    assert first == [p.name for p, _, _ in iter_image_files(tmp_path)]
    assert first == ["A.jpg", "b.jpg", "c.jpg"]


# ---- metadata --------------------------------------------------------------
@pytest.mark.parametrize("value", ["0000:00:00 00:00:00", "", "garbage", None, 42])
def test_bad_exif_dates_rejected(value):
    assert parse_exif_datetime(value) is None


def test_valid_exif_date_parsed():
    assert parse_exif_datetime("2024:06:01 10:30:00") == datetime(2024, 6, 1, 10, 30)


def test_timestamp_priority_exif_then_mtime_then_none():
    exif = Image.Exif()
    exif[0x0132] = "2024:06:01 10:30:00"
    meta = extract_metadata(exif, 10, 10, mtime_ns=1_700_000_000_000_000_000)
    assert (meta.exif_ts, meta.ts_source) == ("2024-06-01T10:30:00", TS_EXIF_DATETIME)

    meta = extract_metadata(Image.Exif(), 10, 10, mtime_ns=1_700_000_000_000_000_000)
    assert meta.ts_source == TS_FILE_MTIME and meta.exif_ts is not None

    meta = extract_metadata(Image.Exif(), 10, 10, mtime_ns=None)
    assert meta.ts_source == TS_NONE and meta.exif_ts is None
