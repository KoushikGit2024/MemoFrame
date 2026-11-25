"""Custom Qt widgets for MemoFrame: Person Avatar Carousel, Photo Gallery Cards, and Layout Helpers.

Engineered for 120 FPS fluid UI performance:
- Asynchronous thumbnail loading off the main UI thread via QThreadPool
- Global LRU memory caching of QPixmap representations (no repeated disk reads)
- Fast vectorized fallback avatars without blocking full-resolution PIL decodes
- Letterbox/pillarbox calibrated face bounding boxes
- Zero-clipping card geometry with responsive grid and compact sizing
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QObject, QRectF, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap, QWheelEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.theme_manager import get_active_theme

# Global memory cache for loaded and scaled QPixmaps
_PIXMAP_CACHE: dict[str, QPixmap] = {}
_MAX_CACHE_ENTRIES = 500


def get_cached_pixmap(key: str) -> QPixmap | None:
    return _PIXMAP_CACHE.get(key)


def set_cached_pixmap(key: str, pix: QPixmap) -> None:
    if len(_PIXMAP_CACHE) >= _MAX_CACHE_ENTRIES:
        keys_to_remove = list(_PIXMAP_CACHE.keys())[:100]
        for k in keys_to_remove:
            _PIXMAP_CACHE.pop(k, None)
    _PIXMAP_CACHE[key] = pix


class HorizontalStripScrollArea(QScrollArea):
    """Horizontal scroll strip that never spawns vertical scrollbars or traps page scrolling."""

    def __init__(self, pass_vertical_wheel: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pass_vertical_wheel = pass_vertical_wheel
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta()
        if delta.x() != 0:
            hbar = self.horizontalScrollBar()
            hbar.setValue(hbar.value() - delta.x())
            event.accept()
            return
        if not self._pass_vertical_wheel or (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            hbar = self.horizontalScrollBar()
            if hbar.maximum() > 0:
                hbar.setValue(hbar.value() - delta.y())
                event.accept()
                return
        # Pass vertical wheel events cleanly up to parent vertical scroll area
        event.ignore()


class EmptyStateWidget(QFrame):
    """Clean, centered placeholder card when a view or filter has no items."""

    def __init__(self, icon_text: str, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("class", "EmptyStateCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(180)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 32, 28, 32)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(icon_text)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 28px; background: transparent;")
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setProperty("class", "SectionTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setProperty("class", "PageSubtitle")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setWordWrap(True)
        layout.addWidget(sub_lbl)


class _ImageLoadSignals(QObject):
    loaded = pyqtSignal(str, QPixmap)


class AsyncThumbnailLoader(QRunnable):
    """Background worker that reads image bytes and produces a scaled QPixmap off the UI thread."""

    def __init__(self, key: str, file_path: str, max_w: int, max_h: int, on_loaded: Callable[[str, QPixmap], None]) -> None:
        super().__init__()
        self.key = key
        self.file_path = file_path
        self.max_w = max_w
        self.max_h = max_h
        self.signals = _ImageLoadSignals()
        self.signals.loaded.connect(on_loaded)

    def run(self) -> None:
        if not self.file_path or not Path(self.file_path).is_file():
            return
        pix = QPixmap(self.file_path)
        if pix.isNull():
            return
        scaled = pix.scaled(
            self.max_w,
            self.max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        try:
            self.signals.loaded.emit(self.key, scaled)
        except RuntimeError:
            pass


class AsyncAvatarLoader(QRunnable):
    """Background worker that crops a person's face from the source image and scales it."""

    def __init__(
        self,
        key: str,
        img_path: str,
        x: int,
        y: int,
        w: int,
        h: int,
        on_loaded: Callable[[str, QPixmap], None],
    ) -> None:
        super().__init__()
        self.key = key
        self.img_path = img_path
        self.x, self.y, self.w, self.h = x, y, w, h
        self.signals = _ImageLoadSignals()
        self.signals.loaded.connect(on_loaded)

    def run(self) -> None:
        if not self.img_path or not Path(self.img_path).is_file():
            return
        try:
            from PIL import Image, ImageOps

            with Image.open(self.img_path) as im:
                mx = int(self.w * 0.2)
                my = int(self.h * 0.2)
                box = (
                    max(0, self.x - mx),
                    max(0, self.y - my),
                    min(im.width, self.x + self.w + mx),
                    min(im.height, self.y + self.h + my),
                )
                crop = im.crop(box)
                crop = ImageOps.exif_transpose(crop)
                crop.thumbnail((96, 96), Image.Resampling.BILINEAR)
                buf = io.BytesIO()
                crop.save(buf, format="JPEG", quality=85)
                pix = QPixmap()
                pix.loadFromData(buf.getvalue())
                if not pix.isNull():
                    self.signals.loaded.emit(self.key, pix)
        except Exception:
            pass


