"""Interactive Fullscreen Lightbox Modal with Pan/Zoom, Face Overlay Toggle, and Metadata Inspector."""
from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap, QWheelEvent
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from engine import Engine
from gui.face_labels import face_display_name
from gui.safe_call import safe_call
from gui.theme_manager import get_active_theme
from gui.views.date_dialogs import DateOverrideDialog
from gui.widgets import clear_pixmap_cache

_FAIL = object()


class FaceRectItem(QGraphicsRectItem):
    """Clickable face rectangle that carries face metadata."""

    def __init__(self, rect: QRectF, face_data: dict[str, Any], parent: QGraphicsItem | None = None) -> None:
        super().__init__(rect, parent)
        self.face_data = face_data
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class InteractivePhotoView(QGraphicsView):
    """High-resolution zoomable and pannable image canvas with toggleable face bounding boxes."""

    face_clicked = pyqtSignal(dict, object)  # face_data, screen_pos
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
        self.face_items: list[QGraphicsItem] = []
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
        fill_col.setAlpha(36)

        solid_pen = QPen(accent_col, 2.2)
        dashed_pen = QPen(accent_col, 1.8)
        dashed_pen.setStyle(Qt.PenStyle.DashLine)

        tag_bg_col = QColor(0, 0, 0, 190) if theme.is_dark else QColor(255, 255, 255, 220)
        tag_text_col = QColor(255, 255, 255) if theme.is_dark else QColor(20, 20, 20)
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        fm = QFontMetrics(font)

        for f in faces:
            bx = float(f.get("x", 0)) * sx
            by = float(f.get("y", 0)) * sy
            bw = float(f.get("w", 0)) * sx
            bh = float(f.get("h", 0)) * sy
            rect = QRectF(bx, by, bw, bh)

            display_name = face_display_name(f)
            if display_name:
                rect_item = FaceRectItem(rect, f)
                rect_item.setPen(solid_pen)
                rect_item.setBrush(fill_col)
                rect_item.setToolTip(f"{display_name} (Click to manage)")
                self.scene.addItem(rect_item)
                self.face_items.append(rect_item)

                # Label tag
                tag_w = fm.horizontalAdvance(display_name) + 12
                tag_h = fm.height() + 4
                tag_x = bx + (bw - tag_w) / 2.0
                tag_y = by + bh + 4 if (by + bh + tag_h + 4 < pixmap.height()) else max(0.0, by - tag_h - 4)
                tag_rect = QRectF(tag_x, tag_y, tag_w, tag_h)

                bg_item = self.scene.addRect(tag_rect, QPen(Qt.PenStyle.NoPen), tag_bg_col)
                txt_item = self.scene.addSimpleText(display_name, font)
                txt_item.setBrush(tag_text_col)
                txt_item.setPos(tag_x + 6, tag_y + 2)
                self.face_items.extend([bg_item, txt_item])
            else:
                rect_item = FaceRectItem(rect, f)
                rect_item.setPen(dashed_pen)
                rect_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                rect_item.setToolTip("Click to name it")
                self.scene.addItem(rect_item)
                self.face_items.append(rect_item)

        self.reset_fit()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if isinstance(item, FaceRectItem):
                self.face_clicked.emit(item.face_data, event.globalPosition().toPoint())

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
        self._changed: bool = False
        self._meta_labels: dict[str, QLabel] = {}

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
        self.canvas.face_clicked.connect(self._on_face_clicked)
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

        tags_str = ", ".join(t["label"] for t in (
            safe_call(self, self.engine.get_tags, self.image_id, default=[]) or [])) or "—"

        meta_rows = [
            ("Date Taken", self.photo_data.get("effective_ts") or self.photo_data.get("exif_ts") or "Unknown"),
            ("Resolution", f"{self.photo_data.get('width', 0)} × {self.photo_data.get('height', 0)}"),
            ("Format", (self.photo_data.get("format") or "Unknown").upper()),
            ("Faces Detected", str(len(self.photo_data.get("faces", [])))),
            ("Quality Score", f"{round(float(self.photo_data.get('quality', 0)))}%" if self.photo_data.get("quality") else "N/A"),
            ("Tags", tags_str),
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
            self._meta_labels[label] = v_lbl
            box.addWidget(lbl)
            box.addWidget(v_lbl)
            info_layout.addLayout(box)

        info_layout.addStretch()
        scroll.setWidget(info_widget)
        d_layout.addWidget(scroll, stretch=1)

        # Quick Actions
        self.btn_fav = QPushButton()
        self.btn_fav.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fav.clicked.connect(lambda: self._toggle_mark("favourite"))
        d_layout.addWidget(self.btn_fav)

        self.btn_hide = QPushButton()
        self.btn_hide.setProperty("class", "Secondary")
        self.btn_hide.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hide.clicked.connect(lambda: self._toggle_mark("hidden"))
        d_layout.addWidget(self.btn_hide)
        self._refresh_mark_buttons()

        date_row = QHBoxLayout()
        b_date = QPushButton("Correct Date…")
        b_date.setProperty("class", "Secondary")
        b_date.clicked.connect(self._correct_date)
        b_orig = QPushButton("Restore Date")
        b_orig.setProperty("class", "Secondary")
        b_orig.clicked.connect(self._restore_date)
        date_row.addWidget(b_date)
        date_row.addWidget(b_orig)
        d_layout.addLayout(date_row)

        b_sim = QPushButton("Find Similar")
        b_sim.setProperty("class", "Secondary")
        b_sim.clicked.connect(self._find_similar)
        d_layout.addWidget(b_sim)

        self._live = safe_call(self, self.engine.live_video, self.image_id, default=None)
        self.btn_live = QPushButton("▶  Play Live Photo")
        self.btn_live.setVisible(bool(self._live and Path(self._live.get("path", "")).is_file()))
        self.btn_live.clicked.connect(self._play_live)
        d_layout.addWidget(self.btn_live)

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

    def _marks(self) -> set[str]:
        rows = safe_call(self, self.engine.get_marks, self.image_id, default=[]) or []
        return {m["kind"] for m in rows}

    def _refresh_mark_buttons(self) -> None:
        marks = self._marks()
        self.btn_fav.setText("★  Remove from Favourites" if "favourite" in marks
                             else "☆  Mark as Favourite")
        self.btn_hide.setText("Unhide Photo" if "hidden" in marks else "Hide Photo")

    def _toggle_mark(self, kind: str) -> None:
        if kind in self._marks():
            safe_call(self, self.engine.clear_mark, self.image_id, kind)
        else:
            safe_call(self, self.engine.set_mark, self.image_id, kind)
        self._changed = True                      # gallery refreshes on close
        self._refresh_mark_buttons()

    def _correct_date(self) -> None:
        cur = self.photo_data.get("effective_ts") or self.photo_data.get("exif_ts")
        dlg = DateOverrideDialog(cur, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        iso = dlg.value_iso()
        if safe_call(self, self.engine.set_date_override, self.image_id, iso,
                     "manual (lightbox)", default=_FAIL) is _FAIL:
            return
        self.photo_data["effective_ts"] = iso
        if "Date Taken" in self._meta_labels:
            self._meta_labels["Date Taken"].setText(iso)
        self._changed = True

    def _restore_date(self) -> None:
        safe_call(self, self.engine.clear_date_override, self.image_id)
        row = safe_call(self, self.engine.get_image, self.image_id, default=None) or {}
        ts = row.get("exif_ts") or "Unknown"
        self.photo_data["effective_ts"] = row.get("exif_ts")
        if "Date Taken" in self._meta_labels:
            self._meta_labels["Date Taken"].setText(ts)
        self._changed = True

    def _find_similar(self) -> None:
        from gui.views.similar_dialog import SimilarDialog
        dlg = SimilarDialog(self.engine, self.lock, self.image_id, self)
        dlg.photo_opened.connect(
            lambda p: PhotoDetailDialog(p, self.engine, self.lock, self).exec())
        dlg.exec()

    def _play_live(self) -> None:
        try:
            from gui.views.live_dialog import LivePhotoDialog
            dlg = LivePhotoDialog(self._live["path"], self)
        except ImportError:
            QMessageBox.information(self, "Live Photo", "Video playback (QtMultimedia) is not available.")
            return
        dlg.exec()

    def _on_face_clicked(self, face_data: dict[str, Any], screen_pos: Any) -> None:
        face_id = face_data.get("id")
        if not face_id:
            return

        menu = QMenu(self)
        act_name = menu.addAction("Name this face...")
        act_assign = menu.addAction("Assign to existing person...")
        act_remove = menu.addAction("Remove from person")

        chosen = menu.exec(screen_pos)
        if not chosen:
            return

        if chosen == act_name:
            current_name = face_data.get("person_name") or ""
            name, ok = QInputDialog.getText(self, "Name Face", "Enter person's name:", text=current_name)
            if ok and name.strip():
                safe_call(self, self.engine.name_face, face_id, name.strip())
                clear_pixmap_cache()
                self._reload_faces_and_canvas()
        elif chosen == act_assign:
            persons = safe_call(self, self.engine.get_persons, default=[]) or []
            if not persons:
                QMessageBox.information(self, "Assign", "No persons exist yet.")
                return
            items = [f"{p['id']}: {p['name']}" for p in persons]
            sel, ok = QInputDialog.getItem(self, "Assign Person", "Choose person:", items, 0, False)
            if ok and sel:
                pid = int(sel.split(":")[0])
                safe_call(self, self.engine.assign_face, face_id, pid)
                clear_pixmap_cache()
                self._reload_faces_and_canvas()
        elif chosen == act_remove:
            safe_call(self, self.engine.assign_face, face_id, None)
            clear_pixmap_cache()
            self._reload_faces_and_canvas()

    def _reload_faces_and_canvas(self) -> None:
        faces_dict = safe_call(self, self.engine.get_faces_many, [self.image_id], default={}) or {}
        new_faces = faces_dict.get(self.image_id, [])
        self.photo_data["faces"] = new_faces
        self.btn_faces.setText(f"Face Boxes ({len(new_faces)})")
        self._load_photo()
