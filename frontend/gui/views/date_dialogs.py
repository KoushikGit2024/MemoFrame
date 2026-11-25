"""Correct wrong photo dates (stored in the database only)."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from gui.safe_call import safe_call

_FAIL = object()
_ISO = "yyyy-MM-dd'T'HH:mm:ss"


class DateOverrideDialog(QDialog):
    def __init__(self, current_iso: str | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Correct Date")
        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                "Set the date and time this photo was really taken.\n"
                "Only the database changes; the file is never modified."
            )
        )
        dt = QDateTime.fromString((current_iso or "")[:19], _ISO)
        if not dt.isValid():
            dt = QDateTime.currentDateTime()
        self.edit = QDateTimeEdit(dt)
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        lay.addWidget(self.edit)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def value_iso(self) -> str:
        return self.edit.dateTime().toString(_ISO)


class SuspiciousDatesDialog(QDialog):
    """Photos with no, future or implausible dates (camera clock wrong, scans...)."""

    def __init__(self, engine, lock, parent=None) -> None:
        super().__init__(parent)
        self.engine, self.lock, self.changed = engine, lock, False
        self.rows: list[dict[str, Any]] = safe_call(self, engine.suspicious_dates, 500, default=[]) or []
        self.setWindowTitle("Suspicious Dates")
        self.resize(960, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                f"{len(self.rows)} photo(s) have a missing, future or implausible date. "
                "Select one or more rows, then set the correct date."
            )
        )
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Path", "Recorded", "Problem", "Corrected to"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        b_set = QPushButton("Set Date…")
        b_set.clicked.connect(self._set)
        b_clear = QPushButton("Clear Correction")
        b_clear.setProperty("class", "Secondary")
        b_clear.clicked.connect(self._clear)
        b_close = QPushButton("Close")
        b_close.setProperty("class", "Secondary")
        b_close.clicked.connect(self.accept)
        for b in (b_set, b_clear):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(b_close)
        lay.addLayout(row)
        self._fill()

    def _fill(self) -> None:
        self.table.setRowCount(len(self.rows))
        for r, d in enumerate(self.rows):
            vals = (
                d.get("path", ""),
                d.get("exif_ts") or "—",
                d.get("date_flag") or "",
                d.get("override_ts") or "",
            )
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(v)))

    def _selected(self) -> list[dict[str, Any]]:
        return [self.rows[r] for r in sorted({i.row() for i in self.table.selectedIndexes()})]

    def _set(self) -> None:
        sel = self._selected()
        if not sel:
            return
        dlg = DateOverrideDialog(sel[0].get("override_ts") or sel[0].get("exif_ts"), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        iso = dlg.value_iso()
        for d in sel:
            if (
                safe_call(self, self.engine.set_date_override, int(d["id"]), iso, "manual (bulk)", default=_FAIL)
                is not _FAIL
            ):
                d["override_ts"] = iso
                self.changed = True
        self._fill()

    def _clear(self) -> None:
        for d in self._selected():
            if safe_call(self, self.engine.clear_date_override, int(d["id"]), default=_FAIL) is not _FAIL:
                d["override_ts"] = None
                self.changed = True
        self._fill()
