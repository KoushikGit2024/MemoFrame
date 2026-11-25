"""Safe image decoding (Pillow) with EXIF orientation and optional downscaling.

Originals are only ever opened for reading. Supports JPEG, PNG, WEBP, BMP, TIFF,
plus HEIC/HEIF (pillow-heif) and RAW (rawpy) when those libraries are installed.
Errors start with a stable code: FILE_MISSING, FILE_UNREADABLE, CORRUPT_IMAGE,
UNSUPPORTED_FORMAT.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import cv2
import numpy as np
from PIL import Image, ImageOps

from config import RAW_EXTENSIONS

_ORIENTATION_TAG = 0x0112
_SWAPS_AXES = frozenset({5, 6, 7, 8})   # EXIF orientations that rotate by 90 degrees


def _register_heif() -> bool:
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        return True
    except Exception:  # noqa: BLE001 - optional dependency
        return False


HEIC_AVAILABLE = _register_heif()       # runs in every worker process on import


class ImageLoadError(Exception):
    """The file is corrupted, truncated, unsupported, missing, or too large to decode."""


@dataclass
class LoadedImage:
    """A decoded image plus the information needed to map back to full size.

    Attributes:
        pil: RGB image, orientation-corrected, long side <= ``max_side``.
        width, height: dimensions of the full-resolution, orientation-corrected image
            (for RAW files: of the embedded preview).
        scale: ``width / pil.width``; multiply coordinates on ``pil`` by this.
        exif: EXIF data read from the original file (empty if none).
        format: decoder name ("JPEG", "HEIF", "RAW", ...).
    """

    pil: Image.Image
    width: int
    height: int
    scale: float
    exif: Image.Exif
    format: str = ""

    def to_bgr(self) -> np.ndarray:
        """Contiguous ``uint8`` BGR array (OpenCV convention) of ``pil``."""
        return cv2.cvtColor(np.asarray(self.pil), cv2.COLOR_RGB2BGR)


def _decode(source: Path | BinaryIO, name: str, max_side: int | None) -> LoadedImage:
    try:
        with Image.open(source) as im:
            fmt = im.format or ""
            orig_w, orig_h = im.size
            exif = im.getexif()
            orientation = exif.get(_ORIENTATION_TAG, 1)
            full_w, full_h = (orig_h, orig_w) if orientation in _SWAPS_AXES else (orig_w, orig_h)
            if full_w < 1 or full_h < 1:
                raise ImageLoadError(f"CORRUPT_IMAGE: {name}: image has zero size")

            if max_side and max(orig_w, orig_h) > max_side:
                ratio = max_side / max(orig_w, orig_h)
                # draft() is a no-op for formats other than JPEG.
                im.draft("RGB", (math.ceil(orig_w * ratio), math.ceil(orig_h * ratio)))

            im.load()  # decode now so truncated files fail here
            work = ImageOps.exif_transpose(im).convert("RGB")

        if max_side and max(work.size) > max_side:
            work.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

        return LoadedImage(pil=work, width=full_w, height=full_h,
                           scale=full_w / work.width, exif=exif, format=fmt)
    except ImageLoadError:
        raise
    except FileNotFoundError as exc:
        raise ImageLoadError(f"FILE_MISSING: {name}") from exc
    except Exception as exc:  # noqa: BLE001 - Pillow plugins raise many exception types
        raise ImageLoadError(f"CORRUPT_IMAGE: {name}: {type(exc).__name__}: {exc}") from exc


def _from_pil(pil: Image.Image, max_side: int | None, fmt: str) -> LoadedImage:
    pil = pil.convert("RGB")
    width, height = pil.size
    if max_side and max(width, height) > max_side:
        pil.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return LoadedImage(pil=pil, width=width, height=height, scale=width / pil.width,
                       exif=Image.Exif(), format=fmt)


def _decode_raw(data: bytes, name: str, max_side: int | None) -> LoadedImage:
    """RAW: use the camera's embedded preview (fast); fall back to a half-size develop."""
    try:
        import importlib
        rawpy = importlib.import_module("rawpy")
    except ImportError as exc:
        raise ImageLoadError(f"UNSUPPORTED_FORMAT: {name}: install rawpy for RAW files") from exc
    try:
        with rawpy.imread(io.BytesIO(data)) as raw:
            try:
                thumb = raw.extract_thumb()
            except Exception:  # noqa: BLE001 - no usable preview in this file
                thumb = None
            if thumb is not None and thumb.format == rawpy.ThumbFormat.JPEG:
                loaded = _decode(io.BytesIO(thumb.data), name, max_side)
                loaded.format = "RAW"
                return loaded
            if thumb is not None and thumb.format == rawpy.ThumbFormat.BITMAP:
                pil = Image.fromarray(thumb.data)
            else:
                pil = Image.fromarray(
                    raw.postprocess(half_size=True, use_camera_wb=True, output_bps=8))
        return _from_pil(pil, max_side, "RAW")
    except ImageLoadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImageLoadError(f"CORRUPT_IMAGE: {name}: {type(exc).__name__}: {exc}") from exc


def load_image(path: Path, max_side: int | None = None) -> LoadedImage:
    """Decode ``path`` to RGB, apply EXIF rotation in memory, optionally downscale.

    Raises:
        ImageLoadError: for any decode failure (message starts with a code).
    """
    if path.suffix.lower() in RAW_EXTENSIONS:
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise ImageLoadError(f"FILE_MISSING: {path.name}") from exc
        except OSError as exc:
            raise ImageLoadError(f"FILE_UNREADABLE: {path.name}: {exc}") from exc
        return _decode_raw(data, path.name, max_side)
    return _decode(path, path.name, max_side)


def load_image_bytes(data: bytes, name: str, max_side: int | None = None) -> LoadedImage:
    """Same as :func:`load_image` for bytes already read from disk (single-read pipeline)."""
    if Path(name).suffix.lower() in RAW_EXTENSIONS:
        return _decode_raw(data, name, max_side)
    return _decode(io.BytesIO(data), name, max_side)