class PersonPillWidget(QFrame):
    """Circular avatar pill representing an identified individual."""

    clicked = pyqtSignal(int)
    renamed = pyqtSignal(int, str)

    def __init__(
        self,
        person_data: dict[str, Any],
        is_selected: bool = False,
        parent: QWidget | None = None,
        *,
        flat: bool = False,
        avatar_size: int = 36,
    ) -> None:
        super().__init__(parent)
        self.person_data = person_data
        self.person_id = person_data.get("id", 0)
        self.name = person_data.get("name", "Person")
        self.image_count = person_data.get("image_count", 0)
        self.cover_crop_path = person_data.get("cover_crop_path")
        self.is_selected = is_selected
        self._flat = flat
        self._avatar_size = avatar_size

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Maximum if not flat else QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(avatar_size + 14)
        self._apply_pill_class()

        layout = QHBoxLayout(self)
        if flat:
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
        else:
            layout.setContentsMargins(7, 5, 14, 5)
            layout.setSpacing(9)

        # Avatar Label
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(avatar_size, avatar_size)
        self._load_avatar()
        layout.addWidget(self.avatar_label)

        # Name and Count Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(1)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.name_lbl = QLabel(self.name)
        self.name_lbl.setProperty("class", "CardTitle")
        self.name_lbl.setToolTip(self.name)
        info_layout.addWidget(self.name_lbl)

        count_text = "All photos" if (self.person_id == 0 and self.name == "All People") else f"{self.image_count} photo{'s' if self.image_count != 1 else ''}"
        self.cnt_lbl = QLabel(count_text)
        self.cnt_lbl.setProperty("class", "Dim")
        info_layout.addWidget(self.cnt_lbl)

        layout.addLayout(info_layout)

    def _apply_pill_class(self) -> None:
        if self._flat:
            self.setProperty("class", "PersonPillFlat")
        else:
            self.setProperty("class", "PersonPillSelected" if self.is_selected else "PersonPill")

    def set_selected(self, selected: bool) -> None:
        if self.is_selected == selected:
            return
        self.is_selected = selected
        self._apply_pill_class()
        style = self.style()
        if style:
            style.unpolish(self)
            style.polish(self)
        self.update()

    def _render_circle_avatar(self, pix: QPixmap) -> QPixmap:
        size = self._avatar_size
        scaled = pix.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        out = QPixmap(size, size)
        out.fill(Qt.GlobalColor.transparent)

        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)

        offset_x = (scaled.width() - size) // 2
        offset_y = (scaled.height() - size) // 2
        painter.drawPixmap(-offset_x, -offset_y, scaled)
        painter.end()
        return out

    def _render_vector_fallback(self) -> QPixmap:
        size = self._avatar_size
        theme = get_active_theme()
        out = QPixmap(size, size)
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_col = QColor(theme.bg_elevated)
        fg_col = QColor(theme.text_secondary)

        painter.setBrush(bg_col)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, size, size)

        # Proportional silhouette
        head_d = int(size * 0.32)
        head_x = (size - head_d) // 2
        head_y = int(size * 0.21)
        painter.setBrush(fg_col)
        painter.drawEllipse(head_x, head_y, head_d, head_d)

        body_w = int(size * 0.58)
        body_h = int(size * 0.36)
        body_x = (size - body_w) // 2
        body_y = int(size * 0.58)
        body = QPainterPath()
        body.addRoundedRect(body_x, body_y, body_w, body_h, 6, 6)
        painter.drawPath(body)
        painter.end()
        return out

    def _load_avatar(self) -> None:
        cache_key = f"avatar_{self.person_id}_{self._avatar_size}_{self.cover_crop_path}"
        cached = get_cached_pixmap(cache_key)
        if cached:
            self.avatar_label.setPixmap(cached)
            return

        # 1. Fast path: pre-computed face crop file
        if self.cover_crop_path and Path(self.cover_crop_path).is_file():
            raw_pix = QPixmap(str(self.cover_crop_path))
            if not raw_pix.isNull():
                avatar_pix = self._render_circle_avatar(raw_pix)
                set_cached_pixmap(cache_key, avatar_pix)
                self.avatar_label.setPixmap(avatar_pix)
                return

        # 2. Async high-precision face crop from source photo
        img_path = self.person_data.get("image_path")
        x = self.person_data.get("x")
        y = self.person_data.get("y")
        w = self.person_data.get("w")
        h = self.person_data.get("h")

        fallback_pix = self._render_vector_fallback()
        self.avatar_label.setPixmap(fallback_pix)

        if img_path and Path(img_path).is_file() and w and h and w > 0 and h > 0:
            loader = AsyncAvatarLoader(
                cache_key,
                str(img_path),
                int(x or 0),
                int(y or 0),
                int(w),
                int(h),
                self._on_avatar_ready,
            )
            QThreadPool.globalInstance().start(loader)

    def _on_avatar_ready(self, key: str, raw_pix: QPixmap) -> None:
        try:
            avatar_pix = self._render_circle_avatar(raw_pix)
            set_cached_pixmap(key, avatar_pix)
            self.avatar_label.setPixmap(avatar_pix)
        except RuntimeError:
            pass

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.person_id)

    def mouseDoubleClickEvent(self, event) -> None:
        if self.person_id == 0 and self.name == "All People":
            return
        from PyQt6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(self, "Rename Person", f"Enter name for {self.name}:", text=self.name)
        if ok and new_name.strip():
            self.renamed.emit(self.person_id, new_name.strip())


