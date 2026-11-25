"""Thumbnail creation and shared JPEG/resize helpers."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from utils.file_utils import atomic_write_bytes, output_name

SHARD_SIZE = 1000


def shard_dir(base: Path, image_id: int) -> Path:
    """Sub-folder for an image id, e.g. ``base/0042`` for ids 42000-42999."""
    return base / f"{image_id // SHARD_SIZE:04d}"


def resize_to_fit(pil: Image.Image, size: int) -> Image.Image:
    """Return a copy whose long side is at most ``size``. Never upscales."""
    scale = min(size / pil.width, size / pil.height, 1.0)
    if scale >= 1.0:
        return pil.copy()
    new_size = (max(1, round(pil.width * scale)), max(1, round(pil.height * scale)))
    return pil.resize(new_size, Image.Resampling.LANCZOS)


def encode_jpeg(pil: Image.Image, quality: int = 90) -> bytes:
    """Encode as JPEG bytes (flattens to RGB)."""
    buffer = io.BytesIO()
    pil.convert("RGB").save(buffer, "JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def save_thumbnail(
    pil: Image.Image,
    image_id: int,
    source: Path,
    thumbnails_dir: Path,
    size: int = 256,
    quality: int = 90,
) -> Path:
    """Write a thumbnail atomically and return its path.

    Raises:
        OSError: if the file cannot be written.
    """
    dest = shard_dir(thumbnails_dir, image_id) / output_name(image_id, source)
    atomic_write_bytes(dest, encode_jpeg(resize_to_fit(pil, size), quality))
    return dest
