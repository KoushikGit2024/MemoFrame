"""Command-line argument parser for the photo organizer CLI."""

from __future__ import annotations

import argparse
import argparse
import re
from pathlib import Path
from typing import Callable

from config import DEFAULT_WORKSPACE
from utils.validators import (
    existing_dir,
    positive_float,
    positive_int,
    unit_float,
)


def _int_between(low: int, high: int | None = None) -> Callable[[str], int]:
    def parse(val: str) -> int:
        try:
            n = int(val)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Must be an integer: {val!r}") from exc
        if n < low:
            raise argparse.ArgumentTypeError(f"Must be >= {low}")
        if high is not None and n > high:
            raise argparse.ArgumentTypeError(f"Must be <= {high}")
        return n

    return parse


def _non_negative_float(value: str) -> float:
    try:
        f = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Not a float: {value!r}") from exc
    if f < 0:
        raise argparse.ArgumentTypeError("Must be >= 0")
    return f


def _iso_date(value: str) -> str:
    from datetime import date

    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Not a YYYY-MM-DD date: {value!r}") from exc
    return value


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help=f"folder for the database and generated files (default: {DEFAULT_WORKSPACE})",
    )
    common.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    common.add_argument("-q", "--quiet", action="store_true", help="warnings and errors only")

    dup_opts = argparse.ArgumentParser(add_help=False)
    dup_opts.add_argument(
        "--near-threshold",
        type=_int_between(0, 16),
        default=None,
        help="max pHash Hamming distance for near duplicates (default 6)",
    )

    group_opts = argparse.ArgumentParser(add_help=False)
    group_opts.add_argument(
        "--event-gap-hours",
        type=positive_float,
        default=None,
        help="gap that starts a new event (default 3)",
    )
    group_opts.add_argument(
        "--gps-km",
        type=_non_negative_float,
        default=None,
        help="GPS jump that starts a new event; 0 disables (default 5)",
    )
    group_opts.add_argument(
        "--visual-distance",
        type=positive_float,
        default=None,
        help="colour distance for undated images (default 0.35)",
    )
    group_opts.add_argument(
        "--min-group-size",
        type=positive_int,
        default=None,
        help="drop groups smaller than this (default 1)",
    )

    proc_opts = argparse.ArgumentParser(add_help=False)
    proc_opts.add_argument(
        "--workers",
        type=positive_int,
        default=None,
        help="worker processes (default: CPU count - 1, max 4)",
    )
    proc_opts.add_argument(
        "--batch-size",
        type=positive_int,
        default=None,
        help="images per database commit (default 64)",
    )
    proc_opts.add_argument(
        "--storage",
        choices=["hdd", "ssd"],
        default=None,
        help="drive type; hdd limits parallel reads (default hdd)",
    )
    proc_opts.add_argument(
        "--cpu-limit",
        type=unit_float,
        default=None,
        help="fraction of time each worker may be busy, 0-1 (default 1)",
    )
    proc_opts.add_argument(
        "--cv-threads",
        type=positive_int,
        default=None,
        help="OpenCV threads per worker (default 1)",
    )
    proc_opts.add_argument(
        "--confidence",
        type=unit_float,
        default=None,
        help="face confidence threshold 0-1 (default 0.7)",
    )
    proc_opts.add_argument(
        "--backend",
        choices=["yunet", "insightface"],
        default=None,
        help="face detector backend (default yunet)",
    )
    proc_opts.add_argument(
        "--min-face-px",
        type=positive_int,
        default=None,
        help="ignore faces smaller than this many pixels (default 20)",
    )
    proc_opts.add_argument("--gpu", action="store_true", help="try GPU acceleration")
    proc_opts.add_argument(
        "--tiled", action="store_true", help="extra small-face pass on large photos (slower)"
    )
    proc_opts.add_argument(
        "--no-annotated", action="store_true", help="do not write annotated copies"
    )
    proc_opts.add_argument("--no-crops", action="store_true", help="do not write face crops")
    proc_opts.add_argument(
        "--tags", action="store_true", help="tag photos with scene labels (needs scene_model.onnx)"
    )
    proc_opts.add_argument(
        "--store-embeddings",
        action="store_true",
        help="save tagger embeddings for 'find similar' search",
    )
    proc_opts.add_argument(
        "--retry-failed", action="store_true", help="re-queue images that failed earlier"
    )

    parser = argparse.ArgumentParser(
        prog="photo_organizer",
        description="Local photo organizer: face detection and offline person clustering, "
        "duplicates and event grouping. Original photos are never modified.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("scan", parents=[common], help="discover images and register them")
    p.add_argument("--input", type=existing_dir, required=True, help="photo folder (recursive)")

    p = sub.add_parser(
        "process",
        parents=[common, proc_opts, dup_opts, group_opts],
        help="analyse pending images, then rebuild duplicates and groups",
    )
    p.add_argument(
        "--input",
        type=existing_dir,
        default=None,
        help="photo folder to scan first (omit to continue pending work)",
    )

    p = sub.add_parser(
        "rescan",
        parents=[common, proc_opts, dup_opts, group_opts],
        help="trigger an on-demand rescan of a folder or known sources (offline, no background polling)",
    )
    p.add_argument(
        "--input",
        type=existing_dir,
        default=None,
        help="folder to rescan (omit to rescan all previously known sources)",
    )

    sub.add_parser("group", parents=[common, group_opts], help="rebuild event groups")

    p = sub.add_parser(
        "duplicates", parents=[common, dup_opts], help="find and list duplicate images"
    )
    p.add_argument(
        "--limit", type=_int_between(0), default=50, help="clusters to show, 0 = all (default 50)"
    )
    p.add_argument("--no-recompute", action="store_true", help="list stored clusters only")

    p = sub.add_parser("people", parents=[common], help="list or recompute people clusters")
    p.add_argument("--recompute", action="store_true", help="force re-clustering people")
    p.add_argument(
        "--rename",
        nargs=2,
        metavar=("PERSON_ID", "NAME"),
        help="rename a person: --rename 1 'Alice'",
    )

    p = sub.add_parser("report", parents=[common], help="print statistics and write report files")
    p.add_argument("--no-files", action="store_true", help="print only, write no files")

    p = sub.add_parser("search", parents=[common], help="search processed images")
    p.add_argument("--text", default=None, help="words to find (file, folder, place, event, date)")
    p.add_argument("--kind", choices=["photo", "video"], default=None, help="filter by kind")
    p.add_argument(
        "--type", dest="content_type", choices=["photo", "screenshot", "document"], default=None
    )
    p.add_argument("--min-quality", type=positive_float, default=None)
    p.add_argument("--place", dest="place", default=None, help="place contains this text")
    p.add_argument("--tag", dest="tag", default=None, help="tagged with this label")
    p.add_argument("--mark", choices=["keep", "reviewed", "favourite", "hidden"], default=None)
    p.add_argument("--duplicate", choices=["none", "any", "exact", "near"], default=None)
    p.add_argument(
        "--sort", choices=["date", "date_desc", "quality", "path", "size"], default="date"
    )
    p.add_argument("--min-faces", type=_int_between(0), default=None)
    p.add_argument("--max-faces", type=_int_between(0), default=None)
    p.add_argument(
        "--from", dest="taken_from", type=_iso_date, default=None, help="taken on/after YYYY-MM-DD"
    )
    p.add_argument(
        "--until",
        dest="taken_until",
        type=_iso_date,
        default=None,
        help="taken on/before YYYY-MM-DD",
    )
    p.add_argument("--group", dest="group_id", type=positive_int, default=None)
    p.add_argument("--path", dest="path_contains", default=None, help="path contains this text")
    p.add_argument("--limit", type=positive_int, default=50)

    p = sub.add_parser(
        "prune", parents=[common], help="remove records of photos that no longer exist on disk"
    )
    p.add_argument(
        "--input",
        type=existing_dir,
        default=None,
        help="only check records under this folder (it must exist)",
    )
    p.add_argument("--dry-run", action="store_true", help="list missing files, remove nothing")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")

    p = sub.add_parser("doctor", parents=[common], help="check the environment")
    p.add_argument(
        "--input",
        type=Path,
        action="append",
        default=[],
        help="a photo folder to check is reachable (repeatable)",
    )

    p = sub.add_parser("maintain", parents=[common], help="database and cache maintenance")
    p.add_argument("--check-files", action="store_true", help="mark photos ok / offline / missing")
    p.add_argument(
        "--forget-missing",
        action="store_true",
        help="drop records of photos confirmed missing (database only)",
    )
    p.add_argument("--clear-thumbnails", action="store_true", help="delete cached thumbnails")
    p.add_argument("--repair", action="store_true", help="fix inconsistencies after a crash")
    p.add_argument("--vacuum", action="store_true", help="compact the database (slow)")

    p = sub.add_parser(
        "analyze",
        parents=[common],
        help="fill quality/dHash/content type for photos processed earlier",
    )
    p.add_argument("--refresh-places", action="store_true", help="re-resolve all place names")

    p = sub.add_parser(
        "tag", parents=[common], help="tag already-processed photos with scene labels"
    )
    p.add_argument(
        "--store-embeddings", action="store_true", help="save embeddings for 'find similar' search"
    )
    p.add_argument("--retag", action="store_true", help="re-tag photos that already have tags")

    p = sub.add_parser(
        "watch", parents=[common], help="watch folders and process new photos (read-only, gentle)"
    )
    p.add_argument(
        "--input",
        type=existing_dir,
        action="append",
        default=[],
        help="folder to watch (repeatable; default: folders scanned before)",
    )
    p.add_argument(
        "--interval", type=positive_float, default=None, help="seconds between checks (30)"
    )
    p.add_argument(
        "--settle",
        type=_non_negative_float,
        default=None,
        help="seconds a file must be unchanged (10)",
    )
    p.add_argument("--allow-battery", action="store_true", help="keep working on battery power")

    p = sub.add_parser("reset", parents=[common], help="clear the database and generated files")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    p.add_argument("--db-only", action="store_true", help="keep generated image files")
    return parser
