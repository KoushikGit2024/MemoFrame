"""Dedicated People Management View with Responsive Cards, Merging, and Renaming."""
from __future__ import annotations

import threading
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from engine import Engine
from gui.state import AppState
from gui.widgets import EmptyStateWidget, PersonPillWidget


class PeopleView(QWidget):
    """View managing identified people, name assignment, and merging clusters."""

    def __init__(self, state: AppState, engine: Engine, lock: threading.RLock, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.engine = engine
        self.lock = lock
        self.persons: list[dict[str, Any]] = []
        self._cards: list[QWidget] = []
        self._last_cols: int = 0

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)

        # Header Bar
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        self.title_lbl = QLabel("Identified People (0)")
        self.title_lbl.setProperty("class", "PageTitle")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()
        title_block.addLayout(title_row)

        sub = QLabel("Click a person to browse their photos, rename clusters, or merge duplicates.")
        sub.setProperty("class", "PageSubtitle")
        title_block.addWidget(sub)
        hdr.addLayout(title_block, stretch=1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by name...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(210)
        self.search_input.textChanged.connect(self._filter_persons)
        hdr.addWidget(self.search_input)

        btn_merge = QPushButton("Merge People")
        btn_merge.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_merge.clicked.connect(self._merge_dialog)
        hdr.addWidget(btn_merge)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "Secondary")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.clicked.connect(self.reload_data)
        hdr.addWidget(btn_refresh)
        layout.addLayout(hdr)

        # Responsive Scroll Area for People Grid (No Horizontal Scrollbar)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.container.setObjectName("ScrollContainer")
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(2, 4, 8, 8)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, stretch=1)

    def reload_data(self) -> None:
        with self.lock:
            self.persons = self.engine.get_persons()
        self.title_lbl.setText(f"Identified People ({len(self.persons)})")
        self._filter_persons()

    def _compute_columns(self) -> int:
        viewport_w = self.scroll.viewport().width()
        if viewport_w < 300:
            viewport_w = max(300, self.width() - 48)
        return max(1, (viewport_w - 16 + 14) // (300 + 14))

    def _filter_persons(self) -> None:
        query = self.search_input.text().strip().lower()
        self._cards.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filtered = [p for p in self.persons if query in p.get("name", "").lower()]
        if not filtered:
            for c in range(max(1, self._last_cols)):
                self.grid.setColumnStretch(c, 1 if c == 0 else 0)
            msg = "No people match that search query." if query else "No face clusters have been indexed in this workspace yet."
            empty = EmptyStateWidget("◎", "No People Found", msg)
            self.grid.addWidget(empty, 0, 0)
            self._last_cols = 1
            return

        cols = self._compute_columns()
        self._last_cols = cols
        for col in range(cols):
            self.grid.setColumnStretch(col, 1)

        for idx, p in enumerate(filtered):
            card = self._create_person_card(p)
            self._cards.append(card)
            self.grid.addWidget(card, idx // cols, idx % cols)

    def _reflow_cards(self) -> None:
        if not self._cards:
            return
        cols = self._compute_columns()
        if cols == self._last_cols:
            return
        for c in range(max(cols, self._last_cols)):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)
        self._last_cols = cols
        for card in self._cards:
            self.grid.removeWidget(card)
        for idx, card in enumerate(self._cards):
            self.grid.addWidget(card, idx // cols, idx % cols)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow_cards()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reflow_cards()

    def _create_person_card(self, person: dict[str, Any]) -> QFrame:
        card = QFrame()
        card.setProperty("class", "PersonRowCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.setMinimumWidth(260)

        c_layout = QHBoxLayout(card)
        c_layout.setContentsMargins(14, 12, 14, 12)
        c_layout.setSpacing(10)

        pill = PersonPillWidget(person, flat=True, avatar_size=44)
        pill.clicked.connect(lambda pid: self._view_person_photos(pid))
        pill.renamed.connect(self._rename_person)
        c_layout.addWidget(pill, stretch=1)

        btn_rename = QPushButton("Rename")
        btn_rename.setProperty("class", "Ghost")
        btn_rename.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rename.clicked.connect(lambda _, p=person: self._prompt_rename(p))
        c_layout.addWidget(btn_rename)

        btn_view = QPushButton("View")
        btn_view.setProperty("class", "Secondary")
        btn_view.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_view.setFixedWidth(64)
        btn_view.clicked.connect(lambda _, pid=person["id"]: self._view_person_photos(pid))
        c_layout.addWidget(btn_view)

        return card

    def _prompt_rename(self, person: dict[str, Any]) -> None:
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Person",
            f"Enter new name for {person.get('name', 'Person')}:",
            text=person.get("name", ""),
        )
        if ok and new_name.strip():
            self._rename_person(person["id"], new_name.strip())

    def _view_person_photos(self, person_id: int) -> None:
        self.state.select_person(person_id)
        self.state.set_view("photos")

    def _rename_person(self, person_id: int, new_name: str) -> None:
        with self.lock:
            self.engine.rename_person(person_id, new_name)
        self.reload_data()
        self.state.invalidate()

    def _merge_dialog(self) -> None:
        if len(self.persons) < 2:
            QMessageBox.information(self, "Merge", "At least 2 people are required to perform a merge.")
            return

        names = [f"{p['id']}: {p['name']} ({p.get('image_count', 0)} photos)" for p in self.persons]
        source_str, ok1 = QInputDialog.getItem(
            self, "Merge People", "Select Person to merge FROM (will be merged into target):", names, 0, False
        )
        if not ok1 or not source_str:
            return

        target_str, ok2 = QInputDialog.getItem(
            self, "Merge People", "Select Target Person to merge INTO:", names, 1, False
        )
        if not ok2 or not target_str:
            return

        source_id = int(source_str.split(":")[0])
        target_id = int(target_str.split(":")[0])

        if source_id == target_id:
            QMessageBox.warning(self, "Merge Error", "Cannot merge a person into themselves.")
            return

        with self.lock:
            self.engine.merge_persons(target_id, [source_id])
        QMessageBox.information(self, "Merged", f"Successfully merged Person #{source_id} into Person #{target_id}!")
        self.reload_data()
        self.state.invalidate()
