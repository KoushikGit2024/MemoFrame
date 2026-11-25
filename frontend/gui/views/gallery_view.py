"""Primary Photo Gallery Screen with Responsive Multi-Layout Views, Filter Bar, and Pagination."""
from __future__ import annotations

import threading
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from engine import Engine
from gui.components.photo_table import PhotoTableWidget
from gui.state import AppState
from gui.widgets import (
    EmptyStateWidget,
    HorizontalStripScrollArea,
    PersonPillWidget,
    PhotoCardWidget,
)


class GalleryView(QWidget):
    """Main photo gallery supporting responsive Grid, Compact, and Table layout modes."""

    photo_opened = pyqtSignal(dict)

    def __init__(self, state: AppState, engine: Engine, lock: threading.RLock, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.engine = engine
        self.lock = lock
        self.current_items: list[dict[str, Any]] = []
        self._person_pills: dict[int | None, PersonPillWidget] = {}
        self._card_widgets: list[QWidget] = []
        self._last_cols: int = 0

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 16)
        main_layout.setSpacing(12)

        # 1. Top Filter & Layout Toolbar Card
        toolbar_card = QFrame()
        toolbar_card.setProperty("class", "ToolbarCard")
        top_bar = QHBoxLayout(toolbar_card)
        top_bar.setContentsMargins(12, 10, 12, 10)
        top_bar.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search photos by filename or path...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(180)
        self.search_input.returnPressed.connect(self.reload_data)
        top_bar.addWidget(self.search_input, stretch=2)

        # Min faces filter
        faces_lbl = QLabel("Min Faces")
        faces_lbl.setProperty("class", "Dim")
        top_bar.addWidget(faces_lbl)

        self.spin_faces = QSpinBox()
        self.spin_faces.setRange(0, 20)
        self.spin_faces.setFixedWidth(64)
        self.spin_faces.setToolTip("Minimum number of detected faces")
        self.spin_faces.valueChanged.connect(lambda _: self.reload_data())
        top_bar.addWidget(self.spin_faces)

        # Duplicate filter
        self.combo_dups = QComboBox()
        self.combo_dups.addItems(["All Photos", "Unique Only", "Duplicates Only"])
        self.combo_dups.setMinimumWidth(122)
        self.combo_dups.currentIndexChanged.connect(lambda _: self.reload_data())
        top_bar.addWidget(self.combo_dups)

        # Sort Order
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["Date (Oldest)", "Date (Newest)", "Quality Score", "Path Name"])
        self.combo_sort.setMinimumWidth(130)
        self.combo_sort.currentIndexChanged.connect(lambda _: self.reload_data())
        top_bar.addWidget(self.combo_sort)

        # Sleek Segmented Control for Layout Mode (Grid, Compact, Table)
        seg_frame = QFrame()
        seg_frame.setProperty("class", "SegmentedControl")
        seg_layout = QHBoxLayout(seg_frame)
        seg_layout.setContentsMargins(3, 3, 3, 3)
        seg_layout.setSpacing(2)

        self.btn_grid = QPushButton("Grid")
        self.btn_grid.setProperty("class", "SegmentButton")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_grid.clicked.connect(lambda: self._set_layout("grid"))

        self.btn_compact = QPushButton("Compact")
        self.btn_compact.setProperty("class", "SegmentButton")
        self.btn_compact.setCheckable(True)
        self.btn_compact.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_compact.clicked.connect(lambda: self._set_layout("compact"))

        self.btn_table = QPushButton("Table")
        self.btn_table.setProperty("class", "SegmentButton")
        self.btn_table.setCheckable(True)
        self.btn_table.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_table.clicked.connect(lambda: self._set_layout("table"))

        self.layout_group = QButtonGroup(self)
        self.layout_group.setExclusive(True)
        self.layout_group.addButton(self.btn_grid)
        self.layout_group.addButton(self.btn_compact)
        self.layout_group.addButton(self.btn_table)

        seg_layout.addWidget(self.btn_grid)
        seg_layout.addWidget(self.btn_compact)
        seg_layout.addWidget(self.btn_table)
        top_bar.addWidget(seg_frame)

        main_layout.addWidget(toolbar_card)

        # 2. People Quick-Filter Carousel
        self.person_frame = QFrame()
        self.person_frame.setProperty("class", "Card")
        p_layout = QVBoxLayout(self.person_frame)
        p_layout.setContentsMargins(12, 10, 12, 8)
        p_layout.setSpacing(8)

        p_header = QHBoxLayout()
        p_header.setContentsMargins(2, 0, 2, 0)
        self.person_count_lbl = QLabel("Identified People")
        self.person_count_lbl.setProperty("class", "SectionTitle")
        p_header.addWidget(self.person_count_lbl)

        self.btn_clear_person = QPushButton("Clear filter")
        self.btn_clear_person.setProperty("class", "Ghost")
        self.btn_clear_person.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_person.setVisible(False)
        self.btn_clear_person.clicked.connect(lambda: self.state.select_person(None))
        p_header.addWidget(self.btn_clear_person)

        p_header.addStretch()
        p_layout.addLayout(p_header)

        self.person_scroll = HorizontalStripScrollArea(pass_vertical_wheel=False)
        self.person_scroll.setFixedHeight(64)
        self.person_container = QWidget()
        self.person_container.setObjectName("ScrollContainer")
        self.person_bar_layout = QHBoxLayout(self.person_container)
        self.person_bar_layout.setContentsMargins(0, 2, 0, 2)
        self.person_bar_layout.setSpacing(8)
        self.person_bar_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.person_bar_layout.addStretch()
        self.person_scroll.setWidget(self.person_container)
        p_layout.addWidget(self.person_scroll)
        main_layout.addWidget(self.person_frame)

        # 3. Stacked View: Responsive Grid / Compact ScrollArea vs Table
        self.view_stack = QStackedWidget()

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.grid_content = QWidget()
        self.grid_content.setObjectName("ScrollContainer")
        self.grid_layout = QGridLayout(self.grid_content)
        self.grid_layout.setContentsMargins(2, 4, 8, 8)
        self.grid_layout.setSpacing(14)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid_scroll.setWidget(self.grid_content)
        self.view_stack.addWidget(self.grid_scroll)

        self.table_view = PhotoTableWidget()
        self.table_view.photo_double_clicked.connect(self._on_photo_clicked)
        self.view_stack.addWidget(self.table_view)

        main_layout.addWidget(self.view_stack, stretch=1)

        # 4. Footer Pagination Bar
        footer_card = QFrame()
        footer_card.setProperty("class", "FooterBar")
        footer = QHBoxLayout(footer_card)
        footer.setContentsMargins(14, 8, 14, 8)
        footer.setSpacing(10)

        self.status_lbl = QLabel("Showing 0 photos")
        self.status_lbl.setProperty("class", "Dim")
        footer.addWidget(self.status_lbl)
        footer.addStretch()

        self.btn_prev = QPushButton("← Prev")
        self.btn_prev.setProperty("class", "Secondary")
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.clicked.connect(self._prev_page)
        footer.addWidget(self.btn_prev)

        self.page_lbl = QLabel("Page 1")
        self.page_lbl.setProperty("class", "CardTitle")
        self.page_lbl.setContentsMargins(8, 0, 8, 0)
        footer.addWidget(self.page_lbl)

        self.btn_next = QPushButton("Next →")
        self.btn_next.setProperty("class", "Secondary")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.clicked.connect(self._next_page)
        footer.addWidget(self.btn_next)

        main_layout.addWidget(footer_card)

    def _connect_signals(self) -> None:
        self.state.person_selected.connect(self._on_person_selection_changed)
        self.state.data_invalidated.connect(self.reload_data)

    def _on_person_selection_changed(self, person_id: int | None) -> None:
        self.btn_clear_person.setVisible(person_id is not None)
        for pid, pill in self._person_pills.items():
            pill.set_selected(pid == person_id)
        self.reload_data(reset_page=True)

    def _set_layout(self, mode: str) -> None:
        self.state.set_layout_mode(mode)
        if mode in ("grid", "compact"):
            self.view_stack.setCurrentIndex(0)
            self._render_cards()
        elif mode == "table":
            self.view_stack.setCurrentIndex(1)
            self.table_view.set_photos(self.current_items)

    def _prev_page(self) -> None:
        if self.state.current_page > 0:
            self.state.set_page(self.state.current_page - 1)
            self.reload_data(reset_page=False)

    def _next_page(self) -> None:
        self.state.set_page(self.state.current_page + 1)
        self.reload_data(reset_page=False)

    def _rename_person_from_pill(self, person_id: int, new_name: str) -> None:
        with self.lock:
            self.engine.rename_person(person_id, new_name)
        self.reload_persons()

    def reload_persons(self) -> None:
        with self.lock:
            persons = self.engine.get_persons()

        self._person_pills.clear()
        while self.person_bar_layout.count() > 1:
            item = self.person_bar_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.person_count_lbl.setText(f"Identified People ({len(persons)})")
        self.btn_clear_person.setVisible(self.state.selected_person_id is not None)
        if not persons:
            self.person_frame.setVisible(False)
            return

        self.person_frame.setVisible(True)
        all_pill = PersonPillWidget(
            {"id": 0, "name": "All People", "image_count": 0},
            is_selected=(self.state.selected_person_id is None),
        )
        all_pill.clicked.connect(lambda _: self.state.select_person(None))
        self._person_pills[None] = all_pill
        self.person_bar_layout.insertWidget(0, all_pill)

        for idx, p in enumerate(persons, start=1):
            is_sel = self.state.selected_person_id == p["id"]
            pill = PersonPillWidget(p, is_selected=is_sel)
            pill.clicked.connect(self.state.select_person)
            pill.renamed.connect(self._rename_person_from_pill)
            self._person_pills[p["id"]] = pill
            self.person_bar_layout.insertWidget(idx, pill)

    def reload_data(self, reset_page: bool = True) -> None:
        if reset_page:
            self.state.current_page = 0

        filters: dict[str, Any] = {}
        txt = self.search_input.text().strip()
        if txt:
            filters["path_contains"] = txt
        if self.spin_faces.value() > 0:
            filters["min_faces"] = self.spin_faces.value()
        if self.state.selected_person_id is not None:
            filters["person_id"] = self.state.selected_person_id

        dup_choice = self.combo_dups.currentText()
        if dup_choice == "Unique Only":
            filters["duplicate"] = "none"
        elif dup_choice == "Duplicates Only":
            filters["duplicate"] = "any"

        sort_choice = {
            "Date (Oldest)": "date",
            "Date (Newest)": "date_desc",
            "Quality Score": "quality",
            "Path Name": "path",
        }.get(self.combo_sort.currentText(), "date")

        offset = self.state.current_page * self.state.page_size
        with self.lock:
            items = self.engine.find(sort=sort_choice, limit=self.state.page_size, offset=offset, **filters)
            for it in items:
                it["faces"] = [dict(f) for f in self.engine.get_faces(it["id"])]
                try:
                    it["thumb_path"] = self.engine.thumbnail(it["id"])
                except Exception:
                    it["thumb_path"] = None

        self.current_items = items
        total_shown = len(items)
        start_idx = offset + 1 if total_shown > 0 else 0
        end_idx = offset + total_shown

        self.status_lbl.setText(f"Showing {start_idx}–{end_idx} photos" if total_shown else "No photos matched")
        self.page_lbl.setText(f"Page {self.state.current_page + 1}")
        self.btn_prev.setEnabled(self.state.current_page > 0)
        self.btn_next.setEnabled(total_shown == self.state.page_size)

        if self.state.layout_mode == "table":
            self.table_view.set_photos(self.current_items)
        else:
            self._render_cards()

    def _compute_grid_columns(self) -> int:
        is_compact = self.state.layout_mode == "compact"
        card_w = 176 if is_compact else 224
        spacing = 10 if is_compact else 14
        viewport_w = self.grid_scroll.viewport().width()
        if viewport_w < card_w:
            viewport_w = max(card_w, self.width() - 48)
        avail_w = max(card_w, viewport_w - 16)
        return max(1, (avail_w + spacing) // (card_w + spacing))

    def _render_cards(self) -> None:
        self._card_widgets.clear()
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        is_compact = self.state.layout_mode == "compact"
        spacing = 10 if is_compact else 14
        self.grid_layout.setSpacing(spacing)

        if not self.current_items:
            self.grid_layout.setColumnStretch(0, 1)
            empty = EmptyStateWidget(
                "◫",
                "No Photos Found",
                "Try adjusting your search query, face filter, or duplicate filter to see more photos.",
            )
            self.grid_layout.addWidget(empty, 0, 0)
            self._last_cols = 1
            return

        self.grid_layout.setColumnStretch(0, 0)
        cols = self._compute_grid_columns()
        self._last_cols = cols

        for idx, item in enumerate(self.current_items):
            card = PhotoCardWidget(item, thumb_path=item.get("thumb_path"), compact=is_compact)
            card.clicked.connect(lambda img_id, it=item: self._on_photo_clicked(it))
            self._card_widgets.append(card)
            self.grid_layout.addWidget(card, idx // cols, idx % cols)

    def _reflow_cards(self) -> None:
        if not self._card_widgets or self.state.layout_mode == "table":
            return
        cols = self._compute_grid_columns()
        if cols == self._last_cols:
            return
        self._last_cols = cols
        for w in self._card_widgets:
            self.grid_layout.removeWidget(w)
        for idx, w in enumerate(self._card_widgets):
            self.grid_layout.addWidget(w, idx // cols, idx % cols)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow_cards()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reflow_cards()

    def _on_photo_clicked(self, photo_data: dict[str, Any]) -> None:
        self.photo_opened.emit(photo_data)
