"""Lazy, recursive discovery of image files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator

from config import SUPPORTED_EXTENSIONS
from utils.logger import get_logger

log = get_logger("core.scanner")


def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def iter_image_files(
    root: Path,
    extensions: Iterable[str] = SUPPORTED_EXTENSIONS,
    exclude: Iterable[Path] = (),
) -> Iterator[tuple[Path, int, int]]:
    """Yield ``(path, size, mtime_ns)`` for every supported image under ``root``.

    * Extensions are matched case-insensitively.
    * Folders in ``exclude`` (e.g. the workspace) are skipped entirely, so
      generated thumbnails are never mistaken for photos.
    * Symlinked/junction folders are not followed (no cycles).
    * Unreadable folders and files are logged and skipped, never fatal.
    * Order is deterministic (case-insensitive name order, depth first).

    This is a generator: memory use stays flat on very large collections.
    """
    exts = frozenset(e.lower() for e in extensions)
    excluded = {_norm(Path(p).resolve()) for p in exclude}
    stack: list[str] = [str(root)]

    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = sorted(it, key=lambda e: e.name.lower())
        except OSError as exc:
            log.warning("Cannot read folder %s: %s", current, exc)
            continue

        subdirs: list[str] = []
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if _norm(entry.path) not in excluded:
                        subdirs.append(entry.path)
                elif entry.is_file():
                    if os.path.splitext(entry.name)[1].lower() in exts:
                        st = entry.stat()
                        yield Path(entry.path), st.st_size, st.st_mtime_ns
            except OSError as exc:
                log.debug("Skipping %s: %s", entry.path, exc)

        stack.extend(reversed(subdirs))  # keeps alphabetical depth-first order
