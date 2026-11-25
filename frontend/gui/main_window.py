"""Main application window for MemoFrame Desktop."""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from config import DEFAULT_WORKSPACE
from engine import Engine, EngineError
from gui.components.nav_rail import NavigationRail
from gui.prefs import Prefs
from gui.progress import StageProgress
from gui.state import AppState
from gui.theme_manager import THEMES, build_stylesheet, set_active_theme
from gui.views.bursts_view import BurstsView
from gui.views.detail_dialog import PhotoDetailDialog
from gui.views.duplicates_view import DuplicatesView
from gui.views.gallery_view import GalleryView
from gui.views.people_view import PeopleView
from gui.views.settings_view import SettingsView
from gui.views.timeline_view import TimelineView


class ScanWorker(QThread):
    """Background worker for folder scanning and processing with progress updates."""

    progress = pyqtSignal(object)
    finished_success = pyqtSignal()
    finished_error = pyqtSignal(str)

    def __init__(self, engine: Engine, folder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.folder = folder

    def run(self) -> None:
        try:
            self.engine.on_event = lambda ev: self.progress.emit(ev)
            self.engine.run_all(self.folder)
            self.finished_success.emit()
        except Exception as exc:
            self.finished_error.emit(str(exc))


class MemoFrameMainWindow(QMainWindow):
    """MemoFrame photographic workspace main window."""

    def __init__(self, workspace: Path | None = None) -> None:
        super().__init__()
        self.workspace = Path(workspace or DEFAULT_WORKSPACE).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.engine = Engine(self.workspace, strict_config=False).open()
        self.engine_lock = threading.RLock()
        self.state = AppState(self)
        self.prefs = Prefs(self.workspace)
        saved = self.prefs.get("theme")
        if saved in THEMES:
            self.state.current_theme = saved
        dark = self.prefs.get("last_dark_theme")
        if dark in THEMES and dark != "Light Canvas":
            self.state.last_dark_theme = dark
        self.stage_progress = StageProgress()

        self.setWindowTitle(f"MemoFrame — Local Photo & Face Intelligence [{self.workspace}]")
        self.setMinimumSize(960, 640)
        self.resize(1340, 860)

        self.scan_worker: ScanWorker | None = None
        self._build_ui()
        self._connect_signals()

        # Display config warnings if any occurred
        if self.engine.config_warnings:
            warn_msg = "\n".join(f"• {w}" for w in self.engine.config_warnings[:5])
            QMessageBox.warning(self, "Config Warnings", f"Settings had unknown or invalid entries:\n\n{warn_msg}")

        # Apply initial theme & initial load
        self.apply_theme(self.state.current_theme)
        self.gallery_view.reload_persons()
        self.gallery_view.reload_tags()
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
        self.bursts_view = BurstsView(self.state, self.engine, self.engine_lock)

        self.view_stack.addWidget(self.gallery_view)       # Index 0: photos
        self.view_stack.addWidget(self.people_view)        # Index 1: people
        self.view_stack.addWidget(self.duplicates_view)    # Index 2: duplicates
        self.view_stack.addWidget(self.timeline_view)      # Index 3: timeline
        self.view_stack.addWidget(self.settings_view)      # Index 4: settings
        self.view_stack.addWidget(self.bursts_view)        # Index 5: bursts

        layout.addWidget(self.view_stack, stretch=1)

        # Status Bar with Scan Controls & Progress Bar
        status_bar = self.statusBar()
        if status_bar is not None:
            self.btn_scan = QPushButton("Scan Folder...")
            self.btn_scan.setProperty("class", "Secondary")
            self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_scan.clicked.connect(self._prompt_scan_folder)
            status_bar.addWidget(self.btn_scan)

            self.btn_pause_scan = QPushButton("Pause")
            self.btn_pause_scan.setProperty("class", "Secondary")
            self.btn_pause_scan.setVisible(False)
            self.btn_pause_scan.clicked.connect(self._toggle_pause_scan)
            status_bar.addWidget(self.btn_pause_scan)

            self.btn_cancel_scan = QPushButton("Cancel")
            self.btn_cancel_scan.setProperty("class", "Secondary")
            self.btn_cancel_scan.setVisible(False)
            self.btn_cancel_scan.clicked.connect(self._cancel_scan)
            status_bar.addWidget(self.btn_cancel_scan)

            self.scan_progress_bar = QProgressBar()
            self.scan_progress_bar.setRange(0, 100)
            self.scan_progress_bar.setVisible(False)
            self.scan_progress_bar.setFixedWidth(200)
            status_bar.addWidget(self.scan_progress_bar)

            self.status_msg_lbl = QLabel("Ready")
            self.status_msg_lbl.setProperty("class", "Dim")
            status_bar.addWidget(self.status_msg_lbl)

    def _prompt_scan_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Photo Folder to Scan")
        if folder:
            self.start_scan(folder)

    def start_scan(self, folder: str) -> None:
        if self.scan_worker is not None and self.scan_worker.isRunning():
            QMessageBox.warning(self, "Scan in Progress", "A scan is already running.")
            return

        self.stage_progress.reset()
        self.btn_scan.setEnabled(False)
        self.btn_pause_scan.setText("Pause")
        self.btn_pause_scan.setVisible(True)
        self.btn_cancel_scan.setVisible(True)
        self.scan_progress_bar.setValue(0)
        self.scan_progress_bar.setVisible(True)
        self.status_msg_lbl.setText(f"Scanning {Path(folder).name}...")

        self.scan_worker = ScanWorker(self.engine, folder, self)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished_success.connect(self._on_scan_finished)
        self.scan_worker.finished_error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _toggle_pause_scan(self) -> None:
        if self.engine.control.paused:
            self.engine.control.resume()
            self.btn_pause_scan.setText("Pause")
            self.status_msg_lbl.setText("Resumed...")
        else:
            self.engine.control.pause()
            self.btn_pause_scan.setText("Resume")
            self.status_msg_lbl.setText("Paused")

    def _cancel_scan(self) -> None:
        self.engine.control.cancel()
        self.status_msg_lbl.setText("Cancelling scan...")

    def _on_scan_progress(self, ev: Any) -> None:
        ev_dict = ev.to_dict() if hasattr(ev, "to_dict") else (dict(ev) if isinstance(ev, dict) else {})
        stage = ev_dict.get("stage") or getattr(ev, "stage", "")
        done = ev_dict.get("done") or getattr(ev, "done", 0)
        total = ev_dict.get("total") or getattr(ev, "total", 0)
        current = ev_dict.get("current") or getattr(ev, "current", "") or ""
        msg = f"[{stage.upper()}] {done}/{total} {current}"
        self.status_msg_lbl.setText(msg)
        pct = self.stage_progress.update(ev_dict if ev_dict else {"stage": stage, "done": done, "total": total})
        self.scan_progress_bar.setValue(pct)

    def _on_scan_finished(self) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_pause_scan.setVisible(False)
        self.btn_cancel_scan.setVisible(False)
        self.scan_progress_bar.setVisible(False)
        self.status_msg_lbl.setText("Scan completed successfully.")
        self.state.invalidate()
        self.gallery_view.reload_persons()
        self.gallery_view.reload_tags()
        self.gallery_view.reload_data(reset_page=True)
        self.settings_view.refresh_stats()
        QMessageBox.information(self, "Scan Complete", "Finished scanning and organizing photos.")

    def _on_scan_error(self, err_msg: str) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_pause_scan.setVisible(False)
        self.btn_cancel_scan.setVisible(False)
        self.scan_progress_bar.setVisible(False)
        self.status_msg_lbl.setText(f"Scan failed: {err_msg}")
        QMessageBox.critical(self, "Scan Error", f"Scan failed: {err_msg}")

    def _connect_signals(self) -> None:
        self.nav_rail.tab_selected.connect(self._on_tab_changed)
        self.nav_rail.theme_selected.connect(self.state.set_theme)
        self.nav_rail.light_dark_toggled.connect(self.state.toggle_light_dark)
        self.state.view_changed.connect(self._on_tab_changed)
        self.state.theme_changed.connect(self.apply_theme)
        self.state.data_invalidated.connect(self.gallery_view.reload_persons)
        self.state.data_invalidated.connect(self.gallery_view.reload_tags)

        self.gallery_view.photo_opened.connect(self._open_lightbox)
        self.timeline_view.photo_opened.connect(self._open_lightbox)
        self.duplicates_view.photo_opened.connect(self._open_lightbox)
        self.bursts_view.photo_opened.connect(self._open_lightbox)

    def _on_tab_changed(self, tab_key: str) -> None:
        mapping = {
            "photos": (0, lambda: self.gallery_view.reload_data(reset_page=False)),
            "people": (1, self.people_view.reload_data),
            "duplicates": (2, self.duplicates_view.reload_data),
            "timeline": (3, self.timeline_view.reload_data),
            "settings": (4, self.settings_view.refresh_stats),
            "bursts": (5, self.bursts_view.reload_data),
        }
        if tab_key in mapping:
            idx, refresh_fn = mapping[tab_key]
            self.state.active_view = tab_key          # keep state in sync with nav clicks
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
            self.prefs.set("theme", theme_name)
            self.prefs.set("last_dark_theme", self.state.last_dark_theme)
            if hasattr(self, "settings_view"):
                self.settings_view._sync_theme_controls(theme_name)

    def closeEvent(self, event) -> None:
        if hasattr(self, "gallery_view"):
            self.gallery_view.shutdown()
        if hasattr(self, "settings_view"):
            self.settings_view.shutdown()
        with self.engine_lock:
            try:
                self.engine.close()
            except Exception:
                pass
        event.accept()


def main(workspace: Path | None = None) -> int:
    app = QApplication(sys.argv)
    try:
        window = MemoFrameMainWindow(workspace=workspace)
    except EngineError as e:
        logging.getLogger("photo_organizer.gui").error("Cannot open workspace: %s", e.to_dict())
        QMessageBox.critical(None, "Cannot open workspace", f"{e.message}\n\n{e.hint}")
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
