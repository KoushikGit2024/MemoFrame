"""Burst sequences: keep the sharpest frame, hide the rest."""
from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QListWidgetItem, QWidget

from gui.safe_call import safe_call
from gui.views.duplicates_view import DuplicatesView
from gui.widgets import EmptyStateWidget


class BurstsView(DuplicatesView):
    def __init__(self, state, engine, lock, parent: QWidget | None = None) -> None:
        super().__init__(state, engine, lock, parent)
        self._bursts: list[dict[str, Any]] = []
        self._hidden: set[int] = set()
        self.title_lbl.setText("Burst Sequences (0)")
        if hasattr(self, "sub_lbl"):
            self.sub_lbl.setText("Rapid-fire sequences. Keep the sharpest frame and hide the rest in one click.")

    def reload_data(self) -> None:
        marks = lambda kind: {int(m["image_id"]) for m in
                              (safe_call(self, self.engine.get_marks, None, kind, default=[]) or [])}
        self._hidden = marks("hidden")
        resolved = self._hidden | marks("keep")
        bursts = safe_call(self, self.engine.get_bursts, default=[]) or []
        # resolved = its best frame was kept or hidden by the user
        self._bursts = [b for b in bursts if int(b.get("image_count", 0)) > 1
                        and b.get("best_image_id") not in resolved]
        self.clusters = [None] * len(self._bursts)               # type: ignore[list-item]
        self.title_lbl.setText(f"Burst Sequences ({len(self._bursts)})")
        self.cluster_list.clear()
        self._clear_comparison()
        if not self._bursts:
            self.cluster_title.setText("No bursts to review")
            self.cards_layout.insertWidget(0, EmptyStateWidget(
                "▤", "No Burst Sequences", "Bursts appear after a scan finds rapid-fire photos."))
            return
        for i, b in enumerate(self._bursts, start=1):
            self.cluster_list.addItem(QListWidgetItem(f"Burst #{i}  ·  {b['image_count']} frames"))
        self.cluster_list.setCurrentRow(0)

    def _load_burst(self, b: dict[str, Any]) -> list[dict[str, Any]]:
        imgs = safe_call(self, self.engine.get_burst_images, b["id"], default=[]) or []
        imgs = [dict(i) for i in imgs if i.get("state") != "missing" and int(i["id"]) not in self._hidden]
        for i in imgs:
            i["suggested_keep"] = i["id"] == b.get("best_image_id")
            i["kind"] = "burst"
        return imgs

    def _on_cluster_selected(self, row: int) -> None:
        if not (0 <= row < len(self._bursts)):
            return
        if self.clusters[row] is None:                           # lazy: one query per opened burst
            self.clusters[row] = self._load_burst(self._bursts[row])
        super()._on_cluster_selected(row)
