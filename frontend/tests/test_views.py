"""Unit tests for new views, state, and navigation components."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest
from PyQt6.QtWidgets import QApplication

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_DIR = REPO_ROOT / "backend"

for p in (FRONTEND_DIR, BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gui.state import AppState
from gui.components.nav_rail import NavigationRail
from gui.components.photo_table import PhotoTableWidget
from gui.views.gallery_view import GalleryView
from gui.views.people_view import PeopleView
from gui.views.duplicates_view import DuplicatesView
from gui.views.timeline_view import TimelineView
from gui.views.settings_view import SettingsView
from gui.main_window import MemoFrameMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])
    return app


def test_app_state_signals(qapp):
    state = AppState()
    views = []
    state.view_changed.connect(views.append)
    state.set_view("duplicates")
    assert views == ["duplicates"]
    assert state.active_view == "duplicates"

    modes = []
    state.layout_mode_changed.connect(modes.append)
    state.set_layout_mode("compact")
    assert modes == ["compact"]
    assert state.layout_mode == "compact"


def test_nav_rail(qapp):
    rail = NavigationRail()
    tabs = []
    rail.tab_selected.connect(tabs.append)
    rail._on_tab_clicked("people")
    assert tabs == ["people"]
    assert rail.buttons["people"].isChecked()


def test_photo_table_widget(qapp):
    table = PhotoTableWidget()
    photos = [
        {"id": 1, "path": "test1.jpg", "effective_ts": "2024-01-01", "width": 800, "height": 600, "format": "jpg"}
    ]
    table.set_photos(photos)
    assert table.rowCount() == 1
    assert table.item(0, 1).text() == "test1.jpg"


def test_main_window_tabs_switching(qapp, tmp_path):
    ws = tmp_path / "test_tabs_ws"
    ws.mkdir(parents=True)
    win = MemoFrameMainWindow(workspace=ws)

    # Test tab transitions
    for tab, expected_idx in [("photos", 0), ("people", 1), ("duplicates", 2), ("timeline", 3), ("settings", 4)]:
        win._on_tab_changed(tab)
        assert win.view_stack.currentIndex() == expected_idx

    win.close()
