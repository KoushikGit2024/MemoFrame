"""Central reactive application state for MemoFrame Desktop."""
from __future__ import annotations

from typing import Any
from PyQt6.QtCore import QObject, pyqtSignal


class AppState(QObject):
    """Singleton-like observable state managing active view, filters, and selection."""

    # Navigation & View
    view_changed = pyqtSignal(str)              # "photos", "people", "duplicates", "timeline", "settings"
    layout_mode_changed = pyqtSignal(str)       # "grid", "compact", "table"
    card_size_changed = pyqtSignal(int)         # 160 to 320 px

    # Filters & Pagination
    filter_changed = pyqtSignal(dict)
    page_changed = pyqtSignal(int)
    theme_changed = pyqtSignal(str)

    # Selection & Inspection
    photo_selected = pyqtSignal(dict)           # photo dict or None
    person_selected = pyqtSignal(object)        # person_id (int) or None
    open_lightbox = pyqtSignal(dict)            # photo dict

    # Data lifecycle
    data_invalidated = pyqtSignal()             # refresh triggers

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.active_view: str = "photos"
        self.layout_mode: str = "grid"
        self.card_size: int = 220
        self.current_page: int = 0
        self.page_size: int = 40
        self.selected_person_id: int | None = None
        self.current_theme: str = "Dark Slate"
        self.last_dark_theme: str = "Dark Slate"
        self.filters: dict[str, Any] = {}

    def set_view(self, view: str) -> None:
        if self.active_view != view:
            self.active_view = view
            self.view_changed.emit(view)

    def set_layout_mode(self, mode: str) -> None:
        if self.layout_mode != mode:
            self.layout_mode = mode
            self.layout_mode_changed.emit(mode)

    def set_card_size(self, size: int) -> None:
        size = max(160, min(320, size))
        if self.card_size != size:
            self.card_size = size
            self.card_size_changed.emit(size)

    def select_person(self, person_id: int | None) -> None:
        self.selected_person_id = person_id
        self.current_page = 0
        self.person_selected.emit(person_id)

    def set_filters(self, filters: dict[str, Any]) -> None:
        self.filters = filters
        self.current_page = 0
        self.filter_changed.emit(self.filters)

    def set_page(self, page: int) -> None:
        if self.current_page != page:
            self.current_page = max(0, page)
            self.page_changed.emit(self.current_page)

    def set_theme(self, theme: str) -> None:
        if theme != "Light Canvas":
            self.last_dark_theme = theme
        if self.current_theme != theme:
            self.current_theme = theme
            self.theme_changed.emit(theme)

    def toggle_light_dark(self) -> None:
        """Toggle seamlessly between Light Canvas and the user's preferred dark palette."""
        if self.current_theme == "Light Canvas":
            self.set_theme(self.last_dark_theme or "Dark Slate")
        else:
            self.last_dark_theme = self.current_theme
            self.set_theme("Light Canvas")

    def invalidate(self) -> None:
        self.data_invalidated.emit()
