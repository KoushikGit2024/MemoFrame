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
from gui.state import AppState
from gui.widgets import EmptyStateWidget, HorizontalStripScrollArea, PhotoCardWidget


class TimelineView(QWidget):
    """Chronological event & burst grouping view."""

    photo_opened = pyqtSignal(dict)

    def __init__(self, state: AppState, engine: Engine, lock: threading.RLock, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.engine = engine
        self.lock = lock
        self.groups: list[dict[str, Any]] = []

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
        with self.lock:
            self.groups = self.engine.get_groups()

        self.title_lbl.setText(f"Events & Timeline Groups ({len(self.groups)})")
        while self.events_layout.count() > 1:
            item = self.events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.groups:
            empty = EmptyStateWidget(
                "◷",
                "No Timeline Events Yet",
                "Event groups will appear here once photos with timestamps are indexed.",
            )
            self.events_layout.insertWidget(0, empty)
            return

        for idx, g in enumerate(self.groups[:20]):
            event_card = self._create_event_section(g)
            self.events_layout.insertWidget(idx, event_card)

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

        with self.lock:
            photos = self.engine.get_group_images(group["id"], limit=8)
            for p_idx, p in enumerate(photos):
                try:
                    thumb = self.engine.thumbnail(p["id"])
                except Exception:
                    thumb = None
                p["faces"] = [dict(f) for f in self.engine.get_faces(p["id"])]
                card = PhotoCardWidget(p, thumb_path=thumb)
                card.clicked.connect(lambda _, item=p: self.photo_opened.emit(item))
                h_box.insertWidget(p_idx, card)

        strip.setWidget(h_widget)
        vbox.addWidget(strip)

        return frame
