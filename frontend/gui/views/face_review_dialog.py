"""Review one person's faces (fix wrong clusters) or browse faces that belong to nobody."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.safe_call import safe_call
from gui.widgets import AsyncAvatarLoader, get_cached_pixmap, set_cached_pixmap

PAGE, COLS, SIZE = 60, 6, 88
_FAIL = object()


class FaceChip(QFrame):
    action = pyqtSignal(str, dict)

    def __init__(self, face: dict[str, Any], removable: bool, parent=None) -> None:
        super().__init__(parent)
        self.face = face
        self.setProperty("class", "PersonRowCard")
        self.setFixedWidth(124)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)
        self.avatar = QLabel()
        self.avatar.setFixedSize(SIZE, SIZE)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setProperty("class", "ThumbCanvas")
        lay.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignHCenter)
        conf = QLabel(
            f"{round(float(face.get('confidence', 0)) * 100)}%"
            + ("  ✓ confirmed" if face.get("locked") else "")
        )
        conf.setProperty("class", "Dim")
        conf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(conf)
        buttons = [("Name…", "name"), ("Move to…" if removable else "Assign…", "assign")]
        if removable:
            buttons.append(("Remove", "remove"))
        for text, kind in buttons:
            b = QPushButton(text)
            b.setProperty("class", "Secondary")
            b.clicked.connect(lambda _=False, k=kind: self.action.emit(k, self.face))
            lay.addWidget(b)
        self._load()

    def _load(self) -> None:
        f = self.face
        key = f"chip_{f['id']}_{f['x']}_{f['y']}_{f['w']}"
        cached = get_cached_pixmap(key)
        if cached:
            self.avatar.setPixmap(cached)
            return
        path = f.get("path")
        if path and Path(path).is_file():
            self.avatar.setText("…")
            QThreadPool.globalInstance().start(
                AsyncAvatarLoader(
                    key,
                    str(path),
                    int(f["x"]),
                    int(f["y"]),
                    int(f["w"]),
                    int(f["h"]),
                    self._ready,
                )
            )
        else:
            self.avatar.setText("Offline")

    def _ready(self, key: str, img: QImage) -> None:
        try:
            pix = QPixmap.fromImage(img).scaled(
                SIZE,
                SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            set_cached_pixmap(key, pix)
            self.avatar.setPixmap(pix)
        except RuntimeError:
            pass


class FaceReviewDialog(QDialog):
    """person_id=None -> faces that belong to nobody; otherwise that person's faces."""

    def __init__(self, engine, lock, person_id: int | None = None, parent=None) -> None:
        super().__init__(parent)
        self.engine, self.lock, self.person_id = engine, lock, person_id
        self.dirty, self._shown = False, 0
        person = (
            safe_call(self, engine.get_person, person_id, default=None)
            if person_id is not None
            else None
        )
        self.setWindowTitle(f"Review faces: {person['name']}" if person else "Unassigned Faces")
        self.resize(900, 620)

        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(
            QLabel(
                "Faces that were removed from every person or never grouped. "
                "Name them or move them to a person."
                if person_id is None
                else "Move wrong faces elsewhere or remove them. "
                "Confirming locks the faces so boxes show this person's name."
            )
        )
        head.addStretch()
        if person_id is not None:
            b = QPushButton("✓ Confirm all faces")
            b.clicked.connect(self._confirm_all)
            head.addWidget(b)
        lay.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("ScrollContainer")
        self.grid = QGridLayout(body)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid.setSpacing(10)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        self.empty_lbl = QLabel("No faces here.")
        self.empty_lbl.setProperty("class", "Dim")
        lay.addWidget(self.empty_lbl)
        foot = QHBoxLayout()
        self.btn_more = QPushButton("Load more")
        self.btn_more.setProperty("class", "Secondary")
        self.btn_more.clicked.connect(lambda: self._populate())
        foot.addWidget(self.btn_more)
        foot.addStretch()
        close = QPushButton("Close")
        close.setProperty("class", "Secondary")
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        lay.addLayout(foot)
        self._populate()

    def _fetch(self, limit: int, offset: int) -> list[dict[str, Any]]:
        if self.person_id is None:
            return safe_call(self, self.engine.get_unassigned_faces, limit, offset, default=[]) or []
        return (
            safe_call(self, self.engine.get_person_faces, self.person_id, limit, offset, default=[])
            or []
        )

    def _populate(self, reset: bool = False) -> None:
        if reset:
            limit, offset = max(PAGE, self._shown), 0
            while self.grid.count():
                w = self.grid.takeAt(0).widget()
                if w:
                    w.deleteLater()
            self._shown = 0
        else:
            limit, offset = PAGE, self._shown
        faces = self._fetch(limit, offset)
        for f in faces:
            chip = FaceChip(f, removable=self.person_id is not None)
            chip.action.connect(self._on_action)
            self.grid.addWidget(chip, self._shown // COLS, self._shown % COLS)
            self._shown += 1
        self.btn_more.setVisible(len(faces) >= limit)
        self.empty_lbl.setVisible(self._shown == 0)

    def _on_action(self, kind: str, face: dict) -> None:
        fid, ok = int(face["id"]), False
        if kind == "name":
            text, accepted = QInputDialog.getText(self, "Name this face", "Name:")
            if accepted and text.strip():
                ok = safe_call(self, self.engine.name_face, fid, text.strip(), default=_FAIL) is not _FAIL
        elif kind == "assign":
            persons = [
                p
                for p in (safe_call(self, self.engine.get_persons, default=[]) or [])
                if p["id"] != self.person_id
            ]
            if not persons:
                QMessageBox.information(self, "No people", "There is nobody to assign to yet.")
                return
            labels = {
                f"{p['name']}  (#{p['id']}, {p['image_count']} photos)": int(p["id"])
                for p in persons
            }
            pick, accepted = QInputDialog.getItem(self, "Assign face", "Person:", list(labels), 0, False)
            if accepted:
                ok = safe_call(self, self.engine.assign_face, fid, labels[pick], default=_FAIL) is not _FAIL
        elif kind == "remove":
            ok = safe_call(self, self.engine.assign_face, fid, None, default=_FAIL) is not _FAIL
        if ok:
            self.dirty = True
            self._populate(reset=True)

    def _confirm_all(self) -> None:
        n = safe_call(self, self.engine.confirm_person, self.person_id, default=None)
        if n is not None:
            self.dirty = True
            QMessageBox.information(self, "Confirmed", f"{n} face(s) confirmed. Boxes now show the name.")
            self._populate(reset=True)
