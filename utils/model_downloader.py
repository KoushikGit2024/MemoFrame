"""One-time download of the YuNet face-detection weights.

Only the model file is downloaded. No image data ever leaves the machine.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

from config import YUNET_SHA256, YUNET_URL
from utils.file_utils import atomic_write_bytes, ensure_dir, human_size, sha256_file
from utils.logger import get_logger

log = get_logger("utils.model_downloader")

_MIN_PLAUSIBLE_BYTES = 10_000  # real file is ~230 KB; guards against HTML error pages
_TIMEOUT_S = 30


class ModelDownloadError(RuntimeError):
    """Raised when the model cannot be obtained or fails verification."""


def _verify(path: Path, expected_sha256: str) -> bool:
    """Size sanity check, plus hash check when a hash is configured."""
    if not path.is_file() or path.stat().st_size < _MIN_PLAUSIBLE_BYTES:
        return False
    actual = sha256_file(path)
    if expected_sha256:
        return actual.lower() == expected_sha256.lower()
    log.warning(
        "No SHA-256 pinned for %s. Computed %s. Set YUNET_SHA256 in config.py to pin it.",
        path.name,
        actual,
    )
    return True


def ensure_model(
    dest: Path,
    url: str = YUNET_URL,
    expected_sha256: str = YUNET_SHA256,
) -> Path:
    """Return ``dest``, downloading it first if it is missing or invalid.

    Offline use: download the file manually and place it at ``dest``.

    Raises:
        ModelDownloadError: on network failure or verification failure.
    """
    if _verify(dest, expected_sha256):
        log.debug("Model already present: %s", dest)
        return dest

    if dest.exists():
        log.warning("Existing model file failed verification, re-downloading: %s", dest)

    ensure_dir(dest.parent)
    log.info("Downloading face-detection model (one time) from %s", url)
    request = urllib.request.Request(url, headers={"User-Agent": "photo-organizer/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:  # noqa: S310
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ModelDownloadError(
            f"Could not download the model: {exc}\n"
            f"Download it manually from:\n  {url}\nand save it as:\n  {dest}"
        ) from exc

    atomic_write_bytes(dest, data)
    if not _verify(dest, expected_sha256):
        try:
            os.unlink(dest)
        except OSError:
            pass
        raise ModelDownloadError(
            "Downloaded model failed verification (wrong size or SHA-256). "
            "The file was removed. Check YUNET_URL / YUNET_SHA256 in config.py."
        )

    log.info("Model saved to %s (%s)", dest, human_size(dest.stat().st_size))
    return dest