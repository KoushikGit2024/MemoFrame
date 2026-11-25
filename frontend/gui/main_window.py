"""Main application window for MemoFrame Desktop."""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from config import DEFAULT_WORKSPACE
from engine import Engine
from gui.components.nav_rail import NavigationRail
from gui.state import AppState
from gui.theme_manager import THEMES, build_stylesheet, set_active_theme
from gui.views.detail_dialog import PhotoDetailDialog
from gui.views.duplicates_view import DuplicatesView
from gui.views.gallery_view import GalleryView
from gui.views.people_view import PeopleView
from gui.views.settings_view import SettingsView
from gui.views.timeline_view import TimelineView


class MemoFrameMainWindow(QMainWindow):
    """MemoFrame photographic workspace main window."""

    def __init__(self, workspace: Path | None = None) -> None:
        super().__init__()
        self.workspace = Path(workspace or DEFAULT_WORKSPACE).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.engine = Engine(self.workspace).open()
        self.engine_lock = threading.RLock()
        self.state = AppState(self)

        self.setWindowTitle(f"MemoFrame — Local Photo & Face Intelligence [{self.workspace}]")
        self.setMinimumSize(960, 640)
        self.resize(1340, 860)

        self._build_ui()
        self._connect_signals()

        # Apply initial theme & initial load
        self.apply_theme(self.state.current_theme)
        self.gallery_view.reload_persons()
        self.gallery_view.reload_data()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Left Navigation Rail (with integrated Theme Toggler)
        self.nav_rail = NavigationRail(self)
        layout.addWidget(self.nav_rail)

        # 2. Main View Stack
        self.view_stack = QStackedWidget(self)

        self.gallery_view = GalleryView(self.state, self.engine, self.engine_lock)
        self.people_view = PeopleView(self.state, self.engine, self.engine_lock)
        self.duplicates_view = DuplicatesView(self.state, self.engine, self.engine_lock)
        self.timeline_view = TimelineView(self.state, self.engine, self.engine_lock)
        self.settings_view = SettingsView(self.state, self.engine, self.engine_lock)

        self.view_stack.addWidget(self.gallery_view)       # Index 0: photos
        self.view_stack.addWidget(self.people_view)        # Index 1: people
        self.view_stack.addWidget(self.duplicates_view)    # Index 2: duplicates
        self.view_stack.addWidget(self.timeline_view)      # Index 3: timeline
        self.view_stack.addWidget(self.settings_view)      # Index 4: settings

        layout.addWidget(self.view_stack, stretch=1)

    def _connect_signals(self) -> None:
        self.nav_rail.tab_selected.connect(self._on_tab_changed)
        self.nav_rail.theme_selected.connect(self.state.set_theme)
        self.nav_rail.light_dark_toggled.connect(self.state.toggle_light_dark)

        self.state.view_changed.connect(self._on_tab_changed)
        self.state.theme_changed.connect(self.apply_theme)
        self.state.data_invalidated.connect(self.gallery_view.reload_persons)

        self.gallery_view.photo_opened.connect(self._open_lightbox)
        self.timeline_view.photo_opened.connect(self._open_lightbox)
        self.duplicates_view.photo_opened.connect(self._open_lightbox)

    def _on_tab_changed(self, tab_key: str) -> None:
        mapping = {
            "photos": (0, lambda: self.gallery_view.reload_data(reset_page=False)),
            "people": (1, self.people_view.reload_data),
            "duplicates": (2, self.duplicates_view.reload_data),
            "timeline": (3, self.timeline_view.reload_data),
            "settings": (4, self.settings_view.refresh_stats),
        }
        if tab_key in mapping:
            idx, refresh_fn = mapping[tab_key]
            self.view_stack.setCurrentIndex(idx)
            self.nav_rail.set_active(tab_key)
            refresh_fn()

    def _open_lightbox(self, photo_data: dict[str, Any]) -> None:
        dlg = PhotoDetailDialog(photo_data, self.engine, self.engine_lock, self)
        dlg.exec()

    def apply_theme(self, theme_name: str) -> None:
        if theme_name in THEMES:
            self.state.current_theme = theme_name
            if theme_name != "Light Canvas":
                self.state.last_dark_theme = theme_name
            palette = set_active_theme(theme_name)
            qss = build_stylesheet(palette)
            self.setStyleSheet(qss)
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(qss)
            self.nav_rail.set_theme(theme_name)
            if hasattr(self, "settings_view"):
                self.settings_view._sync_theme_controls(theme_name)

    def closeEvent(self, event) -> None:
        with self.engine_lock:
            try:
                self.engine.close()
            except Exception:
                pass
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    window = MemoFrameMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
