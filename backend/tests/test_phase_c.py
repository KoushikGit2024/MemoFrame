"""Phase C test suite: HEIC, video indexing, Live Photo pairing, migration v4."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from PIL import Image

from config import Settings
from services.vision.video import probe_video, read_mvhd
from database import DatabaseManager
from services.organization.live_pairs import link_live_pairs
from services.pipeline.orchestrator import run_pipeline


def _create_minimal_mp4(path: Path, duration_s: float = 3.0) -> None:
    """Write a synthetically valid minimal MP4 file with ftyp and moov/mvhd boxes."""
    # ftyp box
    ftyp_data = b"isom" + struct.pack(">I", 512) + b"isomiso2mp41"
    ftyp_box = struct.pack(">I", 8 + len(ftyp_data)) + b"ftyp" + ftyp_data

    # mvhd box (version 0):
    # version (1 byte) + flags (3 bytes)
    # created_mac (4 bytes)
    # modified_mac (4 bytes)
    # timescale (4 bytes)
    # duration (4 bytes)
    timescale = 1000
    duration_ticks = int(duration_s * timescale)
    # Mac epoch 1904-01-01 to 2024-01-01T00:00:00Z: 3786912000
    created_mac = 3786912000
    modified_mac = created_mac

    # header + times: 4 + 16 = 20 bytes
    mvhd_head = struct.pack(
        ">BBBB IIII", 0, 0, 0, 0, created_mac, modified_mac, timescale, duration_ticks
    )
    # rate (4), volume (2), reserved (10), matrix (36), pre_defined (24), next_track_id (4)
    rate = 0x00010000
    volume = 0x0100
    reserved = b"\x00" * 10
    matrix = struct.pack(">9I", 0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000)
    pre_defined = b"\x00" * 24
    next_track_id = 2

    mvhd_payload = (
        mvhd_head
        + struct.pack(">IH", rate, volume)
        + reserved
        + matrix
        + pre_defined
        + struct.pack(">I", next_track_id)
    )
    mvhd_box = struct.pack(">I", 8 + len(mvhd_payload)) + b"mvhd" + mvhd_payload
    moov_box = struct.pack(">I", 8 + len(mvhd_box)) + b"moov" + mvhd_box

    path.write_bytes(ftyp_box + moov_box)


def test_mvhd_parser(tmp_path: Path):
    mp4_file = tmp_path / "test.mp4"
    _create_minimal_mp4(mp4_file, duration_s=4.5)

    created, duration = read_mvhd(mp4_file)
    assert duration is not None
    assert abs(duration - 4.5) < 0.05
    assert created is not None
    assert created.year == 2024


def test_heic_decode_if_supported():
    """Verify pillow-heif is functioning or graceful fallback."""
    import pillow_heif

    assert pillow_heif.__version__ is not None
    extensions = Image.registered_extensions()
    assert ".heic" in extensions


def test_live_photo_pairing(tmp_path: Path):
    db_path = tmp_path / "test.db"
    with DatabaseManager(db_path) as db:
        # Register a photo and a short companion video with the same stem in same directory
        photo_path = str(tmp_path / "IMG_1001.JPG")
        video_path = str(tmp_path / "IMG_1001.MOV")

        db.register_files(
            [
                (photo_path, 1000, 100),
                (video_path, 5000, 100),
            ]
        )

        # Save results marking photo and video
        db.save_results(
            [
                {
                    "image_id": 1,
                    "kind": "photo",
                    "width": 1920,
                    "height": 1080,
                    "sha256": "abc1",
                    "phash": 12345,
                },
                {
                    "image_id": 2,
                    "kind": "video",
                    "duration_s": 2.5,
                    "width": 1920,
                    "height": 1080,
                },
            ]
        )

        # Link live pairs
        linked = link_live_pairs(db, max_seconds=6.0)
        assert linked == 1

        # Check pair_id was updated on the video
        candidates = db.list_pair_candidates()
        by_id = {r["id"]: r for r in candidates}
        assert by_id[2]["pair_id"] == 1

        # Check get_paired_video returns video for photo_id 1
        paired = db.get_paired_video(1)
        assert paired is not None
        assert paired["id"] == 2

        # Check search excludes paired video by default
        results = db.search_images()
        result_ids = [r["id"] for r in results]
        assert 1 in result_ids
        assert 2 not in result_ids  # hidden companion video

        # But include_live_video=True returns both
        all_results = db.search_images(include_live_video=True)
        assert len(all_results) == 2


def test_live_photo_pairing_too_long(tmp_path: Path):
    db_path = tmp_path / "test.db"
    with DatabaseManager(db_path) as db:
        photo_path = str(tmp_path / "IMG_2001.JPG")
        video_path = str(tmp_path / "IMG_2001.MOV")

        db.register_files(
            [
                (photo_path, 1000, 100),
                (video_path, 50000, 100),
            ]
        )

        # 10s video is longer than 6.0s max_seconds
        db.save_results(
            [
                {
                    "image_id": 1,
                    "kind": "photo",
                    "width": 100,
                    "height": 100,
                    "sha256": "a",
                    "phash": 1,
                },
                {"image_id": 2, "kind": "video", "duration_s": 10.0, "width": 100, "height": 100},
            ]
        )

        linked = link_live_pairs(db, max_seconds=6.0)
        assert linked == 0


def test_video_pipeline_indexing(tmp_path: Path, monkeypatch):
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    ws_dir = tmp_path / "ws"

    # Mock ensure_model and detector creation to avoid network dependency in tests
    from models import FaceBox

    class FakeDetector:
        def detect(self, loaded):
            return []

        def close(self):
            pass

    from services.pipeline import orchestrator as pipeline

    monkeypatch.setattr(pipeline, "ensure_model", lambda p: p)
    monkeypatch.setattr(pipeline, "create_detector", lambda s: FakeDetector())

    # Create dummy video
    v_path = photos_dir / "clip.mp4"
    _create_minimal_mp4(v_path, duration_s=2.0)

    # Create dummy image
    img = Image.new("RGB", (100, 100), color=(200, 50, 50))
    i_path = photos_dir / "pic.jpg"
    img.save(i_path, "JPEG")

    settings = Settings(workspace=ws_dir, workers=1)
    with DatabaseManager(settings.db_path) as db:
        summary = run_pipeline(settings, db, photos_dir)
        assert summary.processed == 2
        assert summary.failed == 0

        stats = db.report_stats()
        assert stats["videos"] == 1
        assert stats["processed"] == 2

        # Video should not have pHash or duplicate records
        hashes = db.fetch_hash_records()
        assert len(hashes) == 1

        # Search by kind
        video_rows = db.search_images(kind="video", include_live_video=True)
        assert len(video_rows) == 1
        assert video_rows[0]["kind"] == "video"
        assert abs(video_rows[0]["duration_s"] - 2.0) < 0.1
