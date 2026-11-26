"""Central configuration for the photo organizer.

All tunable values live in the :class:`Settings` dataclass. The CLI builds a
``Settings`` instance and passes it around, so modules never read globals or
environment variables directly.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
)
HEIC_EXTENSIONS = frozenset({".heic", ".heif"})
RAW_EXTENSIONS = frozenset({".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v"})


def default_extensions() -> frozenset[str]:
    """Extensions to scan. HEIC and RAW only count if their library is installed."""
    exts = set(SUPPORTED_EXTENSIONS) | VIDEO_EXTENSIONS
    if importlib.util.find_spec("pillow_heif"):
        exts |= HEIC_EXTENSIONS
    if importlib.util.find_spec("rawpy"):
        exts |= RAW_EXTENSIONS
    return frozenset(exts)


# YuNet face detector (detection only, no embeddings).
# If YUNET_SHA256 is empty, the downloader skips hash verification.
YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"

# SFace face recognizer (extracts 128-d feature embeddings for face clustering).
SFACE_FILENAME = "face_recognition_sface_2021dec.onnx"
SFACE_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
    "face_recognition_sface/face_recognition_sface_2021dec.onnx"
)
SFACE_SHA256 = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"

# Scene tagging classifier (MobileNetV2 ONNX + 1000 ImageNet synset labels).
SCENE_MODEL_FILENAME = "scene_model.onnx"
SCENE_MODEL_URL = (
    "https://github.com/onnx/models/raw/main/validated/vision/classification/"
    "mobilenet/model/mobilenetv2-12.onnx"
)
SCENE_LABELS_FILENAME = "scene_labels.txt"
SCENE_LABELS_URL = (
    "https://raw.githubusercontent.com/onnx/models/main/validated/vision/"
    "classification/synset.txt"
)


# Repository Root and Standard Workspace Resolution
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE: Path = REPO_ROOT / "workspace"


def _default_workers() -> int:
    """Leave one core free and cap at 4 (Windows spawns full interpreters)."""
    return max(1, min((os.cpu_count() or 2) - 1, 4))


@dataclass(frozen=True)
class Settings:
    """Immutable application settings. Use :meth:`with_overrides` to change."""

    # --- Workspace -------------------------------------------------------
    workspace: Path = field(default_factory=lambda: DEFAULT_WORKSPACE)

    # --- Scanning / pipeline --------------------------------------------
    extensions: frozenset[str] = field(default_factory=default_extensions)
    batch_size: int = 64
    workers: int = field(default_factory=_default_workers)
    hash_chunk_bytes: int = 1024 * 1024
    cv_threads: int = 1  # OpenCV threads per worker
    cpu_limit: float = 1.0  # 0.1-1.0 duty cycle per worker (1.0 = no throttle)
    low_priority: bool = True  # run below normal OS priority
    worker_recycle_tasks: int = 50  # restart a worker after N images (frees memory)
    min_free_mem_mb: int = 1024  # memory guard floor (used from Phase A)
    storage_type: str = "hdd"  # "hdd" caps workers at 2 (seek-bound); "ssd" does not
    thumb_cache_max_mb: int = 0  # 0 = unlimited

    # --- Face detection --------------------------------------------------
    detector_backend: str = "yunet"  # "yunet" | "insightface"
    face_recognition: bool = True  # extract 128-d embeddings with SFace
    confidence_threshold: float = 0.7
    nms_threshold: float = 0.3
    max_detect_side: int = 1280  # downscale long side before detection
    min_face_px: int = 20  # ignore boxes smaller than this (full-res px)
    use_gpu: bool = False

    # --- Outputs ---------------------------------------------------------
    thumbnail_size: int = 256
    face_thumb_size: int = 160
    face_crop_margin: float = 0.25  # fraction of box size added around crops
    jpeg_quality: int = 90
    save_annotated: bool = True
    save_face_crops: bool = True

    # --- Duplicates ------------------------------------------------------
    phash_near_threshold: int = 6  # max Hamming distance of 64-bit pHash

    # --- Grouping --------------------------------------------------------
    event_gap_hours: float = 3.0
    gps_split_km: float = 5.0
    visual_cluster_distance: float = 0.35  # agglomerative distance (undated images)
    min_group_size: int = 1

    # --- Phase D ---------------------------------------------------------
    tiled_detection: bool = False  # extra small-face pass on large photos (slow)
    tile_size: int = 960
    tile_source_side: int = 3200  # long side the tiles are cut from
    dhash_confirm_threshold: int = 12  # dHash veto for near duplicates; 64 disables
    burst_gap_seconds: float = 2.0
    burst_hash_threshold: int = 14
    min_burst_size: int = 3
    refine_min_event_size: int = 3
    refine_merge_gap_hours: float = 6.0
    refine_max_event_hours: float = 36.0
    place_max_km: float = 50.0
    group_screenshots: bool = False  # include screenshots/documents in events

    # --- Phase F (scene tags; enabled by default) -------------------------
    tagging_enabled: bool = True
    tags_top_k: int = 5
    tags_min_score: float = 0.15
    store_embeddings: bool = True  # needed for "find similar"
    tag_model_file: str = "scene_model.onnx"
    tag_labels_file: str = "scene_labels.txt"

    # --- Phase G (watch mode) ---------------------------------------------
    watch_interval_s: float = 30.0  # seconds between polls
    watch_settle_s: float = 10.0  # a file must be at least this old and unchanged
    watch_pause_on_battery: bool = True

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
    def generated_dir(self) -> Path:
        return self.thumbnails_dir

    @property
    def log_path(self) -> Path:
        return self.workspace / "photo_organizer.log"

    @property
    def yunet_path(self) -> Path:
        return self.models_dir / YUNET_FILENAME

    @property
    def sface_path(self) -> Path:
        return self.models_dir / SFACE_FILENAME

    @property
    def tag_dir(self) -> Path:
        return self.models_dir / "tags"

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
