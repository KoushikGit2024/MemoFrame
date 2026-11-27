"""Plain data containers shared across the pipeline.

These are picklable dataclasses, so worker processes can return them to the
parent process. Faces carry geometry, confidence, and 128-d embeddings for
offline person clustering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Where an image's timestamp came from, most to least trustworthy.
TS_EXIF_ORIGINAL = "exif_original"
TS_EXIF_DATETIME = "exif_datetime"
TS_FILE_MTIME = "file_mtime"
TS_CONTAINER = "container_date"  # date read from a video file's header
TS_NONE = "none"


@dataclass(frozen=True)
class FaceBox:
    """One detected face in full-resolution, orientation-corrected pixels."""

    x: int
    y: int
    w: int
    h: int
    confidence: float
    label: str | None = None  # "Face 001"; assigned later, local to one image
    crop_path: str | None = None
    embedding: bytes | None = None  # 128-d float32 L2-normalized vector (512 bytes)
    person_id: int | None = None
    landmarks: tuple[float, ...] | None = None  # 5 (x, y) points, full-res px; never stored

    @property
    def area(self) -> int:
        return self.w * self.h

    def to_dict(self) -> dict[str, Any]:
        """Mapping accepted by ``DatabaseManager.save_results``."""
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "confidence": self.confidence,
            "label": self.label,
            "crop_path": self.crop_path,
            "embedding": self.embedding,
            "person_id": self.person_id,
        }


@dataclass(frozen=True)
class ImageMeta:
    """Metadata extracted from one image."""

    width: int
    height: int
    exif_ts: str | None = None  # 'YYYY-MM-DDTHH:MM:SS' (naive local time)
    ts_source: str = TS_NONE
    gps_lat: float | None = None
    gps_lon: float | None = None


@dataclass
class ImageRecord:
    """Everything computed for one image by a worker."""

    image_id: int
    path: Path
    meta: ImageMeta
    sha256: str | None = None
    phash: str | None = None  # 16 hex chars
    features: bytes | None = None  # colour-histogram bytes
    thumb_path: str | None = None
    faces: list[FaceBox] = field(default_factory=list)
    fmt: str | None = None  # decoder format name, e.g. "JPEG", "HEIF"

    def to_result(self) -> dict[str, Any]:
        """Mapping accepted by ``DatabaseManager.save_results``."""
        m = self.meta
        return {
            "image_id": self.image_id,
            "kind": "photo",
            "format": self.fmt,
            "width": m.width,
            "height": m.height,
            "sha256": self.sha256,
            "phash": self.phash,
            "exif_ts": m.exif_ts,
            "ts_source": m.ts_source,
            "gps_lat": m.gps_lat,
            "gps_lon": m.gps_lon,
            "features": self.features,
            "thumb_path": self.thumb_path,
            "faces": [f.to_dict() for f in self.faces],
        }
