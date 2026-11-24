"""Basic video metadata without ffmpeg.

Date and duration come from the MP4/MOV header (``moov/mvhd``), read with a few
seeks, so large videos are never read whole. A poster frame is grabbed through
OpenCV when the build can decode the codec (HEVC often cannot).
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

# Silence noisy FFmpeg/OpenCV internal decoder warnings on odd/truncated video streams
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")
os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")

import cv2
try:
    import cv2.utils.logging as _cv2_logging
    _cv2_logging.setLogLevel(_cv2_logging.LOG_LEVEL_SILENT)
except (ImportError, AttributeError):
    pass
from PIL import Image

_EPOCH_1904 = datetime(1904, 1, 1, tzinfo=timezone.utc)


@dataclass
class VideoInfo:
    created: datetime | None = None          # naive local time
    duration_s: float | None = None
    width: int = 0
    height: int = 0
    poster: Image.Image | None = None


def _boxes(fh: BinaryIO, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """Yield ``(type, payload_start, box_end)`` for the boxes in ``[start, end)``."""
    pos = start
    while pos + 8 <= end:
        fh.seek(pos)
        head = fh.read(8)
        if len(head) < 8:
            return
        size, kind = struct.unpack(">I4s", head)
        header = 8
        if size == 1:                                   # 64-bit size follows
            ext = fh.read(8)
            if len(ext) < 8:
                return
            size, header = struct.unpack(">Q", ext)[0], 16
        elif size == 0:                                 # box runs to the end
            size = end - pos
        if size < header:
            return
        yield kind, pos + header, min(pos + size, end)
        pos += size


def _to_local(seconds: int) -> datetime | None:
    """MP4 times are UTC seconds since 1904; convert to this machine's local time."""
    if seconds <= 0:
        return None
    try:
        local = (_EPOCH_1904 + timedelta(seconds=seconds)).astimezone().replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None
    return local if 1990 <= local.year <= datetime.now().year + 1 else None


def read_mvhd(path: Path) -> tuple[datetime | None, float | None]:
    """Return ``(created, duration_seconds)`` from the movie header, or ``(None, None)``."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            end = fh.tell()
            for kind, start, stop in _boxes(fh, 0, end):
                if kind != b"moov":
                    continue
                for kind2, start2, stop2 in _boxes(fh, start, stop):
                    if kind2 != b"mvhd":
                        continue
                    fh.seek(start2)
                    data = fh.read(min(stop2 - start2, 32))
                    if data[0] == 1 and len(data) >= 32:
                        created, _, scale, dur = struct.unpack(">QQIQ", data[4:32])
                    elif data[0] == 0 and len(data) >= 20:
                        created, _, scale, dur = struct.unpack(">IIII", data[4:20])
                    else:
                        return None, None
                    return _to_local(created), (dur / scale if scale else None)
    except (OSError, struct.error, IndexError, OverflowError, ValueError):
        pass
    return None, None


def probe_video(path: Path, max_side: int = 1280) -> VideoInfo:
    """Header metadata plus a poster frame (``poster`` is ``None`` if it can't be decoded)."""
    created, duration = read_mvhd(path)
    info = VideoInfo(created=created, duration_s=duration)
    cap = None
    try:
        cap = cv2.VideoCapture(str(path))     # may fail for non-ASCII Windows paths
        if cap.isOpened():
            info.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            info.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            if info.duration_s is None and fps > 0 and frames > 0:
                info.duration_s = frames / fps
            if frames > 10 and fps > 0:           # skip a possible black first frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(min(frames * 0.1, fps)))
            ok, frame = cap.read()
            if ok and frame is not None:
                poster = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                poster.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                info.poster = poster
    except Exception:  # noqa: BLE001 - OpenCV can raise varied errors on odd files
        pass
    finally:
        if cap is not None:
            cap.release()
    return info
