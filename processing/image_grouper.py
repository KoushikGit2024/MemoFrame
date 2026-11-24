"""Non-biometric event grouping (time, GPS, colour similarity).

Faces are never used. Pure functions: rows in, group descriptions out, ready
for ``DatabaseManager.replace_groups``.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, NamedTuple, Sequence

from core.image_similarity import features_from_bytes
from core.models import TS_EXIF_DATETIME, TS_EXIF_ORIGINAL
from utils.logger import get_logger

log = get_logger("processing.image_grouper")

_ISO = "%Y-%m-%dT%H:%M:%S"
_TRUSTED_SOURCES = frozenset({TS_EXIF_ORIGINAL, TS_EXIF_DATETIME})
VISUAL_WINDOW = 2000          # max images per agglomerative clustering run
_EARTH_RADIUS_KM = 6371.0088


class _Item(NamedTuple):
    when: datetime
    image_id: int
    lat: float | None
    lon: float | None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), _ISO)
    except ValueError:
        return None


def split_events(items: Sequence[_Item], gap_hours: float, gps_split_km: float) -> list[list[_Item]]:
    """Split time-sorted items into events by time gap and (optional) GPS jump."""
    gap = timedelta(hours=gap_hours)
    events: list[list[_Item]] = []
    current: list[_Item] = []
    last_gps: tuple[float, float] | None = None
    for item in items:
        if current:
            too_late = (item.when - current[-1].when) > gap
            moved = (
                gps_split_km > 0
                and item.lat is not None and item.lon is not None
                and last_gps is not None
                and haversine_km(last_gps[0], last_gps[1], item.lat, item.lon) > gps_split_km
            )
            if too_late or moved:
                events.append(current)
                current, last_gps = [], None
        current.append(item)
        if item.lat is not None and item.lon is not None:
            last_gps = (item.lat, item.lon)
    if current:
        events.append(current)
    return events


def _event_groups(items: list[_Item], label: str, gap_hours: float, gps_km: float) -> list[dict[str, Any]]:
    items = sorted(items, key=lambda i: (i.when, i.image_id))
    groups = []
    for chunk in split_events(items, gap_hours, gps_km):
        start, end = chunk[0].when, chunk[-1].when
        groups.append({
            "kind": "event",
            "name": f"{label} {start:%Y-%m-%d %H:%M}",
            "start_ts": start.strftime(_ISO),
            "end_ts": end.strftime(_ISO),
            "image_ids": [i.image_id for i in chunk],
        })
    return groups


def _visual_groups(rows: Sequence[Mapping[str, Any]], distance: float) -> list[dict[str, Any]]:
    """Cluster undated images by colour histogram (average-linkage agglomerative)."""
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering   # lazy: heavy import

    usable: list[tuple[int, Any]] = []
    for row in sorted(rows, key=lambda r: int(r["id"])):
        vec = features_from_bytes(row["features"])
        if vec is not None:
            usable.append((int(row["id"]), vec))
    skipped = len(rows) - len(usable)
    if skipped:
        log.info("%d undated image(s) have no colour features and stay ungrouped", skipped)

    groups: list[dict[str, Any]] = []
    for start in range(0, len(usable), VISUAL_WINDOW):
        window = usable[start:start + VISUAL_WINDOW]
        ids = [i for i, _ in window]
        if len(window) == 1:
            labels = [0]
        else:
            matrix = np.stack([v for _, v in window])
            labels = AgglomerativeClustering(
                n_clusters=None, distance_threshold=distance,
                metric="euclidean", linkage="average",
            ).fit_predict(matrix).tolist()
        buckets: dict[int, list[int]] = {}
        for image_id, lab in zip(ids, labels):
            buckets.setdefault(lab, []).append(image_id)
        for members in buckets.values():
            groups.append({
                "kind": "visual", "name": None,
                "start_ts": None, "end_ts": None, "image_ids": members,
            })
    for n, g in enumerate(groups, start=1):
        g["name"] = f"Visual group {n}"
    return groups


def group_images(
    rows: Iterable[Mapping[str, Any]],
    *,
    event_gap_hours: float = 3.0,
    gps_split_km: float = 5.0,
    visual_distance: float = 0.35,
    min_group_size: int = 1,
) -> list[dict[str, Any]]:
    """Group images into events and visual clusters.

    Args:
        rows: mappings with ``id, exif_ts, ts_source, gps_lat, gps_lon, features``
            (``DatabaseManager.fetch_grouping_rows`` output works directly).
        event_gap_hours: a longer gap between consecutive photos starts a new event.
        gps_split_km: a larger jump from the last geotagged photo starts a new
            event (0 or less disables).
        visual_distance: colour-histogram distance threshold for undated images.
        min_group_size: groups smaller than this are dropped (images stay ungrouped).

    Returns:
        Dicts with ``kind, name, start_ts, end_ts, image_ids``. Photos with an
        EXIF date form "Event" groups; photos dated only by file mtime form
        separate "File date" groups; undated photos form "Visual group" clusters.
    """
    trusted: list[_Item] = []
    weak: list[_Item] = []
    undated: list[Mapping[str, Any]] = []
    for row in rows:
        when = _parse_ts(row["exif_ts"])
        if when is None:
            undated.append(row)
            continue
        item = _Item(when, int(row["id"]), row["gps_lat"], row["gps_lon"])
        (trusted if row["ts_source"] in _TRUSTED_SOURCES else weak).append(item)

    groups = _event_groups(trusted, "Event", event_gap_hours, gps_split_km)
    groups += _event_groups(weak, "File date", event_gap_hours, gps_split_km)
    if undated:
        groups += _visual_groups(undated, visual_distance)
    return [g for g in groups if len(g["image_ids"]) >= min_group_size]