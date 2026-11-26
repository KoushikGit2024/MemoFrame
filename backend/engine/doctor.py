"""Environment checks. Never modifies anything outside the workspace."""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from config import SFACE_SHA256, YUNET_SHA256, Settings
from utils.file_utils import sha256_file
from utils.system_info import available_memory_mb


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str
    fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_checks(settings: Settings, source_dirs: Iterable[Path | str] = ()) -> list[Check]:
    """Run all checks and return the results."""
    out: list[Check] = []

    v = sys.version_info
    out.append(
        Check(
            "python",
            "ok" if v >= (3, 11) else "fail",
            f"{v.major}.{v.minor}.{v.micro}",
            "" if v >= (3, 11) else "Install Python 3.11 or newer.",
        )
    )

    try:
        import cv2

        has_yunet = hasattr(cv2, "FaceDetectorYN")
        out.append(
            Check(
                "opencv",
                "ok" if has_yunet else "fail",
                cv2.__version__,
                "" if has_yunet else 'pip install -U "opencv-python>=4.8,<5"',
            )
        )
    except ImportError:
        out.append(Check("opencv", "fail", "not installed", "pip install opencv-python"))

    try:
        import pillow_heif

        out.append(Check("heic", "ok", f"pillow-heif {pillow_heif.__version__}"))
    except ImportError:
        out.append(
            Check(
                "heic",
                "warn",
                "pillow-heif not installed",
                "pip install pillow-heif for HEIC photos.",
            )
        )

    try:
        import importlib

        rawpy = importlib.import_module("rawpy")
        out.append(Check("raw", "ok", f"rawpy {getattr(rawpy, '__version__', 'installed')}"))
    except ImportError:
        out.append(Check("raw", "ok", "rawpy not installed (optional, for DSLR RAW photos)"))

    import sqlite3

    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        out.append(Check("fts5", "ok", f"SQLite {sqlite3.sqlite_version}"))
    except sqlite3.Error:
        out.append(
            Check(
                "fts5",
                "warn",
                "full-text index unavailable; text search is slower",
                "Use the python.org build of Python.",
            )
        )
    finally:
        probe.close()

    if settings.detector_backend.lower() == "yunet":
        model = settings.yunet_path
        if not model.is_file():
            out.append(
                Check(
                    "model",
                    "warn",
                    "face model not downloaded yet",
                    f"It downloads on first processing (internet once), or save the file as {model}",
                )
            )
        else:
            digest = sha256_file(model)
            if not YUNET_SHA256:
                out.append(
                    Check(
                        "model",
                        "warn",
                        f"present, hash not pinned (sha256 {digest})",
                        "Paste that value into YUNET_SHA256 in config.py.",
                    )
                )
            elif digest.lower() == YUNET_SHA256.lower():
                out.append(Check("model", "ok", "present, hash verified"))
            else:
                out.append(
                    Check(
                        "model",
                        "fail",
                        "hash does not match",
                        f"Delete {model} and let it download again.",
                    )
                )

    sface = settings.sface_path
    if not sface.is_file():
        out.append(
            Check(
                "sface model",
                "warn",
                "SFace recognition model not downloaded yet",
                f"Downloads on first processing, or save the file as {sface}",
            )
        )
    else:
        digest = sha256_file(sface)
        if SFACE_SHA256 and digest.lower() != SFACE_SHA256.lower():
            out.append(
                Check(
                    "sface model",
                    "fail",
                    f"hash mismatch (sha256 {digest})",
                    "Run tools/verify_models.py; fix SFACE_SHA256 in config.py or re-download.",
                )
            )
        else:
            out.append(Check("sface model", "ok", "present, hash verified"))

    try:
        settings.workspace.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=settings.workspace):
            pass
        out.append(Check("workspace", "ok", f"writable: {settings.workspace}"))
        free_gb = shutil.disk_usage(settings.workspace).free / 1e9
        status = "ok" if free_gb >= 5 else "warn" if free_gb >= 1 else "fail"
        out.append(
            Check(
                "disk space",
                status,
                f"{free_gb:.1f} GB free",
                "" if status == "ok" else "Free up space on the workspace drive.",
            )
        )
    except OSError as exc:
        out.append(Check("workspace", "fail", str(exc), "Choose a writable workspace folder."))

    free = available_memory_mb()
    if free is None:
        out.append(Check("memory", "warn", "could not read free memory"))
    else:
        out.append(
            Check(
                "memory",
                "ok" if free >= 2048 else "warn",
                f"{free} MB free",
                "" if free >= 2048 else "Close other programs or use the gentle profile.",
            )
        )

    if settings.tagging_enabled:
        files = [
            settings.tag_dir / settings.tag_model_file,
            settings.tag_dir / settings.tag_labels_file,
        ]
        gone = [p.name for p in files if not p.is_file()]
        out.append(
            Check(
                "scene tags",
                "fail" if gone else "ok",
                f"missing: {', '.join(gone)}" if gone else "model and labels present",
                (
                    f"Put {', '.join(gone)} in {settings.tag_dir}. "
                    "Get a compatible ONNX classifier (e.g. MobileNetV2 from the ONNX Model Zoo) "
                    "and a matching labels file (one class per line). "
                    "Or disable scene tagging in Settings \u2192 Scene Tags."
                )
                if gone
                else "",
            )
        )

    for src in source_dirs:
        reachable = Path(src).is_dir()
        out.append(
            Check(
                f"source {src}",
                "ok" if reachable else "fail",
                "reachable" if reachable else "not reachable",
                "" if reachable else "Reconnect the drive or fix the path.",
            )
        )
    return out