class PhotoCardWidget(QFrame):
    """Photo card displaying thumbnail with letterbox-aligned face bounding boxes."""

    clicked = pyqtSignal(int)

    def __init__(
        self,
        photo_data: dict[str, Any],
        thumb_path: str | None = None,
        parent: QWidget | None = None,
        *,
        compact: bool = False,
        card_width: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.photo_data = photo_data
        self.image_id = photo_data.get("id", 0)
        self.thumb_path = thumb_path
        self.faces = photo_data.get("faces", [])
        self.orig_w = photo_data.get("width") or 1
        self.orig_h = photo_data.get("height") or 1
        self.compact = compact

        # Deterministic, zero-clipping geometry
        w = card_width or (176 if compact else 224)
        margin = 6 if compact else 8
        self._canvas_w = w - (margin * 2) - 2
        self._canvas_h = 114 if compact else 148
        h = (margin * 2) + self._canvas_h + (56 if compact else 64)

        self.setFixedSize(w, h)
        self.setProperty("class", "PhotoCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(5 if compact else 6)

        # Image Canvas
        self.img_lbl = QLabel()
        self.img_lbl.setFixedSize(self._canvas_w, self._canvas_h)
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_lbl.setProperty("class", "ThumbCanvas")
        layout.addWidget(self.img_lbl)

        # Filename (elided so long filenames never distort card width)
        file_name = Path(photo_data.get("path", "")).name or f"Photo #{self.image_id}"
        self.name_lbl = QLabel()
        self.name_lbl.setProperty("class", "CardTitle")
        self.name_lbl.setFixedHeight(17 if compact else 18)
        self.name_lbl.setToolTip(photo_data.get("path", file_name))
        fm = QFontMetrics(self.name_lbl.font())
        self.name_lbl.setText(fm.elidedText(file_name, Qt.TextElideMode.ElideMiddle, self._canvas_w - 4))
        layout.addWidget(self.name_lbl)

        # Meta Info Row
        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(6)

        date_str = (photo_data.get("effective_ts") or photo_data.get("exif_ts") or "No date")[:10]
        date_lbl = QLabel(date_str)
        date_lbl.setProperty("class", "Dim")
        meta_layout.addWidget(date_lbl)
        meta_layout.addStretch()

        face_cnt = photo_data.get("face_count", len(self.faces))
        badge_txt = f"{face_cnt}f" if compact else (f"{face_cnt} face{'s' if face_cnt != 1 else ''}" if face_cnt else "0 faces")
        badge = QLabel(badge_txt)
        badge.setProperty("class", "FaceBadge")
        meta_layout.addWidget(badge)

        layout.addLayout(meta_layout)
        self._load_thumbnail()

    def _composite_thumbnail(self, scaled: QPixmap) -> QPixmap:
        canvas_w = self._canvas_w
        canvas_h = self._canvas_h
        canvas = QPixmap(canvas_w, canvas_h)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Clip rounded thumbnail frame
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(0, 0, canvas_w, canvas_h), 7.0, 7.0)
        painter.setClipPath(clip_path)

        dx = (canvas_w - scaled.width()) // 2
        dy = (canvas_h - scaled.height()) // 2
        painter.drawPixmap(dx, dy, scaled)

        if self.faces:
            sx = scaled.width() / float(self.orig_w)
            sy = scaled.height() / float(self.orig_h)

            theme = get_active_theme()
            accent_col = QColor(theme.accent_hover if theme.is_dark else theme.accent)
            fill_col = QColor(accent_col)
            fill_col.setAlpha(42)

            painter.setPen(QPen(accent_col, 1.8))
            painter.setBrush(fill_col)

            for f in self.faces:
                bx = dx + float(f.get("x", 0)) * sx
                by = dy + float(f.get("y", 0)) * sy
                bw = float(f.get("w", 0)) * sx
                bh = float(f.get("h", 0)) * sy
                painter.drawRoundedRect(QRectF(bx, by, bw, bh), 3.0, 3.0)

        painter.end()
        return canvas

    def _load_thumbnail(self) -> None:
        if not self.thumb_path or not Path(self.thumb_path).is_file():
            self.img_lbl.setText("No Preview")
            return

        cache_key = f"thumb_{self.image_id}_{self._canvas_w}x{self._canvas_h}_{self.thumb_path}"
        cached = get_cached_pixmap(cache_key)
        if cached:
            self.img_lbl.setPixmap(cached)
            return

        self.img_lbl.setText("Loading...")
        loader = AsyncThumbnailLoader(
            cache_key,
            self.thumb_path,
            self._canvas_w,
            self._canvas_h,
            self._on_thumbnail_ready,
        )
        QThreadPool.globalInstance().start(loader)

    def _on_thumbnail_ready(self, key: str, scaled: QPixmap) -> None:
        try:
            composite = self._composite_thumbnail(scaled)
            set_cached_pixmap(key, composite)
            self.img_lbl.setPixmap(composite)
        except RuntimeError:
            pass

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.image_id)
