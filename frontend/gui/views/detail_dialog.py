"""Interactive Fullscreen Lightbox Modal with Pan/Zoom, Face Overlay Toggle, and Metadata Inspector."""
from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QWheelEvent
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from engine import Engine
from gui.theme_manager import get_active_theme


class InteractivePhotoView(QGraphicsView):
    """High-resolution zoomable and pannable image canvas with toggleable face bounding boxes."""

    face_clicked = pyqtSignal(dict)
    zoom_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.pixmap_item: QGraphicsPixmapItem | None = None
        self.face_items: list[QGraphicsRectItem] = []
        self.faces: list[dict[str, Any]] = []
        self._user_zoomed: bool = False
        self._zoom_factor: float = 1.0

    def set_image(self, pixmap: QPixmap, faces: list[dict[str, Any]], orig_w: int, orig_h: int) -> None:
        self.scene.clear()
        self.face_items.clear()
        self.faces = faces
        self._user_zoomed = False
        self._zoom_factor = 1.0

        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.setSceneRect(QRectF(pixmap.rect()))

        sx = pixmap.width() / float(orig_w or 1)
        sy = pixmap.height() / float(orig_h or 1)

        theme = get_active_theme()
        accent_col = QColor(theme.accent_hover if theme.is_dark else theme.accent)
        fill_col = QColor(accent_col)
        fill_col.setAlpha(42)
        pen = QPen(accent_col, 2.5)

        for f in faces:
            bx = float(f.get("x", 0)) * sx
            by = float(f.get("y", 0)) * sy
            bw = float(f.get("w", 0)) * sx
            bh = float(f.get("h", 0)) * sy

            rect_item = self.scene.addRect(QRectF(bx, by, bw, bh), pen, fill_col)
            rect_item.setCursor(Qt.CursorShape.PointingHandCursor)
            rect_item.setToolTip(f"Face Confidence: {round(float(f.get('confidence', 0)) * 100)}%")
            self.face_items.append(rect_item)

        self.reset_fit()

    def set_faces_visible(self, visible: bool) -> None:
        for item in self.face_items:
            item.setVisible(visible)

    def reset_fit(self) -> None:
        if self.pixmap_item is None:
            return
        self.resetTransform()
        self._user_zoomed = False
        self._zoom_factor = 1.0
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_changed.emit(100)

    def zoom_step(self, factor: float) -> None:
        new_zoom = max(0.25, min(8.0, self._zoom_factor * factor))
        applied = new_zoom / self._zoom_factor
        self._zoom_factor = new_zoom
        self._user_zoomed = True
        self.scale(applied, applied)
        self.zoom_changed.emit(round(self._zoom_factor * 100))

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.zoom_step(factor)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._user_zoomed and self.pixmap_item is not None:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class PhotoDetailDialog(QDialog):
    """Detailed photo inspector with zoom toolbar, interactive canvas, and themed metadata drawer."""

    def __init__(self, photo_data: dict[str, Any], engine: Engine, lock: threading.RLock, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.photo_data = photo_data
        self.engine = engine
        self.lock = lock
        self.image_id = photo_data.get("id", 0)
        self.file_path = photo_data.get("path", "")

        self.setWindowTitle(f"MemoFrame — {Path(self.file_path).name}")
        self.resize(1120, 760)
        self.setMinimumSize(820, 560)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        self._build_ui()
        self._load_photo()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # 1. Left Canvas & Zoom Toolbar Area
        canvas_container = QWidget()
        canvas_container.setObjectName("TransparentContainer")
        c_layout = QVBoxLayout(canvas_container)
        c_layout.setContentsMargins(14, 14, 10, 14)
        c_layout.setSpacing(10)

        toolbar = QFrame()
        toolbar.setProperty("class", "CanvasToolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(8)

        btn_out = QPushButton("−")
        btn_out.setProperty("class", "Secondary")
        btn_out.setFixedWidth(34)
        btn_out.setToolTip("Zoom Out")
        btn_out.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_out.clicked.connect(lambda: self.canvas.zoom_step(1 / 1.2))
        tb_layout.addWidget(btn_out)

        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setProperty("class", "Dim")
        self.zoom_lbl.setFixedWidth(44)
        self.zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb_layout.addWidget(self.zoom_lbl)

        btn_in = QPushButton("+")
        btn_in.setProperty("class", "Secondary")
        btn_in.setFixedWidth(34)
        btn_in.setToolTip("Zoom In")
        btn_in.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_in.clicked.connect(lambda: self.canvas.zoom_step(1.2))
        tb_layout.addWidget(btn_in)

        btn_fit = QPushButton("Fit")
        btn_fit.setProperty("class", "Secondary")
        btn_fit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fit.clicked.connect(lambda: self.canvas.reset_fit())
        tb_layout.addWidget(btn_fit)

        tb_layout.addStretch()

        self.btn_faces = QPushButton(f"Face Boxes ({len(self.photo_data.get('faces', []))})")
        self.btn_faces.setProperty("class", "Secondary")
        self.btn_faces.setCheckable(True)
        self.btn_faces.setChecked(True)
        self.btn_faces.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_faces.toggled.connect(lambda checked: self.canvas.set_faces_visible(checked))
        tb_layout.addWidget(self.btn_faces)

        c_layout.addWidget(toolbar)

        self.canvas = InteractivePhotoView()
        self.canvas.zoom_changed.connect(lambda pct: self.zoom_lbl.setText(f"{pct}%"))
        c_layout.addWidget(self.canvas, stretch=1)
        splitter.addWidget(canvas_container)

        # 2. Right Metadata & Actions Drawer
        drawer = QFrame()
        drawer.setProperty("class", "InspectorDrawer")
        drawer.setMinimumWidth(290)
        drawer.setMaximumWidth(360)
        d_layout = QVBoxLayout(drawer)
        d_layout.setContentsMargins(18, 18, 18, 18)
        d_layout.setSpacing(14)

        title = QLabel(Path(self.file_path).name or "Photo Details")
        title.setProperty("class", "Heading")
        title.setWordWrap(True)
        d_layout.addWidget(title)

        divider = QFrame()
        divider.setProperty("class", "NavDivider")
        d_layout.addWidget(divider)

        # Scrollable Metadata Fields
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        info_widget = QWidget()
        info_widget.setObjectName("ScrollContainer")
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 4, 0)
        info_layout.setSpacing(12)

        meta_rows = [
            ("Date Taken", self.photo_data.get("effective_ts") or self.photo_data.get("exif_ts") or "Unknown"),
            ("Resolution", f"{self.photo_data.get('width', 0)} × {self.photo_data.get('height', 0)}"),
            ("Format", (self.photo_data.get("format") or "Unknown").upper()),
            ("Faces Detected", str(len(self.photo_data.get("faces", [])))),
            ("Quality Score", f"{round(float(self.photo_data.get('quality', 0)))}%" if self.photo_data.get("quality") else "N/A"),
            ("File Path", self.file_path or "—"),
        ]

        for label, val in meta_rows:
            box = QVBoxLayout()
            box.setSpacing(2)
            lbl = QLabel(label.upper())
            lbl.setProperty("class", "MetaKey")
            v_lbl = QLabel(str(val))
            v_lbl.setProperty("class", "MetaValue")
            v_lbl.setWordWrap(True)
            v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.addWidget(lbl)
            box.addWidget(v_lbl)
            info_layout.addLayout(box)

        info_layout.addStretch()
        scroll.setWidget(info_widget)
        d_layout.addWidget(scroll, stretch=1)

        # Quick Actions
        btn_fav = QPushButton("★  Mark as Favourite")
        btn_fav.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fav.clicked.connect(self._toggle_favourite)
        d_layout.addWidget(btn_fav)

        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "Secondary")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        d_layout.addWidget(btn_close)

        splitter.addWidget(drawer)
        splitter.setSizes([790, 330])
        layout.addWidget(splitter)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.canvas.reset_fit()

    def _load_photo(self) -> None:
        if not Path(self.file_path).is_file():
            return
        try:
            with Image.open(self.file_path) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((1600, 1600), Image.Resampling.BILINEAR)
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=90)
                pix = QPixmap()
                pix.loadFromData(buf.getvalue())
                self.canvas.set_image(
                    pix,
                    self.photo_data.get("faces", []),
                    self.photo_data.get("width", im.width),
                    self.photo_data.get("height", im.height),
                )
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Could not load image: {exc}")

    def _toggle_favourite(self) -> None:
        with self.lock:
            self.engine.set_mark(self.image_id, "favourite")
        QMessageBox.information(self, "Success", "Photo marked as Favourite!")
