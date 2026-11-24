"""Non-biometric image similarity: perceptual hash and colour features.

These describe whole-image appearance only. Nothing here looks at faces.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

PHASH_BITS = 64
FEATURE_DIM = 8 * 4 * 4          # HSV bins: H8 x S4 x V4


def compute_phash(pil: Image.Image) -> str:
    """64-bit DCT perceptual hash as 16 lowercase hex characters.

    Greyscale -> 32x32 -> DCT -> keep the 8x8 low-frequency block -> bit = 1
    where the coefficient exceeds the median of the AC terms. Robust to
    resizing, re-compression and mild colour changes.
    """
    grey = np.asarray(pil.convert("L").resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float32)
    block = cv2.dct(grey)[:8, :8]
    median = float(np.median(block.flatten()[1:]))     # ignore the DC term
    bits = (block > median + 1e-3).flatten()           # epsilon keeps flat images stable
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def parse_phash(text: str | None) -> int | None:
    """Hex string -> int, or ``None`` if missing or malformed."""
    if not text or len(text) != 16:
        return None
    try:
        return int(text, 16)
    except ValueError:
        return None


def hamming(a: str, b: str) -> int:
    """Hamming distance between two hex pHashes (0 = identical)."""
    x, y = parse_phash(a), parse_phash(b)
    if x is None or y is None:
        raise ValueError("invalid pHash")
    return (x ^ y).bit_count()


def compute_features(pil: Image.Image) -> bytes:
    """Colour feature for clustering undated images, as float16 bytes.

    sqrt of the L1-normalised HSV histogram (unit L2 norm), so Euclidean
    distance between two vectors lies in [0, sqrt(2)].
    """
    small = np.asarray(pil.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR))
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
    hist /= max(float(hist.sum()), 1.0)
    return np.sqrt(hist).astype(np.float16).tobytes()


def features_from_bytes(blob: bytes | None) -> np.ndarray | None:
    """Inverse of :func:`compute_features` (float32), or ``None`` if invalid."""
    if not blob or len(blob) != FEATURE_DIM * 2:
        return None
    return np.frombuffer(blob, dtype=np.float16).astype(np.float32)