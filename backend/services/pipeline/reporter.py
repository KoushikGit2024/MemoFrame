"""Reports: console text, JSON/CSV files, and the group manifest."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from config import Settings
from services.organization.duplicates import choose_keeper
from database import DatabaseManager
from utils.file_utils import atomic_write_bytes, human_size


def format_report(stats: dict[str, int]) -> str:
    """Human-readable summary of ``DatabaseManager.report_stats()``."""
    lines = [
        "Photo organizer report",
        "======================",
        f"Total images scanned:           {stats['total_images']}",
        f"Successfully processed:         {stats['processed']}",
        f"Failed:                         {stats['failed']}",
    ]
    if stats["pending"]:
        lines.append(f"Still pending:                  {stats['pending']}")
    lines += [
        f"Faces detected (total):         {stats['total_faces']}",
        f"Images with at least one face:  {stats['images_with_faces']}",
        f"Images with multiple faces:     {stats['multi_face_images']}",
        f"Duplicate clusters:             {stats['duplicate_clusters']}",
        f"Duplicate images (extra copies): {stats['duplicate_images']}",
        f"Groups generated:               {stats['groups']}",
        "",
        "Note: counts are detected faces; see 'people' for identified clusters.",
    ]
    return "\n".join(lines)


def format_duplicates(db: DatabaseManager, limit: int | None = 50) -> str:
    """List duplicate clusters, marking one suggested keeper per cluster."""
    clusters = db.get_duplicate_clusters()
    if not clusters:
        return "No duplicates found."
    lines: list[str] = []
    for n, (cluster_id, members) in enumerate(clusters.items()):
        if limit is not None and n >= limit:
            lines.append(f"... {len(clusters) - limit} more cluster(s). Full list: report command.")
            break
        keeper = choose_keeper(members)
        lines.append(f"Cluster {cluster_id} ({members[0]['kind']}, {len(members)} files)")
        for m in members:
            mark = "*" if m["id"] == keeper else " "
            size = f"{m['width']}x{m['height']}" if m["width"] else "?"
            lines.append(f"  {mark} {m['path']}  {size}  {human_size(m['size'])}")
    lines.append("")
    lines.append("* = suggested file to keep. Nothing has been deleted or modified.")
    return "\n".join(lines)


def _csv_bytes(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")      # BOM: Excel on Windows reads UTF-8


def write_group_manifest(settings: Settings, db: DatabaseManager) -> Path:
    """Write ``grouped_images/groups.csv`` listing every group and its images.

    Only a list is written. Photographs are never copied, moved or linked.
    """
    rows: list[list[Any]] = []
    for g in db.get_groups():
        for img in db.get_group_images(g["id"]):
            rows.append([g["id"], g["kind"], g["name"], g["start_ts"], g["end_ts"],
                         img["id"], img["path"], img["exif_ts"], img["face_count"]])
    dest = settings.grouped_dir / "groups.csv"
    atomic_write_bytes(dest, _csv_bytes(
        ["group_id", "kind", "name", "start_ts", "end_ts",
         "image_id", "path", "exif_ts", "face_count"], rows))
    return dest


def write_report_files(settings: Settings, db: DatabaseManager) -> list[Path]:
    """Write timestamped JSON and CSV reports to the reports folder.

    Returns the paths written: ``report_*.json``, ``duplicates_*.csv`` and,
    only if something failed, ``failed_*.csv``.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = settings.reports_dir
    failed = [(r["path"], r["error"]) for r in db.failed_images()]
    paths: list[Path] = []

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stats": db.report_stats(),
        "failed": [{"path": p, "error": e} for p, e in failed],
    }
    dest = out / f"report_{stamp}.json"
    atomic_write_bytes(dest, json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))
    paths.append(dest)

    dup_rows: list[list[Any]] = []
    for cluster_id, members in db.get_duplicate_clusters().items():
        keeper = choose_keeper(members)
        for m in members:
            dup_rows.append([cluster_id, m["kind"], m["id"] == keeper, m["id"],
                             m["path"], m["size"], m["width"], m["height"]])
    dest = out / f"duplicates_{stamp}.csv"
    atomic_write_bytes(dest, _csv_bytes(
        ["cluster_id", "kind", "suggested_keep", "image_id", "path", "size", "width", "height"],
        dup_rows))
    paths.append(dest)

    if failed:
        dest = out / f"failed_{stamp}.csv"
        atomic_write_bytes(dest, _csv_bytes(["path", "error"], failed))
        paths.append(dest)
    return paths