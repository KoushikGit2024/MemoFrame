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

from gui.main_window import MemoFrameMainWindow
from gui.prefs import Prefs


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])
    return app


def test_prefs_roundtrip(tmp_path):
    Prefs(tmp_path).set("theme", "Cyber Amber")
    assert Prefs(tmp_path).get("theme") == "Cyber Amber"


def test_theme_is_remembered(qapp, tmp_path):
    ws = tmp_path / "w"
    ws.mkdir()
    win = MemoFrameMainWindow(workspace=ws)
    win.apply_theme("Emerald Forest")
    win.close()
    win2 = MemoFrameMainWindow(workspace=ws)
    assert win2.state.current_theme == "Emerald Forest"
    win2.close()


def test_bursts_tab_exists(qapp, tmp_path):
    ws = tmp_path / "w2"
    ws.mkdir()
    win = MemoFrameMainWindow(workspace=ws)
    win._on_tab_changed("bursts")
    assert win.view_stack.currentIndex() == 5
    win.close()
