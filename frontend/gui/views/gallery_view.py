"""Primary Photo Gallery Screen with Responsive Multi-Layout Views, Filter Bar, and Pagination."""
from __future__ import annotations

import threading
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from engine import Engine
from gui.components.photo_table import PhotoTableWidget
from gui.safe_call import safe_call
from gui.state import AppState
from gui.tasks import ThumbRepairWorker, enrich_photos
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
        self._thumb_repair: ThumbRepairWorker | None = None
        self._extra_filters: dict[str, Any] = {}

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
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(350)
        self._search_timer.timeout.connect(self.reload_data)
        self.search_input.textChanged.connect(lambda _: self._search_timer.start())
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
        self.combo_dups.addItems(["All Photos", "Unique Only", "Duplicates Only", "Hidden Only"])
        self.combo_dups.setMinimumWidth(122)
        self.combo_dups.currentIndexChanged.connect(lambda _: self.reload_data())
        top_bar.addWidget(self.combo_dups)

        # Sort Order
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["Date (Oldest)", "Date (Newest)", "Quality Score", "Path Name"])
        self.combo_sort.setMinimumWidth(130)
        self.combo_sort.currentIndexChanged.connect(lambda _: self.reload_data())
        top_bar.addWidget(self.combo_sort)

        self.combo_tag = QComboBox()
        self.combo_tag.addItem("Any Tag", None)
        self.combo_tag.setMinimumWidth(110)
        self.combo_tag.setVisible(False)                  # shown only when tags exist
        self.combo_tag.currentIndexChanged.connect(lambda _: self.reload_data())
        top_bar.addWidget(self.combo_tag)

        self.btn_saved = QPushButton("Saved ▾")
        self.btn_saved.setProperty("class", "Secondary")
        self.saved_menu = QMenu(self)
        self.saved_menu.aboutToShow.connect(self._rebuild_saved_menu)
        self.btn_saved.setMenu(self.saved_menu)
        top_bar.addWidget(self.btn_saved)

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

        self.page_lbl = QLabel("Page 1 of 1")
        self.page_lbl.setProperty("class", "CardTitle")
        self.page_lbl.setContentsMargins(8, 0, 8, 0)
        footer.addWidget(self.page_lbl)

        self.spin_page = QSpinBox()
        self.spin_page.setRange(1, 1)
        self.spin_page.setFixedWidth(55)
        self.spin_page.setToolTip("Go to page")
        self.spin_page.valueChanged.connect(self._on_page_spin_changed)
        footer.addWidget(self.spin_page)

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

    def _on_page_spin_changed(self, val: int) -> None:
        target = val - 1
        if target != self.state.current_page and target >= 0:
            self.state.set_page(target)
            self.reload_data(reset_page=False)

    def _rename_person_from_pill(self, person_id: int, new_name: str) -> None:
        safe_call(self, self.engine.rename_person, person_id, new_name)
        self.reload_persons()

    def reload_persons(self) -> None:
        persons = safe_call(self, self.engine.get_persons, default=[]) or []

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

    _SORT_LABELS = {
        "date": "Date (Oldest)",
        "date_desc": "Date (Newest)",
        "quality": "Quality Score",
        "path": "Path Name",
    }

    def shutdown(self) -> None:
        if self._thumb_repair is not None and self._thumb_repair.isRunning():
            self._thumb_repair.requestInterruption()
            self._thumb_repair.wait(5000)

    def reload_tags(self) -> None:
        tags = safe_call(self, self.engine.list_tags, 80, default=[]) or []
        current = self.combo_tag.currentData()
        self.combo_tag.blockSignals(True)
        self.combo_tag.clear()
        self.combo_tag.addItem("Any Tag", None)
        for t in tags:
            self.combo_tag.addItem(f"{t['label']} ({t['count']})", t["label"])
        self.combo_tag.setCurrentIndex(max(0, self.combo_tag.findData(current)) if current else 0)
        self.combo_tag.blockSignals(False)
        self.combo_tag.setVisible(bool(tags))

    def _rebuild_saved_menu(self) -> None:
        self.saved_menu.clear()
        saved = safe_call(self, self.engine.list_saved_searches, default=[]) or []
        for s in saved:
            act = self.saved_menu.addAction(s["name"])
            act.triggered.connect(lambda _=False, f=s["filters"]: self._apply_filters(f))
        if saved:
            self.saved_menu.addSeparator()
        self.saved_menu.addAction("Save current search…").triggered.connect(self._save_current)
        if saved:
            delete = self.saved_menu.addMenu("Delete")
            for s in saved:
                delete.addAction(s["name"]).triggered.connect(
                    lambda _=False, n=s["name"]: safe_call(self, self.engine.delete_saved_search, n))
        self.saved_menu.addAction("Reset all filters").triggered.connect(
            lambda _=False: self._apply_filters({}))

    def _save_current(self) -> None:
        name, ok = QInputDialog.getText(self, "Save search", "Name:")
        if ok and name.strip():
            filters, sort = self._current_filters()
            safe_call(self, self.engine.save_search, name.strip(), {**filters, "sort": sort})

    def _current_filters(self) -> tuple[dict[str, Any], str]:
        filters: dict[str, Any] = dict(self._extra_filters)
        txt = self.search_input.text().strip()
        if txt:
            filters["path_contains"] = txt
        if self.spin_faces.value() > 0:
            filters["min_faces"] = self.spin_faces.value()
        if self.state.selected_person_id is not None:
            filters["person_id"] = self.state.selected_person_id

        tag = self.combo_tag.currentData()
        if tag:
            filters["tag"] = tag

        dup = self.combo_dups.currentText()
        if dup == "Unique Only":
            filters["duplicate"] = "none"
        elif dup == "Duplicates Only":
            filters["duplicate"] = "any"
        elif dup == "Hidden Only":
            filters["mark"] = "hidden"

        sort_choice = {
            "Date (Oldest)": "date",
            "Date (Newest)": "date_desc",
            "Quality Score": "quality",
            "Path Name": "path",
        }.get(self.combo_sort.currentText(), "date")
        return filters, sort_choice

    def _apply_filters(self, saved: dict[str, Any]) -> None:
        f = dict(saved)
        sort = f.pop("sort", "date")
        extras: dict[str, Any] = {}
        label = "All Photos"
        if f.get("mark") == "hidden":
            f.pop("mark")
            label = "Hidden Only"
            if "duplicate" in f:
                extras["duplicate"] = f.pop("duplicate")
        elif f.get("duplicate") in ("none", "any"):
            label = "Unique Only" if f.pop("duplicate") == "none" else "Duplicates Only"
        tag = f.pop("tag", None)
        tag_idx = self.combo_tag.findData(tag) if tag else 0
        if tag and tag_idx < 0:
            extras["tag"], tag_idx = tag, 0
        pid = f.pop("person_id", None)
        path_txt = f.pop("path_contains", "") or ""
        min_faces = int(f.pop("min_faces", 0) or 0)
        extras.update(f)
        self._extra_filters = extras

        widgets = (self.search_input, self.spin_faces, self.combo_dups, self.combo_sort, self.combo_tag)
        for w in widgets:
            w.blockSignals(True)
        self.search_input.setText(path_txt)
        self.spin_faces.setValue(min_faces)
        self.combo_dups.setCurrentText(label)
        self.combo_sort.setCurrentText(self._SORT_LABELS.get(sort, "Date (Oldest)"))
        self.combo_tag.setCurrentIndex(tag_idx)
        for w in widgets:
            w.blockSignals(False)
        if pid != self.state.selected_person_id:
            self.state.select_person(pid)
        else:
            self.reload_data()

    def reload_data(self, reset_page: bool = True) -> None:
        pid = self.state.selected_person_id
        if pid is not None and safe_call(self, self.engine.get_person, pid, default=None) is None:
            self.state.selected_person_id = None
            self.btn_clear_person.setVisible(False)

        if reset_page:
            self.state.current_page = 0

        filters, sort_choice = self._current_filters()

        total_matched = safe_call(self, self.engine.count, kind="photo", default=0, **filters) or 0
        total_pages = max(1, (total_matched + self.state.page_size - 1) // self.state.page_size)

        offset = self.state.current_page * self.state.page_size
        raw_items = safe_call(
            self,
            self.engine.find,
            kind="photo",
            sort=sort_choice,
            limit=self.state.page_size,
            offset=offset,
            default=[],
            **filters,
        ) or []

        # Batch-enrich faces and get thumbnail paths
        items = enrich_photos(self.engine, raw_items)
        missing_thumbs = []
        for it in items:
            try:
                t = self.engine.thumbnail(it["id"])
                it["thumb_path"] = t
            except Exception:
                it["thumb_path"] = None
                missing_thumbs.append(it.get("path"))

        if missing_thumbs:
            self._thumb_repair = ThumbRepairWorker(self.engine, missing_thumbs, self)
            self._thumb_repair.start()

        self.current_items = items
        total_shown = len(items)
        start_idx = offset + 1 if total_shown > 0 else 0
        end_idx = offset + total_shown

        extra = f"  ·  {len(self._extra_filters)} saved filter(s) active" if self._extra_filters else ""
        self.status_lbl.setText(
            (f"Showing {start_idx}–{end_idx} of {total_matched} photos" if total_shown else "No photos matched") + extra
        )
        self.page_lbl.setText(f"Page {self.state.current_page + 1} of {total_pages}")
        self.spin_page.blockSignals(True)
        self.spin_page.setRange(1, total_pages)
        self.spin_page.setValue(self.state.current_page + 1)
        self.spin_page.blockSignals(False)

        self.btn_prev.setEnabled(self.state.current_page > 0)
        self.btn_next.setEnabled(self.state.current_page + 1 < total_pages)

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
