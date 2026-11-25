"""CLI parsing, error handling, reset, prune and report files (fake detector, no network)."""

from __future__ import annotations

import json
import os

import pytest

from cli import build_parser, main
from models import FaceBox
from database import DatabaseManager
from services.pipeline import orchestrator as pipeline
from utils.logger import setup_logging


@pytest.fixture(autouse=True)
def _close_log_handlers():
    yield
    setup_logging(None)  # closes the log file so Windows can clean up temp dirs


class FakeDetector:
    def detect(self, loaded):
        return [FaceBox(10, 10, 40, 40, 0.9)]

    def close(self):
        pass


@pytest.fixture
def fake_detector(monkeypatch):
    monkeypatch.setattr(pipeline, "create_detector", lambda settings: FakeDetector())
    monkeypatch.setattr(pipeline, "ensure_model", lambda path: path)


@pytest.fixture
def photos(tmp_path, make_image):
    root = tmp_path / "photos"
    make_image(root / "a.jpg", seed=1)
    make_image(root / "b.jpg", seed=2)
    return root


def run(*args):
    return main([str(a) for a in args])


# ---- parsing ---------------------------------------------------------------
def test_defaults_and_overrides_parse():
    ns = build_parser().parse_args(["process", "--workers", "2", "--confidence", "0.5"])
    assert (ns.command, ns.workers, ns.confidence, ns.input) == ("process", 2, 0.5, None)


@pytest.mark.parametrize(
    "argv",
    [
        ["scan"],  # --input is required
        ["scan", "--input", "definitely/not/here"],  # directory must exist
        ["process", "--confidence", "1.5"],
        ["process", "--workers", "0"],
        ["duplicates", "--near-threshold", "17"],
        ["search", "--from", "June 2024"],
        ["nonsense"],
    ],
)
def test_invalid_arguments_exit_with_usage_error(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(argv)
    assert exc.value.code == 2


def test_command_without_database_gives_clean_error(tmp_path, capsys):
    assert run("report", "--workspace", tmp_path / "none") == 1
    assert "No database" in capsys.readouterr().err


# ---- end to end through the CLI -----------------------------------------------
def test_scan_process_report_search(tmp_path, photos, fake_detector, capsys):
    ws = tmp_path / "ws"
    assert run("scan", "--input", photos, "--workspace", ws) == 0
    assert "2 new" in capsys.readouterr().out

    assert run("process", "--workspace", ws, "--workers", 1, "-q") == 0
    assert "Processed 2, failed 0, remaining 0" in capsys.readouterr().out

    assert run("report", "--workspace", ws) == 0
    out = capsys.readouterr().out
    assert "Successfully processed:         2" in out
    reports = sorted((ws / "reports").glob("report_*.json"))
    stats = json.loads(reports[-1].read_text(encoding="utf-8"))["stats"]
    assert (stats["processed"], stats["total_faces"]) == (2, 2)
    dup_csv = sorted((ws / "reports").glob("duplicates_*.csv"))[-1]
    assert dup_csv.read_bytes().startswith(b"\xef\xbb\xbf")  # UTF-8 BOM for Excel

    assert run("search", "--workspace", ws, "--min-faces", 1) == 0
    assert "2 result(s)" in capsys.readouterr().out
    assert run("search", "--workspace", ws, "--min-faces", 2) == 0
    assert "0 result(s)" in capsys.readouterr().out


# ---- reset ---------------------------------------------------------------------
def _populated_workspace(tmp_path, photos, fake_detector):
    ws = tmp_path / "ws"
    assert run("process", "--input", photos, "--workspace", ws, "--workers", 1, "-q") == 0
    (ws / "models").mkdir(exist_ok=True)
    (ws / "models" / "keep.onnx").write_bytes(b"x")
    return ws


def test_reset_clears_db_and_outputs_but_keeps_models_and_photos(tmp_path, photos, fake_detector):
    ws = _populated_workspace(tmp_path, photos, fake_detector)
    assert any((ws / "thumbnails").rglob("*.jpg"))
    assert run("reset", "--workspace", ws, "--yes") == 0
    assert not any((ws / "thumbnails").rglob("*.jpg"))
    assert not any((ws / "face_crops").rglob("*.jpg"))
    assert (ws / "models" / "keep.onnx").is_file()
    assert sorted(p.name for p in photos.iterdir()) == ["a.jpg", "b.jpg"]
    with DatabaseManager(ws / "photos.db") as db:
        assert db.report_stats()["total_images"] == 0


def test_reset_cancelled_keeps_everything(tmp_path, photos, fake_detector, monkeypatch):
    ws = _populated_workspace(tmp_path, photos, fake_detector)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")
    assert run("reset", "--workspace", ws) == 1
    with DatabaseManager(ws / "photos.db") as db:
        assert db.report_stats()["total_images"] == 2


def test_reset_db_only_keeps_generated_files(tmp_path, photos, fake_detector):
    ws = _populated_workspace(tmp_path, photos, fake_detector)
    assert run("reset", "--workspace", ws, "--yes", "--db-only") == 0
    assert any((ws / "thumbnails").rglob("*.jpg"))
    with DatabaseManager(ws / "photos.db") as db:
        assert db.report_stats()["total_images"] == 0


# ---- prune via CLI -----------------------------------------------------------------
def test_prune_dry_run_then_confirmed(tmp_path, photos, fake_detector, capsys):
    ws = _populated_workspace(tmp_path, photos, fake_detector)
    (photos / "b.jpg").unlink()
    capsys.readouterr()

    assert run("prune", "--workspace", ws, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "1 missing" in out and "Dry run" in out
    with DatabaseManager(ws / "photos.db") as db:
        assert db.report_stats()["total_images"] == 2

    assert run("prune", "--workspace", ws, "--yes") == 0
    with DatabaseManager(ws / "photos.db") as db:
        assert db.report_stats()["total_images"] == 1
    assert (photos / "a.jpg").is_file()


def test_prune_declined_removes_nothing(tmp_path, photos, fake_detector, monkeypatch):
    ws = _populated_workspace(tmp_path, photos, fake_detector)
    (photos / "b.jpg").unlink()
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert run("prune", "--workspace", ws) == 1
    with DatabaseManager(ws / "photos.db") as db:
        assert db.report_stats()["total_images"] == 2
