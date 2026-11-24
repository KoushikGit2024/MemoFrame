"""Safe image decoding (Pillow) with EXIF orientation and optional downscaling.

Originals are only ever opened for reading. Pillow handles non-ASCII Windows
paths, unlike ``cv2.imread``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

_ORIENTATION_TAG = 0x0112
_SWAPS_AXES = frozenset({5, 6, 7, 8})   # EXIF orientations that rotate by 90 degrees


class ImageLoadError(Exception):
    """The file is corrupted, truncated, unsupported, or too large to decode."""


@dataclass
class LoadedImage:
    """A decoded image plus the information needed to map back to full size.

    Attributes:
        pil: RGB image, orientation-corrected, long side <= ``max_side``.
        width, height: dimensions of the full-resolution, orientation-corrected
            image (what a photo viewer would show).
        scale: ``width / pil.width``. Multiply coordinates measured on ``pil``
            by this to get full-resolution coordinates.
        exif: EXIF data read from the original file (empty if none).
    """

    pil: Image.Image
    width: int
    height: int
    scale: float
    exif: Image.Exif

    def to_bgr(self) -> np.ndarray:
        """Contiguous ``uint8`` BGR array (OpenCV convention) of ``pil``."""
        return cv2.cvtColor(np.asarray(self.pil), cv2.COLOR_RGB2BGR)


def load_image(path: Path, max_side: int | None = None) -> LoadedImage:
    """Decode ``path`` to RGB, apply EXIF rotation in memory, optionally downscale.

    Args:
        path: image file.
        max_side: if set, the long side of the returned image is at most this.
            JPEGs are shrunk during decoding, which is much faster and lighter
            on memory for large photos.

    Raises:
        ImageLoadError: for any decode failure (message names the file).
    """
    try:
        with Image.open(path) as im:
            orig_w, orig_h = im.size
            exif = im.getexif()
            orientation = exif.get(_ORIENTATION_TAG, 1)
            full_w, full_h = (orig_h, orig_w) if orientation in _SWAPS_AXES else (orig_w, orig_h)
            if full_w < 1 or full_h < 1:
                raise ImageLoadError(f"{path.name}: image has zero size")

            if max_side and max(orig_w, orig_h) > max_side:
                ratio = max_side / max(orig_w, orig_h)
                # draft() is a no-op for formats other than JPEG.
                im.draft("RGB", (math.ceil(orig_w * ratio), math.ceil(orig_h * ratio)))

            im.load()  # decode now so truncated files fail here
            work = ImageOps.exif_transpose(im).convert("RGB")

        if max_side and max(work.size) > max_side:
            work.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

        return LoadedImage(
            pil=work,
            width=full_w,
            height=full_h,
            scale=full_w / work.width,
            exif=exif,
        )
    except ImageLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow plugins raise many exception types
        raise ImageLoadError(f"{path.name}: {type(exc).__name__}: {exc}") from exc