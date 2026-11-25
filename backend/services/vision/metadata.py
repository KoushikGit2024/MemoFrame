"""EXIF timestamp and GPS extraction.

Works on the ``Image.Exif`` object already captured by the loader, so the file
is not opened a second time.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from PIL import Image

from models import (
    TS_EXIF_DATETIME,
    TS_EXIF_ORIGINAL,
    TS_FILE_MTIME,
    TS_NONE,
    ImageMeta,
)

_TAG_DATETIME = 0x0132
_TAG_EXIF_IFD = 0x8769
_TAG_DATETIME_ORIGINAL = 0x9003
_TAG_GPS_IFD = 0x8825

_FORMATS = ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S")
_ISO = "%Y-%m-%dT%H:%M:%S"


def parse_exif_datetime(value: Any) -> datetime | None:
    """Parse an EXIF date string. Returns ``None`` for blank or nonsense values
    (cameras often write ``0000:00:00 00:00:00``)."""
    if isinstance(value, bytes):
        value = value.decode("ascii", errors="ignore")
    if not isinstance(value, str):
        return None
    text = value.replace("\x00", "").strip()
    for fmt in _FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if 1900 <= parsed.year <= datetime.now().year + 1:
            return parsed
    return None


def _ifd(exif: Image.Exif, tag: int) -> dict[int, Any]:
    try:
        return dict(exif.get_ifd(tag))
    except Exception:  # noqa: BLE001 - damaged EXIF must never abort processing
        return {}


def _to_degrees(dms: Any, ref: Any) -> float | None:
    try:
        deg, minutes, seconds = (float(v) for v in dms)
        value = deg + minutes / 60.0 + seconds / 3600.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if isinstance(ref, bytes):
        ref = ref.decode("ascii", errors="ignore")
    if str(ref).strip().upper() in ("S", "W"):
        value = -value
    return value if math.isfinite(value) else None


def extract_gps(exif: Image.Exif) -> tuple[float | None, float | None]:
    """Return ``(lat, lon)`` in decimal degrees, or ``(None, None)``."""
    gps = _ifd(exif, _TAG_GPS_IFD)
    if not gps:
        return None, None
    lat = _to_degrees(gps.get(2), gps.get(1)) if 2 in gps else None
    lon = _to_degrees(gps.get(4), gps.get(3)) if 4 in gps else None
    if lat is None or lon is None:
        return None, None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None, None
    if lat == 0.0 and lon == 0.0:  # "null island": a common no-fix placeholder
        return None, None
    return lat, lon


def extract_metadata(
    exif: Image.Exif,
    width: int,
    height: int,
    mtime_ns: int | None = None,
) -> ImageMeta:
    """Build :class:`ImageMeta` from EXIF data.

    Timestamp priority: EXIF ``DateTimeOriginal``, then EXIF ``DateTime``, then
    the file's modification time (if ``mtime_ns`` is given), else none. The
    source is recorded so later stages can weigh how trustworthy it is.
    """
    ts: datetime | None = None
    source = TS_NONE

    original = _ifd(exif, _TAG_EXIF_IFD).get(_TAG_DATETIME_ORIGINAL)
    ts = parse_exif_datetime(original)
    if ts is not None:
        source = TS_EXIF_ORIGINAL
    else:
        ts = parse_exif_datetime(exif.get(_TAG_DATETIME))
        if ts is not None:
            source = TS_EXIF_DATETIME
        elif mtime_ns:
            try:
                ts = datetime.fromtimestamp(mtime_ns / 1e9)
                source = TS_FILE_MTIME
            except (OverflowError, OSError, ValueError):
                ts = None

    lat, lon = extract_gps(exif)
    return ImageMeta(
        width=width,
        height=height,
        exif_ts=ts.strftime(_ISO) if ts else None,
        ts_source=source,
        gps_lat=lat,
        gps_lon=lon,
    )
