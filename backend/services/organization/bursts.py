"""Burst detection: near-identical shots taken seconds apart (EXIF-dated photos only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from services.organization.similarity import parse_phash

_ISO = "%Y-%m-%dT%H:%M:%S"


def detect_bursts(
    rows: Iterable[Mapping[str, Any]],
    *,
    gap_seconds: float = 2.0,
    hash_threshold: int = 14,
    min_size: int = 3,
) -> list[dict[str, Any]]:
    """Runs of consecutive photos within ``gap_seconds`` whose pHashes are close.

    Returns ``{"image_ids": [...], "best_id": id}``; the best frame has the highest
    quality (ties: lowest id).
    """
    items = []
    for r in rows:
        try:
            when = datetime.strptime(str(r["exif_ts"]), _ISO)
        except (ValueError, TypeError):
            continue
        ph = parse_phash(r["phash"])
        if ph is not None:
            items.append((when, int(r["id"]), ph, r["quality"]))
    items.sort(key=lambda t: (t[0], t[1]))

    runs: list[list[tuple]] = []
    cur: list[tuple] = []
    for it in items:
        if (
            cur
            and (it[0] - cur[-1][0]).total_seconds() <= gap_seconds
            and (it[2] ^ cur[-1][2]).bit_count() <= hash_threshold
        ):
            cur.append(it)
        else:
            if len(cur) >= min_size:
                runs.append(cur)
            cur = [it]
    if len(cur) >= min_size:
        runs.append(cur)

    return [
        {
            "image_ids": [t[1] for t in run],
            "best_id": max(run, key=lambda t: (t[3] if t[3] is not None else -1.0, -t[1]))[1],
        }
        for run in runs
    ]
