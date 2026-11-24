"""Filesystem helpers: hashing, fingerprints, safe and atomic output."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import NamedTuple


class Fingerprint(NamedTuple):
    """Cheap change detector: if both fields match, the file is unchanged."""

    size: int
    mtime_ns: int


def file_fingerprint(path: Path) -> Fingerprint:
    """Return ``(size, mtime_ns)``. Raises ``OSError`` if the file is unreadable."""
    st = path.stat()
    return Fingerprint(st.st_size, st.st_mtime_ns)


def sha256_file(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    """Stream the file in chunks and return its hex SHA-256 digest."""
    digest = hashlib.sha256()
    buffer = bytearray(chunk_bytes)
    view = memoryview(buffer)
    with path.open("rb") as fh:
        while True:
            n = fh.readinto(buffer)
            if not n:
                break
            digest.update(view[:n])
    return digest.hexdigest()


def is_within(child: Path, parent: Path) -> bool:
    """True if ``child`` is ``parent`` or lives under it (after resolving)."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_stem(name: str, max_len: int = 40) -> str:
    """Filesystem-safe version of a file stem (ASCII, Windows-reserved chars removed)."""
    cleaned = _UNSAFE.sub("_", Path(name).stem).strip("._") or "image"
    return cleaned[:max_len]


def output_name(image_id: int, source: Path, suffix: str = ".jpg", tag: str = "") -> str:
    """Collision-free output filename, e.g. ``00000042_beach_f001.jpg``.

    The numeric id guarantees uniqueness even when many source files share a name.
    """
    tag_part = f"_{tag}" if tag else ""
    return f"{image_id:08d}_{safe_stem(source.name)}{tag_part}{suffix}"


def ensure_dir(path: Path) -> Path:
    """Create a directory (and parents) if missing, and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes to ``path`` via a temp file + ``os.replace``.

    A crash mid-write can never leave a truncated output file, which keeps
    resumed runs safe. Also works with non-ASCII Windows paths, unlike
    ``cv2.imwrite``. Encode with ``cv2.imencode`` and pass the bytes here.
    """
    ensure_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def human_size(num_bytes: float) -> str:
    """Format a byte count, e.g. ``1.5 MB``."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def lower_process_priority() -> None:
    """Run this process below normal priority so the machine stays responsive."""
    try:
        if os.name == "nt":
            import ctypes
            BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(10)
    except Exception:  # noqa: BLE001 - best effort only
        pass