"""Central configuration for the photo organizer.

All tunable values live in the :class:`Settings` dataclass. The CLI builds a
``Settings`` instance and passes it around, so modules never read globals or
environment variables directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
)

# YuNet face detector (detection only, no embeddings).
# TODO(verify): confirm the URL still resolves and fill in the SHA-256.
# If YUNET_SHA256 is empty, the downloader skips hash verification, logs the
# hash it computed, and warns. Paste that value here to pin the file.
YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


def _default_workers() -> int:
    """Leave one core free and cap at 4 (Windows spawns full interpreters)."""
    return max(1, min((os.cpu_count() or 2) - 1, 4))


@dataclass(frozen=True)
class Settings:
    """Immutable application settings. Use :meth:`with_overrides` to change."""

    # --- Workspace -------------------------------------------------------
    workspace: Path = Path("workspace")

    # --- Scanning / pipeline --------------------------------------------
    extensions: frozenset[str] = SUPPORTED_EXTENSIONS
    batch_size: int = 64
    workers: int = field(default_factory=_default_workers)
    hash_chunk_bytes: int = 1024 * 1024
    cv_threads: int = 1                      # OpenCV threads per worker
    cpu_limit: float = 1.0                   # 0.1-1.0 duty cycle per worker (1.0 = no throttle)
    low_priority: bool = True                # run below normal OS priority
    worker_recycle_tasks: int = 50           # restart a worker after N images (frees memory)

    # --- Face detection --------------------------------------------------
    detector_backend: str = "yunet"          # "yunet" | "insightface"
    confidence_threshold: float = 0.7
    nms_threshold: float = 0.3
    max_detect_side: int = 1280              # downscale long side before detection
    min_face_px: int = 20                    # ignore boxes smaller than this (full-res px)
    use_gpu: bool = False

    # --- Outputs ---------------------------------------------------------
    thumbnail_size: int = 256
    face_thumb_size: int = 160
    face_crop_margin: float = 0.25           # fraction of box size added around crops
    jpeg_quality: int = 90
    save_annotated: bool = True
    save_face_crops: bool = True

    # --- Duplicates ------------------------------------------------------
    phash_near_threshold: int = 6            # max Hamming distance of 64-bit pHash

    # --- Grouping --------------------------------------------------------
    event_gap_hours: float = 3.0
    gps_split_km: float = 5.0
    visual_cluster_distance: float = 0.35    # agglomerative distance (undated images)
    min_group_size: int = 1

    # --- Derived paths ---------------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.workspace / "photos.db"

    @property
    def models_dir(self) -> Path:
        return self.workspace / "models"

    @property
    def thumbnails_dir(self) -> Path:
        return self.workspace / "thumbnails"

    @property
    def face_crops_dir(self) -> Path:
        return self.workspace / "face_crops"

    @property
    def annotated_dir(self) -> Path:
        return self.workspace / "annotated"

    @property
    def grouped_dir(self) -> Path:
        return self.workspace / "grouped_images"

    @property
    def reports_dir(self) -> Path:
        return self.workspace / "reports"

    @property
    def log_path(self) -> Path:
        return self.workspace / "photo_organizer.log"

    @property
    def yunet_path(self) -> Path:
        return self.models_dir / YUNET_FILENAME

    def output_dirs(self) -> tuple[Path, ...]:
        """All directories that must exist before processing starts."""
        return (
            self.workspace,
            self.models_dir,
            self.thumbnails_dir,
            self.face_crops_dir,
            self.annotated_dir,
            self.grouped_dir,
            self.reports_dir,
        )

    def ensure_dirs(self) -> None:
        """Create the workspace tree (idempotent)."""
        for directory in self.output_dirs():
            directory.mkdir(parents=True, exist_ok=True)

    def with_overrides(self, **changes: Any) -> "Settings":
        """Return a copy with ``None`` values ignored (handy for CLI args)."""
        return replace(self, **{k: v for k, v in changes.items() if v is not None})