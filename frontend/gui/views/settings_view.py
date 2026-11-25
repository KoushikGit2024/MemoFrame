"""Settings, Theme Studio, Doctor Diagnostics, and Cache Maintenance View."""
from __future__ import annotations

import logging
import os
import subprocess
import threading

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from engine import Engine
from gui.safe_call import safe_call
from gui.state import AppState
from gui.tasks import EngineTask
from gui.theme_manager import THEMES, ThemePalette
from gui.views.date_dialogs import SuspiciousDatesDialog
from gui.views.failed_dialog import FailedImagesDialog
from gui.views.reset_dialog import ResetDialog
from gui.widgets import clear_pixmap_cache


class _ThemePreviewCard(QFrame):
    """Clickable visual palette card for instant theme switching."""

    clicked = pyqtSignal(str)

    def __init__(self, palette: ThemePalette, selected: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme_name = palette.name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(76)
        self.set_selected(selected)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Mini color swatches representing surface, card, and accent
        dots = QHBoxLayout()
        dots.setContentsMargins(0, 0, 0, 0)
        dots.setSpacing(6)
        for color in (palette.bg_app, palette.bg_card, palette.accent):
            dot = QLabel()
            dot.setFixedSize(16, 16)
            dot.setStyleSheet(
                f"background-color: {color}; border: 1px solid {palette.border}; border-radius: 8px;"
            )
            dots.addWidget(dot)
        dots.addStretch()

        mode_tag = QLabel("Light" if not palette.is_dark else "Dark")
        mode_tag.setProperty("class", "Dim")
        dots.addWidget(mode_tag)
        layout.addLayout(dots)

        name_lbl = QLabel(palette.name)
        name_lbl.setProperty("class", "CardTitle")
        layout.addWidget(name_lbl)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("class", "ThemeOptionCardSelected" if selected else "ThemeOptionCard")
        style = self.style()
        if style:
            style.unpolish(self)
            style.polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.theme_name)


