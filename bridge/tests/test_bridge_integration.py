"""Regression tests for real backend/database/settings_file + bridge integration."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from bridge.server import _find_backend_dir
from database.db_manager import DatabaseManager


def _load_backend_module(name: str, rel_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, BACKEND_DIR / rel_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_find_backend_dir_resolves_sibling_backend() -> None:
    found = _find_backend_dir()
    assert found is not None
    assert found.resolve() == BACKEND_DIR.resolve()


def test_update_config_file_atomic_and_reload(tmp_path: Path) -> None:
    if "engine" not in sys.modules:
        pkg = ModuleType("engine")
        pkg.__path__ = [str(BACKEND_DIR / "engine")]  # type: ignore[attr-defined]
        sys.modules["engine"] = pkg
    _load_backend_module("engine.errors", "engine/errors.py")
    _load_backend_module("engine.profiles", "engine/profiles.py")
    sf = _load_backend_module("engine.settings_file", "engine/settings_file.py")

    updated = sf.update_config_file(tmp_path, tagging_enabled=True, store_embeddings=True)
    assert updated == {"tagging_enabled": True, "store_embeddings": True}

    settings = sf.load_settings(tmp_path, strict=True)
    assert settings.tagging_enabled is True
    assert settings.store_embeddings is True

    sf.update_config_file(tmp_path, tagging_enabled=False)
    reloaded = sf.load_settings(tmp_path, strict=True)
    assert reloaded.tagging_enabled is False
    assert reloaded.store_embeddings is True


def test_db_sorts_and_failed_images_include_id(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "photos.db").open()
    try:
        db.register_files([
            (str(tmp_path / "a.jpg"), 100, 1),
            (str(tmp_path / "b.jpg"), 500, 2),
            (str(tmp_path / "c.jpg"), 300, 3),
        ])
        pending = db.fetch_pending(10)
        ids = {Path(r["path"]).name: int(r["id"]) for r in pending}
        img1, img2, img3 = ids["a.jpg"], ids["b.jpg"], ids["c.jpg"]

        db.save_results([
            {"image_id": img1, "sha256": "s1", "width": 100, "height": 100, "faces": [{"x": 0, "y": 0, "w": 10, "h": 10, "confidence": 0.9}]},
            {"image_id": img2, "sha256": "s2", "width": 100, "height": 100, "faces": []},
        ])
        db.save_failures([(img3, "decode error")])

        assert [r["id"] for r in db.find_images(sort="path_desc")] == [img2, img1]
        assert [r["id"] for r in db.find_images(sort="size_asc")] == [img1, img2]
        assert [r["id"] for r in db.find_images(sort="faces")] == [img1, img2]

        failed = db.failed_images()
        assert len(failed) == 1
        assert failed[0]["id"] == img3
        assert failed[0]["error"] == "decode error"
    finally:
        db.close()
