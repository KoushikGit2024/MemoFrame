"""Dialog showing list of failed images and their errors."""
from __future__ import annotations

from typing import Any
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QLabel,
)


class FailedImagesDialog(QDialog):
    """Displays images that failed processing, along with error messages."""

    def __init__(self, engine: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle("Failed Photos")
        self.resize(700, 400)
        self._init_ui()
        self._load_data()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.info_lbl = QLabel("Images that encountered errors during processing:")
        layout.addWidget(self.info_lbl)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "File Path", "Error"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_close)
        layout.addLayout(btn_box)

    def _load_data(self) -> None:
        failed_items = []
        try:
            failed_items = self.engine.find(status="failed", limit=500)
        except Exception:
            pass

        self.table.setRowCount(len(failed_items))
        for row, item in enumerate(failed_items):
            self.table.setItem(row, 0, QTableWidgetItem(str(item.get("id", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(str(item.get("path", ""))))
            self.table.setItem(row, 2, QTableWidgetItem(str(item.get("error", "Unknown error"))))
