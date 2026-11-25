"""Photos with similar whole-image content (needs stored embeddings)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.tasks import EngineTask, enrich_photos
from gui.widgets import PhotoCardWidget

COLS = 4


class SimilarDialog(QDialog):
    photo_opened = pyqtSignal(dict)

    def __init__(self, engine, lock, image_id: int, parent=None) -> None:
        super().__init__(parent)
        self.engine, self.lock, self.image_id = engine, lock, image_id
        self.setWindowTitle("Similar Photos")
        self.resize(1040, 640)
        lay = QVBoxLayout(self)
        self.status = QLabel("Searching…")
        self.status.setProperty("class", "Dim")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("ScrollContainer")
        self.grid = QGridLayout(body)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid.setSpacing(14)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        close = QPushButton("Close")
        close.setProperty("class", "Secondary")
        close.clicked.connect(self.accept)
        lay.addWidget(close)

        self.task = EngineTask(self._work, parent=self)
        self.task.success.connect(self._show)
        self.task.failed.connect(lambda m: self.status.setText(m))
        self.task.start()

    def _work(self):
        items = self.engine.similar(self.image_id, 24)      # brute force: keep off the UI thread
        enrich_photos(self.engine, items)
        return items

    def _show(self, items: list) -> None:
        self.status.setText(
            f"{len(items)} similar photo(s), best match first."
            if items
            else "No similar photos found."
        )
        for i, it in enumerate(items):
            box = QVBoxLayout()
            card = PhotoCardWidget(it, thumb_path=it.get("thumb_path"))
            card.clicked.connect(lambda _, p=it: self.photo_opened.emit(p))
            box.addWidget(card)
            pct = QLabel(f"{round(float(it.get('similarity', 0)) * 100)}% similar")
            pct.setProperty("class", "Dim")
            pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(pct)
            holder = QWidget()
            holder.setLayout(box)
            self.grid.addWidget(holder, i // COLS, i % COLS)

    def done(self, result: int) -> None:
        self.task.wait(15000)
        super().done(result)