class SettingsView(QWidget):
    """View managing Appearance themes, Workspace statistics, Doctor diagnostics, and Cache maintenance."""

    def __init__(self, state: AppState, engine: Engine, lock: threading.RLock, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.engine = engine
        self.lock = lock
        self._stat_values: dict[str, QLabel] = {}
        self._theme_cards: dict[str, _ThemePreviewCard] = {}
        self._task: EngineTask | None = None
        self._maint_buttons: list[QPushButton] = []
        self.maint_status = QLabel("")
        self.maint_status.setProperty("class", "Dim")
        self.maint_status.setWordWrap(True)

        self._build_ui()
        self.state.theme_changed.connect(self._sync_theme_controls)
        self.refresh_stats()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)

        # Page Header
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title = QLabel("Workspace & System Settings")
        title.setProperty("class", "PageTitle")
        title_block.addWidget(title)

        sub = QLabel("Personalize the interface palette, inspect workspace health, and manage cached thumbnails.")
        sub.setProperty("class", "PageSubtitle")
        title_block.addWidget(sub)
        layout.addLayout(title_block)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        outer_container = QWidget()
        outer_container.setObjectName("ScrollContainer")
        outer_layout = QHBoxLayout(outer_container)
        outer_layout.setContentsMargins(0, 4, 8, 12)
        outer_layout.setSpacing(0)

        # Constrained max-width column for clean modern web readability
        content_col = QWidget()
        content_col.setObjectName("ScrollContainer")
        content_col.setMaximumWidth(880)
        content_col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        c_box = QVBoxLayout(content_col)
        c_box.setContentsMargins(0, 0, 0, 0)
        c_box.setSpacing(16)

        # 1. Theme Configuration
        theme_card = self._create_card(
            "Appearance & Color Theme",
            "Switch instantly between dark studio palettes and Light Canvas.",
        )
        t_box = theme_card.layout()

        t_row = QHBoxLayout()
        t_row.setSpacing(10)
        lbl_palette = QLabel("Active Palette")
        lbl_palette.setProperty("class", "CardTitle")
        t_row.addWidget(lbl_palette)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setCurrentText(self.state.current_theme)
        self.theme_combo.setMinimumWidth(180)
        self.theme_combo.currentTextChanged.connect(self.state.set_theme)
        t_row.addWidget(self.theme_combo)

        self.btn_quick_toggle = QPushButton("Toggle Light / Dark")
        self.btn_quick_toggle.setProperty("class", "Secondary")
        self.btn_quick_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quick_toggle.clicked.connect(self.state.toggle_light_dark)
        t_row.addWidget(self.btn_quick_toggle)
        t_row.addStretch()
        t_box.addLayout(t_row)

        # Visual Theme Swatch Grid
        swatch_grid = QGridLayout()
        swatch_grid.setContentsMargins(0, 4, 0, 0)
        swatch_grid.setSpacing(10)
        for idx, (name, palette) in enumerate(THEMES.items()):
            card = _ThemePreviewCard(palette, selected=(name == self.state.current_theme))
            card.clicked.connect(self.state.set_theme)
            self._theme_cards[name] = card
            swatch_grid.addWidget(card, idx // 5, idx % 5)
        t_box.addLayout(swatch_grid)
        c_box.addWidget(theme_card)

        # 2. Workspace Health & Stats
        stats_card = self._create_card(
            "Workspace Statistics",
            "Live overview of indexed media, detected faces, duplicate clusters, and event groups.",
        )
        s_box = stats_card.layout()

        stat_grid = QGridLayout()
        stat_grid.setContentsMargins(0, 2, 0, 2)
        stat_grid.setSpacing(10)
        stat_defs = [
            ("total_images", "Total Photos"),
            ("total_faces", "Faces Detected"),
            ("duplicate_clusters", "Duplicate Clusters"),
            ("groups", "Event Groups"),
            ("videos", "Videos Indexed"),
        ]
        for idx, (key, label) in enumerate(stat_defs):
            tile = QFrame()
            tile.setProperty("class", "StatTile")
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(12, 10, 12, 10)
            tl.setSpacing(2)

            val_lbl = QLabel("0")
            val_lbl.setProperty("class", "StatValue")
            name_lbl = QLabel(label)
            name_lbl.setProperty("class", "StatLabel")
            tl.addWidget(val_lbl)
            tl.addWidget(name_lbl)

            self._stat_values[key] = val_lbl
            stat_grid.addWidget(tile, 0, idx)
        s_box.addLayout(stat_grid)

        self.stats_lbl = QLabel("Loading stats...")
        self.stats_lbl.setProperty("class", "Dim")
        self.stats_lbl.setWordWrap(True)
        s_box.addWidget(self.stats_lbl)
        c_box.addWidget(stats_card)

        # 3. Doctor Diagnostics
        doc_card = self._create_card(
            "Engine Doctor Health Check",
            "Verify database integrity, model availability, and workspace path consistency.",
        )
        d_box = doc_card.layout()

        d_row = QHBoxLayout()
        d_row.setSpacing(12)
        self.doc_btn = QPushButton("Run Diagnostic Health Check")
        self.doc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.doc_btn.clicked.connect(self._run_doctor)
        d_row.addWidget(self.doc_btn)
        d_row.addStretch()
        d_box.addLayout(d_row)

        self.doc_result = QLabel("")
        self.doc_result.setWordWrap(True)
        self.doc_result.setVisible(False)
        d_box.addWidget(self.doc_result)
        c_box.addWidget(doc_card)

        # 4. Cache & Thumbnail Management
        cache_card = self._create_card(
            "Cache Maintenance",
            "Remove orphaned thumbnails to reclaim local disk space without affecting original photos.",
        )
        ch_box = cache_card.layout()

        ch_row = QHBoxLayout()
        ch_row.setSpacing(12)
        btn_clean = QPushButton("Clean Stale Thumbnails & Reclaim Disk Space")
        btn_clean.setProperty("class", "Secondary")
        btn_clean.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clean.clicked.connect(self._clean_cache)
        ch_row.addWidget(btn_clean)

        btn_logs = QPushButton("Show Log File")
        btn_logs.setProperty("class", "Secondary")
        btn_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_logs.clicked.connect(self._open_logs)
        ch_row.addWidget(btn_logs)

        btn_diag = QPushButton("Export Diagnostics")
        btn_diag.setProperty("class", "Secondary")
        btn_diag.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_diag.clicked.connect(self._export_diag)
        ch_row.addWidget(btn_diag)

        ch_row.addStretch()
        ch_box.addLayout(ch_row)
        c_box.addWidget(cache_card)

        # 5. Scene Tags and Similar Photos
        c_box.addWidget(self._build_tags_card())

        # 6. Database & Maintenance
        maint_card = self._build_maintenance_card()
        c_box.addWidget(maint_card)

        # 7. Danger Zone: Reset Workspace
        reset_card = self._build_reset_card()
        c_box.addWidget(reset_card)

        c_box.addStretch()
        outer_layout.addWidget(content_col)
        outer_layout.addStretch()

        scroll.setWidget(outer_container)
        layout.addWidget(scroll, stretch=1)

    def _create_card(self, title_str: str, subtitle_str: str = "") -> QFrame:
        card = QFrame()
        card.setProperty("class", "Card")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(18, 16, 18, 16)
        vbox.setSpacing(10)

        hdr = QVBoxLayout()
        hdr.setSpacing(2)
        t = QLabel(title_str)
        t.setProperty("class", "AccentTitle")
        hdr.addWidget(t)
        if subtitle_str:
            s = QLabel(subtitle_str)
            s.setProperty("class", "PageSubtitle")
            s.setWordWrap(True)
            hdr.addWidget(s)
        vbox.addLayout(hdr)
        return card

    def _sync_theme_controls(self, theme_name: str) -> None:
        self.theme_combo.blockSignals(True)
        if theme_name in THEMES:
            self.theme_combo.setCurrentText(theme_name)
        self.theme_combo.blockSignals(False)

        for name, card in self._theme_cards.items():
            card.set_selected(name == theme_name)

    def refresh_stats(self) -> None:
        stats = safe_call(self, self.engine.stats, default={}) or {}

        for key, lbl in self._stat_values.items():
            lbl.setText(str(stats.get(key, 0)))

        text = (
            f"{stats.get('processed', 0)} of {stats.get('total_images', 0)} photos processed  ·  "
            f"{stats.get('images_with_faces', 0)} photos contain faces  ·  "
            f"{stats.get('duplicate_images', 0)} redundant copies detected"
        )
        self.stats_lbl.setText(text)

    def _run_doctor(self) -> None:
        report = safe_call(self, self.engine.doctor, default={}) or {}
        issues = [
            f"{c['name']}: {c['detail']}" + (f"  (fix: {c['fix']})" if c.get("fix") else "")
            for c in report.get("checks", [])
            if c.get("status") != "ok"
        ]
        self.doc_result.setVisible(True)
        if not issues:
            self.doc_result.setText("✓ All checks passed. Workspace and models are healthy.")
            self.doc_result.setProperty("class", "StatusHealthy")
        else:
            self.doc_result.setText(f"Found {len(issues)} issue(s):\n" + "\n".join(f"• {i}" for i in issues))
            self.doc_result.setProperty("class", "StatusIssue")
        style = self.doc_result.style()
        if style:
            style.unpolish(self.doc_result)
            style.polish(self.doc_result)

    def _clean_cache(self) -> None:
        res = safe_call(self, self.engine.clear_cache, default={}) or {}
        freed_mb = sum(res.values())
        QMessageBox.information(self, "Cache Cleaned", f"Reclaimed about {freed_mb} MB of thumbnail cache.")
        self.refresh_stats()

    def _open_logs(self) -> None:
        log_file = self.engine.settings.log_path
        if os.name == "nt" and log_file.is_file():
            subprocess.Popen(["explorer.exe", f"/select,{log_file}"])    # highlights the file
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_file.parent)))

    def _export_diag(self) -> None:
        path = safe_call(self, self.engine.export_diagnostics)
        if path:
            QMessageBox.information(self, "Diagnostics", f"Saved to:\n{path}")

    def _run_task(self, label: str, fn, on_done=None) -> None:
        if self._task is not None and self._task.isRunning():
            return
        self.maint_status.setText(f"{label}…")
        for b in self._maint_buttons:
            b.setEnabled(False)

        def success(res):
            self._task_end()
            if on_done:
                on_done(res)

        def failed(err):
            self._task_end()
            self.maint_status.setText(f"Failed: {err}")
            QMessageBox.critical(self, "Error", err)

        self._task = EngineTask(fn, parent=self)
        self._task.success.connect(success)
        self._task.failed.connect(failed)
        self._task.start()

    def _task_end(self) -> None:
        if self._task is not None:
            self._task.wait()
        for b in self._maint_buttons:
            b.setEnabled(True)
        self.maint_status.setText("")

    def shutdown(self) -> None:
        if self._task is not None and self._task.isRunning():
            self.engine.cancel()
            self._task.wait(15000)

    def _build_maintenance_card(self) -> QFrame:
        card = self._create_card(
            "Library & Record Maintenance",
            "Verify source photo files on disk, purge stale missing records, and repair database anomalies.",
        )
        box = card.layout()

        grid = QGridLayout()
        grid.setSpacing(10)
        buttons = (
            ("Verify Files", self._verify_files),
            ("Prune Missing Records", self._prune_missing),
            ("Detect Moved Files", self._detect_moves),
            ("Suspicious Dates…", self._suspicious_dates),
            ("Rebuild Groups and Index", self._rebuild),
            ("Repair and Optimize Database", self._repair_db),
            ("Failed Photos…", self._show_failed),
        )
        for i, (text, slot) in enumerate(buttons):
            b = QPushButton(text)
            b.setProperty("class", "Secondary")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            self._maint_buttons.append(b)
            grid.addWidget(b, i // 4, i % 4)
        box.addLayout(grid)
        box.addWidget(self.maint_status)
        return card

    def _build_tags_card(self) -> QFrame:
        card = self._create_card(
            "Scene Tags and Similar Photos",
            "Tags every processed photo with scene labels and enables 'Find Similar'. Needs "
            "tagging_enabled = true and store_embeddings = true in config.toml (restart afterwards) "
            "and the model files in workspace/models/tags/.",
        )
        row = QHBoxLayout()
        b = QPushButton("Tag Existing Photos")
        b.setProperty("class", "Secondary")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(self._tag_existing)
        self._maint_buttons.append(b)
        row.addWidget(b)
        row.addStretch()
        card.layout().addLayout(row)
        return card

    def _tag_existing(self) -> None:
        def done(res: dict) -> None:
            self.maint_status.setText(f"Tagged {res.get('tagged', 0)} photo(s).")
            self.state.invalidate()
        self._run_task("Tagging photos", self.engine.tag_existing, done)

    def _build_reset_card(self) -> QFrame:
        card = self._create_card(
            "Danger Zone: Reset Workspace",
            "Clear all indexed photos, faces, duplicates, and timeline data from this workspace. Original files are never touched.",
        )
        box = card.layout()

        row = QHBoxLayout()
        row.setSpacing(12)

        btn_reset = QPushButton("Reset Workspace Data...")
        btn_reset.setProperty("class", "Danger")
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._reset_workspace)
        row.addWidget(btn_reset)

        row.addStretch()
        box.addLayout(row)
        return card

    def _verify_files(self) -> None:
        def done(res: dict) -> None:
            QMessageBox.information(
                self,
                "Verification Complete",
                f"Checked {res.get('checked', 0)} files:\n"
                f"• {res.get('missing', 0)} missing\n"
                f"• {res.get('modified', 0)} modified",
            )
            self.refresh_stats()
        self._run_task("Verifying files", self.engine.verify_files, done)

    def _prune_missing(self) -> None:
        reply = QMessageBox.question(
            self,
            "Prune Missing Records",
            "This will remove database records for files that no longer exist on disk. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            def done(pruned: int) -> None:
                QMessageBox.information(self, "Prune Complete", f"Pruned {pruned} missing record(s).")
                self.refresh_stats()
                self.state.invalidate()
            self._run_task("Pruning missing records", self.engine.prune, done)

    def _detect_moves(self) -> None:
        def done(rows: list) -> None:
            self.maint_status.setText(
                f"{len(rows)} photo(s) were moved or renamed. Favourite/keep marks followed them."
                if rows
                else "No moved files found. (Scan the new location first, then run this again.)"
            )
        self._run_task("Looking for moved files", self.engine.moves, done)

    def _suspicious_dates(self) -> None:
        dlg = SuspiciousDatesDialog(self.engine, self.lock, self)
        dlg.exec()
        if dlg.changed:
            self._rebuild()

    def _rebuild(self) -> None:
        def done(res: dict) -> None:
            self.maint_status.setText(
                f"Rebuilt: {res.get('groups', 0)} groups, "
                f"{res.get('duplicate_clusters', 0)} duplicate clusters, "
                f"{res.get('persons', 0)} people."
            )
            self.state.invalidate()
            self.refresh_stats()
        self._run_task("Rebuilding groups and index", self.engine.rebuild, done)

    def _repair_db(self) -> None:
        def done(res: dict) -> None:
            QMessageBox.information(
                self,
                "Database Repair",
                f"Repair finished:\n"
                f"• Fixed face counts: {res.get('face_counts_fixed', 0)}\n"
                f"• Requeued pending: {res.get('requeued', 0)}\n"
                f"• Orphan faces removed: {res.get('orphan_faces_removed', 0)}",
            )
            self.refresh_stats()
        self._run_task("Repairing database", self.engine.repair, done)

    def _show_failed(self) -> None:
        dlg = FailedImagesDialog(self.engine, self)
        dlg.exec()

    def _reset_workspace(self) -> None:
        dlg = ResetDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sources, saved = dlg.clear_sources, dlg.clear_saved

        def done(res: dict) -> None:
            clear_pixmap_cache()
            self.state.select_person(None)
            self.state.invalidate()
            self.refresh_stats()
            QMessageBox.information(
                self,
                "Reset complete",
                f"Removed {res.get('images_removed', 0)} photo record(s).",
            )
        self._run_task(
            "Resetting",
            lambda: self.engine.reset_workspace(
                clear_sources=sources, clear_saved_searches=saved
            ),
            done,
        )
