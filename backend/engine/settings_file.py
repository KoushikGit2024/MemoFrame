"""Load and validate ``config.toml`` from the workspace."""
from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from config import VIDEO_EXTENSIONS, Settings
from engine.errors import EngineError, ErrorCode
from engine.profiles import DEFAULT_PROFILE, apply_profile
from utils.file_utils import atomic_write_bytes

_log = logging.getLogger("photo_organizer.config")

CONFIG_NAME = "config.toml"

# Engine defaults: boxes live in the database, so no extra image files by default.
ENGINE_DEFAULTS: dict[str, Any] = {"save_annotated": False, "save_face_crops": False}

# key -> (type, min, max)
_FIELDS: dict[str, tuple[type, float | None, float | None]] = {
    "workers": (int, 1, 64),
    "batch_size": (int, 1, 1000),
    "confidence_threshold": (float, 0.0, 1.0),
    "min_face_px": (int, 1, 1000),
    "max_detect_side": (int, 320, 4096),
    "thumbnail_size": (int, 64, 1024),
    "face_thumb_size": (int, 32, 512),
    "phash_near_threshold": (int, 0, 16),
    "event_gap_hours": (float, 0.1, 168.0),
    "gps_split_km": (float, 0.0, 1000.0),
    "visual_cluster_distance": (float, 0.01, 1.5),
    "min_group_size": (int, 1, 1000),
    "cpu_limit": (float, 0.1, 1.0),
    "cv_threads": (int, 1, 16),
    "min_free_mem_mb": (int, 0, 65536),
    "save_face_crops": (bool, None, None),
    "save_annotated": (bool, None, None),
    "low_priority": (bool, None, None),
    "detector_backend": (str, None, None),
    "storage_type": (str, None, None),
    "thumb_cache_max_mb": (int, 0, 1_000_000),
    "face_recognition": (bool, None, None),
    "index_videos": (bool, None, None),
    "tiled_detection": (bool, None, None),
    "tile_size": (int, 320, 2048),
    "tile_source_side": (int, 1280, 8000),
    "dhash_confirm_threshold": (int, 0, 64),
    "burst_gap_seconds": (float, 0.1, 60.0),
    "burst_hash_threshold": (int, 0, 32),
    "min_burst_size": (int, 2, 50),
    "refine_min_event_size": (int, 1, 100),
    "refine_merge_gap_hours": (float, 0.0, 168.0),
    "refine_max_event_hours": (float, 1.0, 720.0),
    "place_max_km": (float, 1.0, 500.0),
    "group_screenshots": (bool, None, None),
    "tagging_enabled": (bool, None, None),
    "tags_top_k": (int, 1, 20),
    "tags_min_score": (float, 0.0, 1.0),
    "store_embeddings": (bool, None, None),
    "tag_model_file": (str, None, None),
    "tag_labels_file": (str, None, None),
    "watch_interval_s": (float, 1.0, 3600.0),
    "watch_settle_s": (float, 0.0, 3600.0),
    "watch_pause_on_battery": (bool, None, None),
}

TEMPLATE = """\
# Photo organizer settings. Delete a line to use its default.
profile = "balanced"          # gentle | balanced | fast
storage_type = "hdd"          # hdd | ssd (an HDD limits parallel reads)
thumb_cache_max_mb = 0        # 0 = no limit
index_videos = false         # true indexes .mp4/.mov/.m4v (videos are skipped by default)

# Explicit values below override the profile.
# workers = 2
# cpu_limit = 0.8             # 0.1 - 1.0
# batch_size = 32
# min_free_mem_mb = 1024      # pause when free RAM drops below this

confidence_threshold = 0.7    # face detection threshold, 0 - 1
min_face_px = 20
phash_near_threshold = 6      # near-duplicate sensitivity, 0 - 16
event_gap_hours = 3.0
gps_split_km = 5.0
thumbnail_size = 256

save_face_crops = false       # boxes are in the database; the app can draw them
save_annotated = false
tiled_detection = false       # slower; finds small faces in big group photos
group_screenshots = false
tagging_enabled = false       # scene tags; needs a model, see docs
store_embeddings = false      # enables "find similar" (about 2 KB per photo)
watch_interval_s = 30         # watch mode: seconds between folder checks
watch_settle_s = 10           # watch mode: file must be unchanged this long
watch_pause_on_battery = true
"""


def _bad(message: str) -> EngineError:
    return EngineError(ErrorCode.CONFIG_INVALID, f"{CONFIG_NAME}: {message}",
                       f"Fix or delete that line in {CONFIG_NAME}.")


def _check(key: str, value: Any) -> Any:
    kind, low, high = _FIELDS[key]
    if kind is bool:
        valid = isinstance(value, bool)
    elif kind is int:
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif kind is float:
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        valid = isinstance(value, str)
    if not valid:
        raise _bad(f"'{key}' must be {kind.__name__}, got {value!r}")
    if low is not None and not (low <= value <= high):
        raise _bad(f"'{key}' must be between {low} and {high}, got {value}")
    if key == "detector_backend" and value not in ("yunet", "insightface"):
        raise _bad("'detector_backend' must be 'yunet' or 'insightface'")
    if key == "storage_type" and value not in ("hdd", "ssd"):
        raise _bad("'storage_type' must be 'hdd' or 'ssd'")
    if key in ("tag_model_file", "tag_labels_file") and (not value or "/" in value or "\\" in value):
        raise _bad(f"'{key}' must be a file name only (no folders)")
    return float(value) if kind is float else value


def write_default_config(workspace: Path) -> Path:
    """Create ``config.toml`` with the template if it does not exist."""
    path = Path(workspace) / CONFIG_NAME
    if not path.exists():
        atomic_write_bytes(path, TEMPLATE.encode("utf-8"))
    return path


def load_settings(workspace: Path, profile: str | None = None, *,
                  strict: bool = True, warnings: list[str] | None = None) -> Settings:
    """Build :class:`Settings`: defaults, then profile, then explicit config values.

    strict=True  : any problem raises EngineError(CONFIG_INVALID).
    strict=False : bad lines are skipped and described in ``warnings`` (used by the GUI).
    """
    notes = warnings if warnings is not None else []

    def problem(message: str) -> None:
        if strict:
            raise _bad(message)
        _log.warning("%s: %s (ignored)", CONFIG_NAME, message)
        notes.append(message)

    workspace = Path(workspace).expanduser().resolve()
    path = workspace / CONFIG_NAME
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
            problem(f"cannot read file: {exc}")
            data = {}
    file_profile = data.pop("profile", None)
    if file_profile is not None and not isinstance(file_profile, str):
        problem("'profile' must be text")
        file_profile = None
    unknown = sorted(set(data) - set(_FIELDS))
    if unknown:
        problem(f"unknown setting(s): {', '.join(unknown)}")
        for key in unknown:
            data.pop(key)

    clean: dict[str, Any] = {}
    for key, value in data.items():
        try:
            clean[key] = _check(key, value)
        except EngineError as exc:
            if strict:
                raise
            notes.append(exc.message)
            _log.warning("%s (ignored)", exc.message)

    index_videos = clean.pop("index_videos", False)
    settings = Settings(workspace=workspace).with_overrides(**ENGINE_DEFAULTS)
    try:
        settings = apply_profile(settings, profile or file_profile or DEFAULT_PROFILE)
    except EngineError as exc:
        if strict:
            raise
        notes.append(exc.message)
        settings = apply_profile(settings, DEFAULT_PROFILE)
    if not index_videos:
        settings = settings.with_overrides(extensions=settings.extensions - VIDEO_EXTENSIONS)
    return settings.with_overrides(**clean)
