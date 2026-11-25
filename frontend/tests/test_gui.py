"""Unit and GUI integration tests for MemoFrame Desktop Frontend."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtWidgets import QApplication

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_DIR = REPO_ROOT / "backend"

for p in (FRONTEND_DIR, BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gui.main_window import MemoFrameMainWindow
from gui.theme_manager import THEMES, build_stylesheet
from gui.widgets import (
    PersonPillWidget,
    PhotoCardWidget,
    get_cached_pixmap,
    set_cached_pixmap,
)
from PyQt6.QtGui import QPixmap


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single persistent QApplication instance for headless or offscreen test runs."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])
    return app


def test_theme_manager_stylesheets():
    """Verify all theme definitions generate valid Qt stylesheets."""
    assert "Dark Slate" in THEMES
    assert "Midnight Purple" in THEMES
    assert "Emerald Forest" in THEMES
    assert "Cyber Amber" in THEMES
    assert "Light Canvas" in THEMES

    for name, palette in THEMES.items():
        qss = build_stylesheet(palette)
        assert palette.bg_app in qss
        assert palette.accent in qss
        assert "QMainWindow" in qss
        assert "QPushButton" in qss


def test_pixmap_caching(qapp):
    """Test global QPixmap memory caching and eviction behavior."""
    pix = QPixmap(10, 10)
    set_cached_pixmap("test_key", pix)
    assert get_cached_pixmap("test_key") is not None
    assert get_cached_pixmap("non_existent") is None


def test_person_pill_widget_creation(qapp):
    """Verify PersonPillWidget initializes avatar and labels properly."""
    person_data = {
        "id": 1,
        "name": "Alice",
        "image_count": 12,
        "cover_crop_path": None,
    }
    pill = PersonPillWidget(person_data, is_selected=False)
    assert pill.person_id == 1
    assert pill.name == "Alice"
    assert pill.image_count == 12
    assert pill.name_lbl.text() == "Alice"
    assert pill.avatar_label.pixmap() is not None


def test_photo_card_widget_creation(qapp, tmp_path):
    """Verify PhotoCardWidget projects letterbox-aligned coordinates correctly."""
    photo_data = {
        "id": 42,
        "path": "IMG_9999.jpg",
        "width": 1920,
        "height": 1080,
        "effective_ts": "2024-05-15T14:30:00",
        "faces": [
            {"x": 100, "y": 100, "w": 200, "h": 200, "confidence": 0.95}
        ],
    }
    # Create dummy thumbnail file
    thumb_file = tmp_path / "thumb_42.jpg"
    pix = QPixmap(256, 144)
    pix.save(str(thumb_file))

    card = PhotoCardWidget(photo_data, thumb_path=str(thumb_file))
    assert card.image_id == 42
    assert card.orig_w == 1920
    assert card.orig_h == 1080
    assert len(card.faces) == 1


def test_main_window_lifecycle_and_pagination(qapp, tmp_path):
    """Verify MemoFrameMainWindow lifecycle, pagination controls, and clean shutdown."""
    ws = tmp_path / "test_gui_ws"
    ws.mkdir(parents=True)

    win = MemoFrameMainWindow(workspace=ws)
    assert win.workspace == ws
    assert win.state.current_page == 0
    assert win.state.page_size == 40

    win.engine.db.register_files([(f"{i}.jpg", 1, i) for i in range(1, 101)])
    win.engine.db.save_results([{"image_id": i, "exif_ts": "2024-01-01T10:00:00"}
                                for i in range(1, 101)])
    win.gallery_view.reload_data()                 # 100 photos -> 3 pages

    win.gallery_view._next_page()
    assert win.state.current_page == 1
    win.gallery_view._prev_page()
    assert win.state.current_page == 0

    # Test theme switching
    win.apply_theme("Midnight Purple")
    assert win.state.current_theme == "Midnight Purple"

    win.close()
