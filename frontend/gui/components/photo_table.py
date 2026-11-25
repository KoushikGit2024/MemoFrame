"""Tabular List View for high-density photo browsing and batch inspection."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class PhotoTableWidget(QTableWidget):
    """Sortable, modern web-styled tabular photo view with metadata columns."""

    photo_double_clicked = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.photos: list[dict[str, Any]] = []
        self.setColumnCount(8)
        self.setHorizontalHeaderLabels([
            "ID", "Filename", "Date", "Faces", "Quality", "Dimensions", "Format", "Path"
        ])

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)

        # Clean proportional column widths
        col_widths = [54, 210, 152, 64, 78, 108, 70]
        for idx, width in enumerate(col_widths):
            self.setColumnWidth(idx, width)

        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(38)

        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.cellDoubleClicked.connect(self._on_cell_double_clicked)

    def set_photos(self, photos: list[dict[str, Any]]) -> None:
        self.photos = photos
        self.setRowCount(len(photos))

        center_cols = {0, 3, 4, 6}
        for row, p in enumerate(photos):
            file_name = Path(p.get("path", "")).name
            date_str = (p.get("effective_ts") or p.get("exif_ts") or "—")[:19]
            face_cnt = str(p.get("face_count", len(p.get("faces", []))))
            q_str = f"{round(float(p.get('quality', 0)))}%" if p.get("quality") else "—"
            dims = f"{p.get('width', 0)} × {p.get('height', 0)}"
            fmt = (p.get("format") or "—").upper()
            full_path = p.get("path", "")

            values = [
                str(p.get("id", "")),
                file_name,
                date_str,
                face_cnt,
                q_str,
                dims,
                fmt,
                full_path,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col in center_cols:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if col in (1, 7):
                    item.setToolTip(full_path)
                self.setItem(row, col, item)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if 0 <= row < len(self.photos):
            self.photo_double_clicked.emit(self.photos[row])
