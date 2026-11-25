"""Pipeline post-processing and update steps: duplicates, places, bursts, groups, persons, and search index."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from services.face.clusterer import (
    DEFAULT_COSINE_DISTANCE_EPS,
    attach_faces,
    attach_to_anchors,
    cluster_face_embeddings,
)
from services.intelligence.geo import load_place_index
from services.organization.bursts import detect_bursts
from services.organization.duplicates import find_duplicates
from services.organization.grouper import group_images, name_groups, refine_events
from services.organization.live_pairs import link_live_pairs
from services.pipeline.reporter import write_group_manifest

if TYPE_CHECKING:
    from config import Settings
    from database import DatabaseManager

log = logging.getLogger("photo_organizer.orchestrator")


def update_duplicates(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Recompute duplicate clusters (pHash candidates confirmed by dHash)."""
    from services.pipeline import orchestrator as pipeline
    sig = f"{db.revision()}|{settings.phash_near_threshold}|{settings.dhash_confirm_threshold}"
    cached = db.get_meta("dup_state")
    if cached and not force and cached.split("#")[0] == sig:
        return int(cached.split("#")[1])
    records = [(r["id"], r["sha256"], r["phash"], r["dhash"]) for r in db.fetch_hash_records()]
    rows = pipeline.find_duplicates(records, settings.phash_near_threshold, settings.dhash_confirm_threshold)
    db.replace_duplicates(rows)
    count = len({cluster_id for _, cluster_id, _ in rows})
    db.set_meta("dup_state", f"{sig}#{count}")
    return count


def update_places(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Resolve place names for GPS-tagged photos (offline). Returns how many got a name.

    Photos with no city within ``place_max_km`` get an empty place and are not retried
    unless ``force`` (use after adding a bigger cities file).
    """
    if force:
        db.clear_places()
    index = None
    named = 0
    while True:
        rows = db.fetch_gps_without_place(2000)
        if not rows:
            return named
        if index is None:
            places_dir = settings.workspace / "data" / "places"
            data_dir = places_dir if places_dir.is_dir() else (settings.workspace / "data")
            index = load_place_index(data_dir)
        points = np.array([[r["gps_lat"], r["gps_lon"]] for r in rows], dtype=np.float64)
        labels = index.lookup_many(points, settings.place_max_km)
        db.set_places([(int(r["id"]), label or "") for r, label in zip(rows, labels)])
        named += sum(1 for label in labels if label)


def update_bursts(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Detect bursts and suggest the best frame. Skipped if nothing changed."""
    sig = (f"{db.revision()}|{settings.burst_gap_seconds}|{settings.burst_hash_threshold}|"
           f"{settings.min_burst_size}")
    cached = db.get_meta("burst_state")
    if cached and not force and cached.split("#")[0] == sig:
        return int(cached.split("#")[1])
    bursts = detect_bursts(db.fetch_burst_rows(), gap_seconds=settings.burst_gap_seconds,
                           hash_threshold=settings.burst_hash_threshold,
                           min_size=settings.min_burst_size)
    count = db.replace_bursts(bursts)
    db.set_meta("burst_state", f"{sig}#{count}")
    return count


def update_groups(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Recompute groups: events (refined, place-named) and visual clusters."""
    link_live_pairs(db)
    sig = (f"{db.revision()}|{settings.event_gap_hours}|{settings.gps_split_km}|"
           f"{settings.visual_cluster_distance}|{settings.min_group_size}|"
           f"{settings.refine_min_event_size}|{settings.refine_merge_gap_hours}|"
           f"{settings.refine_max_event_hours}|{settings.group_screenshots}")
    cached = db.get_meta("group_state")
    if cached and not force and cached.split("#")[0] == sig:
        return int(cached.split("#")[1])
    rows = db.fetch_grouping_rows(include_junk=settings.group_screenshots)
    groups = group_images(
        rows, event_gap_hours=settings.event_gap_hours, gps_split_km=settings.gps_split_km,
        visual_distance=settings.visual_cluster_distance, min_group_size=1)
    times = {int(r["id"]): datetime.strptime(r["exif_ts"], "%Y-%m-%dT%H:%M:%S")
             for r in rows if r["exif_ts"]}
    groups = refine_events(groups, times, min_size=settings.refine_min_event_size,
                           merge_gap_hours=settings.refine_merge_gap_hours,
                           max_hours=settings.refine_max_event_hours)
    name_groups(groups, {int(r["id"]): r["place"] for r in rows})
    groups = [g for g in groups if len(g["image_ids"]) >= settings.min_group_size]
    count = db.replace_groups(groups)
    try:
        write_group_manifest(settings, db)
    except OSError as exc:
        log.warning("Could not write group manifest: %s", exc)
    db.set_meta("group_state", f"{sig}#{count}")
    return count


PERSON_MIN_FACE_PX = 40
PERSON_MIN_CONF = 0.8
MIN_PERSON_FACES = 2


def update_persons(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Rebuild people. Confirmed (locked) faces are fixed points; everything else is re-derived."""
    rows = db.fetch_faces_with_embeddings()
    locked = [r for r in rows if r["locked"]]
    sig = (f"{len(rows)}|{sum(int(r['id']) for r in rows)}|{len(locked)}|"
           f"{sum(int(r['id']) for r in locked)}|{DEFAULT_COSINE_DISTANCE_EPS}")
    if not force and db.get_meta("person_state") == sig:
        return len(db.list_persons())

    anchors: dict[int, list[bytes]] = {}
    for r in locked:
        if r["person_id"] is not None:
            anchors.setdefault(int(r["person_id"]), []).append(r["embedding"])
    good, weak = [], []
    for r in rows:
        if r["locked"]:
            continue
        strong = min(r["w"], r["h"]) >= PERSON_MIN_FACE_PX and r["confidence"] >= PERSON_MIN_CONF
        (good if strong else weak).append((int(r["id"]), r["embedding"]))

    # 1. confirmed people claim the free faces that clearly look like them (weak faces: stricter)
    fixed = attach_to_anchors(anchors, good, DEFAULT_COSINE_DISTANCE_EPS)
    for pid, fids in attach_to_anchors(anchors, weak, DEFAULT_COSINE_DISTANCE_EPS * 0.85).items():
        fixed.setdefault(pid, []).extend(fids)
    claimed = {f for fids in fixed.values() for f in fids}
    good = [g for g in good if g[0] not in claimed]
    weak = [w for w in weak if w[0] not in claimed]

    # 2. cluster the rest
    if not good:
        good, weak = weak, []
    clusters = cluster_face_embeddings(good)
    clusters = attach_faces(clusters, good, weak, DEFAULT_COSINE_DISTANCE_EPS * 1.15)
    clusters = {k: v for k, v in clusters.items() if len(v) >= MIN_PERSON_FACES}
    count = db.replace_person_clusters(clusters, fixed=fixed)
    db.set_meta("person_state", sig)
    return count


def update_search_index(settings: Settings, db: DatabaseManager, force: bool = False) -> int:
    """Rebuild the text index when results, groups or places changed. Returns rows indexed."""
    sig = f"{db.revision()}|{(db.get_meta('group_state') or '').replace('#', ':')}|{db.get_meta('persons_rev') or ''}"
    cached = db.get_meta("fts_state")
    if cached and not force and cached.split("#")[0] == sig:
        return int(cached.split("#")[1])
    count = db.rebuild_fts()
    db.set_meta("fts_state", f"{sig}#{count}")
    return count
