"""Tests for stability and architecture audit fixes."""

from pathlib import Path
import pytest
from engine.api import Engine
from engine.contract import API_VERSION
from services.pipeline.control import ProgressEvent


def test_api_version_is_1_2_0() -> None:
    assert API_VERSION == "1.2.0"


def test_tolerant_config_mode(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("bogus_unknown_key = 12345\n", encoding="utf-8")

    # Strict mode should raise EngineError
    with pytest.raises(Exception):
        Engine(tmp_path, strict_config=True)

    # Tolerant mode should open cleanly with warnings recorded
    eng = Engine(tmp_path, strict_config=False)
    assert len(eng.config_warnings) > 0
    assert "bogus_unknown_key" in eng.config_warnings[0]


def test_engine_on_event_property(tmp_path: Path) -> None:
    events = []
    eng = Engine(tmp_path)
    assert eng.on_event is None

    eng.on_event = lambda ev: events.append(ev)
    assert eng.on_event is not None
    eng.control.emit(ProgressEvent(stage="test", done=1, total=1))
    assert len(events) == 1
    assert events[0].stage == "test"


def test_faces_for_images_and_name_face(tmp_path: Path) -> None:
    with Engine(tmp_path) as eng:
        eng.db.register_files([(str(tmp_path / "photo.jpg"), 100, 1000)])
        img_id = 1
        eng.db.save_results(
            [
                {
                    "image_id": img_id,
                    "width": 800,
                    "height": 600,
                    "faces": [
                        {
                            "x": 10,
                            "y": 10,
                            "w": 50,
                            "h": 50,
                            "confidence": 0.95,
                            "embedding": b"\x00" * 512,
                        }
                    ],
                }
            ]
        )

        # Batch faces lookup
        faces_map = eng.get_faces_many([img_id])
        assert img_id in faces_map
        assert len(faces_map[img_id]) == 1
        face_id = faces_map[img_id][0]["id"]
        assert faces_map[img_id][0]["person_name"] is None

        # Name face
        pid = eng.name_face(face_id, "Alice Smith")
        assert pid > 0

        # Verify updated lookup
        faces_map2 = eng.get_faces_many([img_id])
        assert faces_map2[img_id][0]["person_name"] == "Alice Smith"
        assert faces_map2[img_id][0]["locked"] == 1


def test_reset_workspace(tmp_path: Path) -> None:
    with Engine(tmp_path) as eng:
        eng.db.register_files([(str(tmp_path / "pic.jpg"), 10, 1)])
        eng.db.save_results(
            [
                {
                    "image_id": 1,
                    "width": 100,
                    "height": 100,
                    "faces": [],
                }
            ]
        )
        assert eng.db.report_stats()["total_images"] == 1

        # Create a mock cache file
        cache_file = eng.settings.generated_dir / "test.cache"
        cache_file.write_text("cache", encoding="utf-8")
        assert cache_file.exists()

        res = eng.reset_workspace(keep_generated=False)
        assert res["cleared_images"] == 1
        assert eng.db.report_stats()["total_images"] == 0
        assert not cache_file.exists()
