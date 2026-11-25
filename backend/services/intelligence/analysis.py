"""Whole-image analysis: quality, dHash, content type, date plausibility.

Faces are never examined here.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import cv2
import numpy as np
from PIL import Image

from services.vision.loader import LoadedImage

_MAKE, _MODEL = 0x010F, 0x0110
_ISO = "%Y-%m-%dT%H:%M:%S"


def compute_dhash(pil: Image.Image) -> str:
    """64-bit difference hash as 16 hex chars (compare with ``image_similarity.hamming``)."""
    grey = np.asarray(pil.convert("L").resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16)
    value = 0
    for bit in (grey[:, 1:] > grey[:, :-1]).flatten():
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def quality_metrics(pil: Image.Image, full_pixels: int) -> dict[str, float]:
    """``quality`` (0-100), ``sharpness`` (Laplacian variance at <=512 px), ``brightness`` (0-255)."""
    grey = np.asarray(pil.convert("L"))
    h, w = grey.shape
    scale = 512 / max(h, w)
    if scale < 1:
        grey = cv2.resize(grey, (max(1, round(w * scale)), max(1, round(h * scale))),
                          interpolation=cv2.INTER_AREA)
    sharp = float(cv2.Laplacian(grey, cv2.CV_64F).var())
    mean = float(grey.mean())
    clipped = float(((grey <= 5) | (grey >= 250)).mean())
    sharp_score = min(1.0, math.log1p(sharp) / math.log1p(400))
    exposure = 1.0 - min(1.0, clipped * 2.5)
    if mean < 50:
        exposure *= mean / 50
    elif mean > 210:
        exposure *= max(0.0, (255 - mean) / 45)
    resolution = min(1.0, full_pixels / 12e6)
    quality = 100 * (0.6 * sharp_score + 0.25 * exposure + 0.15 * resolution)
    return {"quality": round(quality, 2), "sharpness": round(sharp, 2), "brightness": round(mean, 1)}


def classify_content(loaded: LoadedImage, name: str) -> str:
    """``photo`` | ``screenshot`` | ``document`` (heuristic; see notes in the docs)."""
    lower = name.lower()
    if "screenshot" in lower or "screen shot" in lower:
        return "screenshot"
    if loaded.exif.get(_MAKE) or loaded.exif.get(_MODEL):
        return "photo"                                   # a camera wrote this file
    small = loaded.pil.convert("RGB").copy()
    small.thumbnail((128, 128))
    arr = np.asarray(small)
    codes = (arr[..., 0] // 32).astype(np.int32) * 64 + (arr[..., 1] // 32) * 8 + (arr[..., 2] // 32)
    counts = np.bincount(codes.ravel(), minlength=512)
    dominant = float(np.sort(counts)[-3:].sum() / codes.size)
    used = int((counts >= 0.002 * codes.size).sum())
    if dominant < 0.6 or used > 48:
        return "photo"
    sat = float(cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)[..., 1].mean()) / 255
    return "document" if float(arr.mean()) >= 170 and sat < 0.12 else "screenshot"


def date_flag(exif_ts: str | None, ts_source: str | None, now: datetime | None = None) -> str | None:
    """``none`` | ``future`` | ``implausible`` | ``mtime_only`` | ``None`` (date looks fine)."""
    if not exif_ts:
        return "none"
    try:
        when = datetime.strptime(exif_ts, _ISO)
    except ValueError:
        return "implausible"
    now = now or datetime.now()
    if when > now + timedelta(days=1):
        return "future"
    if when.year < 1995 or (when.month, when.day) == (1, 1) and when.year in (1970, 2000, 1980):
        return "implausible"
    return "mtime_only" if ts_source == "file_mtime" else None


def analyze_image(loaded: LoadedImage, name: str, exif_ts: str | None, ts_source: str | None) -> dict[str, Any]:
    """All Phase D per-image values, ready to merge into a ``save_results`` mapping."""
    out: dict[str, Any] = quality_metrics(loaded.pil, loaded.width * loaded.height)
    out["dhash"] = compute_dhash(loaded.pil)
    out["content_type"] = classify_content(loaded, name)
    out["date_flag"] = date_flag(exif_ts, ts_source)
    return out
