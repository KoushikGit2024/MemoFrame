"""Duplicate Resolution and Cleaning Screen with Side-by-Side Comparison."""
from __future__ import annotations

import threading
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from engine import Engine
from gui.state import AppState
from gui.widgets import EmptyStateWidget, HorizontalStripScrollArea, PhotoCardWidget


class DuplicatesView(QWidget):
    """Side-by-side comparison of duplicate clusters with 1-click keeper resolution."""

    photo_opened = pyqtSignal(dict)

    def __init__(self, state: AppState, engine: Engine, lock: threading.RLock, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.engine = engine
        self.lock = lock
        self.clusters: list[list[dict[str, Any]]] = []

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)

        # Header Bar
        hdr = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        self.title_lbl = QLabel("Duplicate Clusters (0)")
        self.title_lbl.setProperty("class", "PageTitle")
        title_block.addWidget(self.title_lbl)

        sub = QLabel("Compare duplicate candidates side-by-side and keep the sharpest version in one click.")
        sub.setProperty("class", "PageSubtitle")
        title_block.addWidget(sub)
        hdr.addLayout(title_block, stretch=1)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "Secondary")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.clicked.connect(self.reload_data)
        hdr.addWidget(btn_refresh)
        layout.addLayout(hdr)

        # Responsive Splitter: Left cluster list, Right side-by-side comparator
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left Cluster List Panel
        left_panel = QFrame()
        left_panel.setMinimumWidth(220)
        left_panel.setMaximumWidth(340)
        l_box = QVBoxLayout(left_panel)
        l_box.setContentsMargins(0, 0, 6, 0)
        l_box.setSpacing(8)

        lbl = QLabel("CLUSTERS")
        lbl.setProperty("class", "NavSectionLabel")
        lbl.setStyleSheet("padding-left: 2px;")
        l_box.addWidget(lbl)

        self.cluster_list = QListWidget()
        self.cluster_list.currentRowChanged.connect(self._on_cluster_selected)
        l_box.addWidget(self.cluster_list, stretch=1)
        splitter.addWidget(left_panel)

        # Right Comparison Panel
        right_panel = QFrame()
        r_box = QVBoxLayout(right_panel)
        r_box.setContentsMargins(10, 0, 0, 0)
        r_box.setSpacing(12)

        header_row = QHBoxLayout()
        self.cluster_title = QLabel("Select a cluster to compare")
        self.cluster_title.setProperty("class", "SectionTitle")
        header_row.addWidget(self.cluster_title)
        header_row.addStretch()
        r_box.addLayout(header_row)

        self.cards_scroll = HorizontalStripScrollArea(pass_vertical_wheel=False)
        self.cards_container = QWidget()
        self.cards_container.setObjectName("ScrollContainer")
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(2, 4, 8, 8)
        self.cards_layout.setSpacing(16)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.cards_layout.addStretch()
        self.cards_scroll.setWidget(self.cards_container)
        r_box.addWidget(self.cards_scroll, stretch=1)

        splitter.addWidget(right_panel)
        splitter.setSizes([260, 820])
        layout.addWidget(splitter, stretch=1)

    def _clear_comparison(self) -> None:
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def reload_data(self) -> None:
        with self.lock:
            dups = self.engine.find(duplicate="any", limit=300)
            cluster_map: dict[int, list[dict[str, Any]]] = {}
            for d in dups:
                cid = d.get("cluster_id") or d.get("id")
                cluster_map.setdefault(cid, []).append(d)

            self.clusters = [c for c in cluster_map.values() if len(c) > 1]

        self.title_lbl.setText(f"Duplicate Clusters ({len(self.clusters)})")
        self.cluster_list.clear()
        self._clear_comparison()

        if not self.clusters:
            self.cluster_title.setText("Library Clean")
            empty = EmptyStateWidget(
                "✓",
                "No Duplicate Clusters Found",
                "Your library has no unresolved duplicate photo clusters.",
            )
            self.cards_layout.insertWidget(0, empty)
            return

        for idx, cl in enumerate(self.clusters):
            kind = str(cl[0].get("dup_kind", "near")).capitalize()
            item = QListWidgetItem(f"Cluster #{idx + 1}  ·  {len(cl)} copies ({kind})")
            self.cluster_list.addItem(item)

        self.cluster_list.setCurrentRow(0)

    def _on_cluster_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.clusters):
            return

        cluster = self.clusters[row]
        self.cluster_title.setText(f"Comparing Cluster #{row + 1}  ·  {len(cluster)} Photos")
        self._clear_comparison()

        best_id = max(
            cluster,
            key=lambda x: (x.get("quality") or 0, (x.get("width") or 0) * (x.get("height") or 0)),
        )["id"]

        for idx, photo in enumerate(cluster):
            is_best = photo["id"] == best_id
            wrapper = QFrame()
            wrapper.setProperty("class", "KeeperCard" if is_best else "DuplicateCard")
            wrapper.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)

            card_box = QVBoxLayout(wrapper)
            card_box.setContentsMargins(12, 12, 12, 12)
            card_box.setSpacing(10)

            badge_row = QHBoxLayout()
            badge_row.setContentsMargins(0, 0, 0, 0)
            tag = QLabel("★ Recommended Keeper" if is_best else "Duplicate Copy")
            tag.setProperty("class", "KeeperBadge" if is_best else "DuplicateBadge")
            badge_row.addWidget(tag)
            badge_row.addStretch()
            card_box.addLayout(badge_row)

            with self.lock:
                try:
                    thumb = self.engine.thumbnail(photo["id"])
                except Exception:
                    thumb = None
                photo["faces"] = [dict(f) for f in self.engine.get_faces(photo["id"])]

            card = PhotoCardWidget(photo, thumb_path=thumb)
            card.clicked.connect(lambda _, p=photo: self.photo_opened.emit(p))
            card_box.addWidget(card)

            # Resolution & Quality Comparison Specs
            specs_row = QHBoxLayout()
            specs_row.setContentsMargins(2, 0, 2, 0)
            dims = f"{photo.get('width', 0)}×{photo.get('height', 0)}"
            q_val = f"Quality {round(float(photo.get('quality', 0)))}%" if photo.get("quality") else "Quality —"
            dims_lbl = QLabel(dims)
            dims_lbl.setProperty("class", "Dim")
            q_lbl = QLabel(q_val)
            q_lbl.setProperty("class", "Dim")
            specs_row.addWidget(dims_lbl)
            specs_row.addStretch()
            specs_row.addWidget(q_lbl)
            card_box.addLayout(specs_row)

            btn_keep = QPushButton("Keep This Only")
            if not is_best:
                btn_keep.setProperty("class", "Secondary")
            btn_keep.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_keep.clicked.connect(lambda _, pid=photo["id"]: self._keep_single(pid, cluster))
            card_box.addWidget(btn_keep)

            self.cards_layout.insertWidget(idx, wrapper)

    def _keep_single(self, keep_id: int, cluster: list[dict[str, Any]]) -> None:
        with self.lock:
            self.engine.set_mark(keep_id, "keep")
            for p in cluster:
                if p["id"] != keep_id:
                    self.engine.set_mark(p["id"], "hidden")
        QMessageBox.information(self, "Resolved", "Marked keeper photo and hidden redundant copies.")
        self.reload_data()
        self.state.invalidate()
