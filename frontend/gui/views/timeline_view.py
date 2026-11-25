"""Timeline and Event Grouping Screen with Smooth Non-Trapping Horizontal Strips."""
from __future__ import annotations

import threading
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from engine import Engine
from gui.safe_call import safe_call
from gui.state import AppState
from gui.tasks import enrich_photos
from gui.widgets import EmptyStateWidget, HorizontalStripScrollArea, PhotoCardWidget


GROUPS_PER_PAGE = 20


class TimelineView(QWidget):
    """Chronological event & burst grouping view."""

    photo_opened = pyqtSignal(dict)

    def __init__(self, state: AppState, engine: Engine, lock: threading.RLock, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.engine = engine
        self.lock = lock
        self.groups: list[dict[str, Any]] = []
        self._shown = GROUPS_PER_PAGE

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)

        hdr = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        self.title_lbl = QLabel("Events & Timeline Groups (0)")
        self.title_lbl.setProperty("class", "PageTitle")
        title_block.addWidget(self.title_lbl)

        sub = QLabel("Chronological bursts and automatically clustered photo events.")
        sub.setProperty("class", "PageSubtitle")
        title_block.addWidget(sub)
        hdr.addLayout(title_block, stretch=1)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "Secondary")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.clicked.connect(self.reload_data)
        hdr.addWidget(btn_refresh)
        layout.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.container.setObjectName("ScrollContainer")
        self.events_layout = QVBoxLayout(self.container)
        self.events_layout.setContentsMargins(2, 4, 8, 12)
        self.events_layout.setSpacing(16)
        self.events_layout.addStretch()
        scroll.setWidget(self.container)
        layout.addWidget(scroll, stretch=1)

    def reload_data(self) -> None:
        groups = safe_call(self, self.engine.get_groups, default=[]) or []
        dated = sorted((g for g in groups if g.get("start_ts")),
                       key=lambda g: g["start_ts"], reverse=True)      # newest first
        undated = [g for g in groups if not g.get("start_ts")]
        self.groups = dated + undated
        self._shown = GROUPS_PER_PAGE
        self._rebuild()

    def _rebuild(self) -> None:
        self.title_lbl.setText(f"Events & Timeline Groups ({len(self.groups)})")
        while self.events_layout.count() > 1:
            item = self.events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.groups:
            self.events_layout.insertWidget(0, EmptyStateWidget(
                "◷", "No Timeline Events Yet",
                "Event groups will appear here once photos with timestamps are indexed."))
            return
        visible = self.groups[:self._shown]
        for idx, g in enumerate(visible):
            self.events_layout.insertWidget(idx, self._create_event_section(g))
        remaining = len(self.groups) - len(visible)
        if remaining > 0:
            btn = QPushButton(f"Show {min(GROUPS_PER_PAGE, remaining)} more  ({remaining} remaining)")
            btn.setProperty("class", "Secondary")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self._show_more)
            self.events_layout.insertWidget(len(visible), btn)

    def _show_more(self) -> None:
        self._shown += GROUPS_PER_PAGE
        self._rebuild()

    def _create_event_section(self, group: dict[str, Any]) -> QFrame:
        frame = QFrame()
        frame.setProperty("class", "EventCard")
        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(16, 14, 16, 14)
        vbox.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)

        name = group.get("name") or f"Event #{group.get('id')}"
        lbl = QLabel(name)
        lbl.setProperty("class", "AccentTitle")
        header.addWidget(lbl)

        start = (group.get("start_ts") or "")[:10]
        end = (group.get("end_ts") or "")[:10]
        date_text = start if (not end or start == end) else f"{start} → {end}"
        if date_text:
            date_chip = QLabel(date_text)
            date_chip.setProperty("class", "DateChip")
            header.addWidget(date_chip)

        count_chip = QLabel(f"{group.get('image_count', 0)} photos")
        count_chip.setProperty("class", "CountChip")
        header.addWidget(count_chip)

        header.addStretch()
        vbox.addLayout(header)

        # Horizontal strip with exact non-clipping height & vertical wheel pass-through
        strip = HorizontalStripScrollArea(pass_vertical_wheel=True)
        strip.setFixedHeight(248)
        h_widget = QWidget()
        h_widget.setObjectName("ScrollContainer")
        h_box = QHBoxLayout(h_widget)
        h_box.setContentsMargins(0, 2, 0, 8)
        h_box.setSpacing(12)
        h_box.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        h_box.addStretch()

        raw_photos = safe_call(self, self.engine.get_group_images, group["id"], limit=8, default=[]) or []
        photos = enrich_photos(self.engine, raw_photos)
        for p_idx, p in enumerate(photos):
            try:
                thumb = self.engine.thumbnail(p["id"])
            except Exception:
                thumb = None
            card = PhotoCardWidget(p, thumb_path=thumb)
            card.clicked.connect(lambda _, item=p: self.photo_opened.emit(item))
            h_box.insertWidget(p_idx, card)

        extra = int(group.get("image_count", 0)) - len(photos)
        if extra > 0:
            more = QLabel(f"+{extra} more")
            more.setProperty("class", "Dim")
            h_box.insertWidget(len(photos), more)

        strip.setWidget(h_widget)
        vbox.addWidget(strip)

        return frame
