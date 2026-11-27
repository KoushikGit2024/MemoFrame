"""Phase H: workspace lock, API contract, diagnostics, bundled model, runner encoding."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from memoframe_engine.api import API_VERSION, Engine, EngineError, ErrorCode
from memoframe_engine.core.contract import describe
from memoframe_engine.utils.model_downloader import install_bundled_model

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTED = [
    "scan",
    "process",
    "run_all",
    "analyze_existing",
    "rebuild",
    "cancel",
    "pause",
    "resume",
    "find",
    "count",
    "timeline",
    "search",
    "get_image",
    "get_faces",
    "get_groups",
    "get_group_images",
    "get_duplicate_clusters",
    "get_bursts",
    "get_burst_images",
    "failed_images",
    "live_video",
    "low_confidence_faces",
    "stats",
    "save_search",
    "list_saved_searches",
    "run_saved_search",
    "delete_saved_search",
    "set_mark",
    "clear_mark",
    "get_marks",
    "suspicious_dates",
    "set_date_override",
    "clear_date_override",
    "moves",
    "check_files",
    "forget_missing",
    "thumbnail",
    "cache_info",
    "clear_cache",
    "maintenance",
    "repair",
    "doctor",
    "export_diagnostics",
    "watch",
    "tag_existing",
    "get_tags",
    "list_tags",
    "similar",
    "rescan",
    "recognize_existing",
    "get_persons",
    "get_person",
    "rename_person",
    "get_person_faces",
    "get_unassigned_faces",
    "assign_face",
    "create_person",
    "merge_persons",
    "confirm_person",
    "unlock_face",
]


def test_second_engine_on_same_workspace_is_refused(settings):
    with Engine(settings.workspace, settings=settings):
        with pytest.raises(EngineError) as err:
            Engine(settings.workspace, settings=settings).open()
        assert err.value.code == ErrorCode.WORKSPACE_LOCKED
    with Engine(settings.workspace, settings=settings):  # released on close
        pass


def test_documented_methods_exist_and_version_is_semver():
    missing = [m for m in DOCUMENTED if not callable(getattr(Engine, m, None))]
    assert missing == []
    assert len(API_VERSION.split(".")) == 3 and all(p.isdigit() for p in API_VERSION.split("."))
    assert set(DOCUMENTED) <= set(describe(Engine)["methods"])


def test_diagnostics_bundle_has_no_photos(settings, tmp_path):
    settings.ensure_dirs()
    (settings.thumbnails_dir / "t.jpg").write_bytes(b"jpeg")
    settings.log_path.write_text("log line\n", encoding="utf-8")
    with Engine(settings.workspace, settings=settings) as eng:
        path = Path(eng.export_diagnostics())
    assert path.parent == settings.workspace / "diagnostics"
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert {"info.json", "doctor.json", "stats.json", "settings.json"} <= set(names)
        assert not any(n.lower().endswith((".jpg", ".png", ".heic")) for n in names)
        assert json.loads(z.read("info.json"))["api_version"] == API_VERSION
        assert b"log line" in z.read("photo_organizer.log.tail")


def test_bundled_model_installed_once(settings, tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / settings.yunet_path.name).write_bytes(b"x" * 20_000)
    monkeypatch.setenv("PHOTO_ORGANIZER_BUNDLED_MODELS", str(bundle))
    assert install_bundled_model(settings.yunet_path) is True
    assert settings.yunet_path.stat().st_size == 20_000
    assert install_bundled_model(settings.yunet_path) is False


def _run(*args):
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{str(ROOT)}{os.pathsep}{env.get('PYTHONPATH', '')}"
    return subprocess.run(
        [sys.executable, "-m", "memoframe_engine", *args], cwd=ROOT, env=env, capture_output=True, timeout=120
    )


def test_runner_version_and_utf8_output(tmp_path):
    out = json.loads(_run("version").stdout.decode("utf-8").splitlines()[-1])
    assert out["type"] == "version" and out["api_version"] == API_VERSION
    ws = tmp_path / "ছবি_фото"
    proc = _run("doctor", "--workspace", str(ws))
    last = json.loads(proc.stdout.decode("utf-8").splitlines()[-1])  # must decode as UTF-8
    assert proc.returncode == 0 and last["type"] == "doctor"
    assert any("ছবি_фото" in c["detail"] for c in last["checks"])
