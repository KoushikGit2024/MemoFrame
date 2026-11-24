"""Command-line interface: scan, process, group, report, duplicates, search, reset."""
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Callable

from config import Settings
from core.face_detector import DetectorUnavailableError
from database import DatabaseError, DatabaseManager
from processing.pipeline import (
    PipelineError,
    find_missing_images,
    process_pending,
    remove_images,
    scan_directory,
    update_duplicates,
    update_groups,
)
from processing.reporter import format_duplicates, format_report, write_report_files
from utils.file_utils import is_within
from utils.logger import setup_logging
from utils.model_downloader import ModelDownloadError
from utils.validators import ValidationError, existing_dir, positive_float, positive_int, unit_float


class CliError(Exception):
    """A user-facing error (printed without a traceback)."""


# ----------------------------------------------------------------------
# argparse types
# ----------------------------------------------------------------------
def _int_between(low: int, high: int | None = None) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from exc
        if number < low or (high is not None and number > high):
            bound = f"at least {low}" if high is None else f"between {low} and {high}"
            raise argparse.ArgumentTypeError(f"must be {bound}, got {number}")
        return number
    return parse


def _non_negative_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from exc
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or more, got {number}")
    return number


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$")


def _iso_date(value: str) -> str:
    if not _ISO_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, got {value!r}")
    return value


# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", type=Path, default=Path("workspace"),
                        help="folder for the database and generated files (default: ./workspace)")
    common.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    common.add_argument("-q", "--quiet", action="store_true", help="warnings and errors only")

    dup_opts = argparse.ArgumentParser(add_help=False)
    dup_opts.add_argument("--near-threshold", type=_int_between(0, 16), default=None,
                          help="max pHash Hamming distance for near duplicates (default 6)")

    group_opts = argparse.ArgumentParser(add_help=False)
    group_opts.add_argument("--event-gap-hours", type=positive_float, default=None,
                            help="gap that starts a new event (default 3)")
    group_opts.add_argument("--gps-km", type=_non_negative_float, default=None,
                            help="GPS jump that starts a new event; 0 disables (default 5)")
    group_opts.add_argument("--visual-distance", type=positive_float, default=None,
                            help="colour distance for undated images (default 0.35)")
    group_opts.add_argument("--min-group-size", type=positive_int, default=None,
                            help="drop groups smaller than this (default 1)")

    proc_opts = argparse.ArgumentParser(add_help=False)
    proc_opts.add_argument("--workers", type=positive_int, default=None,
                           help="worker processes (default: CPU count - 1, max 4)")
    proc_opts.add_argument("--batch-size", type=positive_int, default=None,
                           help="images per database commit (default 64)")
    proc_opts.add_argument("--cpu-limit", type=unit_float, default=None,
                           help="fraction of time each worker may be busy, 0-1 (default 1)")
    proc_opts.add_argument("--cv-threads", type=positive_int, default=None,
                           help="OpenCV threads per worker (default 1)")
    proc_opts.add_argument("--confidence", type=unit_float, default=None,
                           help="face confidence threshold 0-1 (default 0.7)")
    proc_opts.add_argument("--backend", choices=["yunet", "insightface"], default=None,
                           help="face detector backend (default yunet)")
    proc_opts.add_argument("--min-face-px", type=positive_int, default=None,
                           help="ignore faces smaller than this many pixels (default 20)")
    proc_opts.add_argument("--gpu", action="store_true", help="try GPU acceleration")
    proc_opts.add_argument("--no-annotated", action="store_true",
                           help="do not write annotated copies")
    proc_opts.add_argument("--no-crops", action="store_true", help="do not write face crops")
    proc_opts.add_argument("--retry-failed", action="store_true",
                           help="re-queue images that failed earlier")

    parser = argparse.ArgumentParser(
        prog="photo_organizer",
        description="Local photo organizer: face detection (no identity matching), "
                    "duplicates and event grouping. Original photos are never modified.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("scan", parents=[common], help="discover images and register them")
    p.add_argument("--input", type=existing_dir, required=True, help="photo folder (recursive)")

    p = sub.add_parser("process", parents=[common, proc_opts, dup_opts, group_opts],
                       help="analyse pending images, then rebuild duplicates and groups")
    p.add_argument("--input", type=existing_dir, default=None,
                   help="photo folder to scan first (omit to continue pending work)")

    sub.add_parser("group", parents=[common, group_opts], help="rebuild event groups")

    p = sub.add_parser("duplicates", parents=[common, dup_opts],
                       help="find and list duplicate images")
    p.add_argument("--limit", type=_int_between(0), default=50,
                   help="clusters to show, 0 = all (default 50)")
    p.add_argument("--no-recompute", action="store_true", help="list stored clusters only")

    p = sub.add_parser("report", parents=[common], help="print statistics and write report files")
    p.add_argument("--no-files", action="store_true", help="print only, write no files")

    p = sub.add_parser("search", parents=[common], help="search processed images")
    p.add_argument("--min-faces", type=_int_between(0), default=None)
    p.add_argument("--max-faces", type=_int_between(0), default=None)
    p.add_argument("--from", dest="taken_from", type=_iso_date, default=None,
                   help="taken on/after YYYY-MM-DD")
    p.add_argument("--until", dest="taken_until", type=_iso_date, default=None,
                   help="taken on/before YYYY-MM-DD")
    p.add_argument("--group", dest="group_id", type=positive_int, default=None)
    p.add_argument("--path", dest="path_contains", default=None,
                   help="path contains this text")
    p.add_argument("--limit", type=positive_int, default=50)

    p = sub.add_parser("prune", parents=[common],
                       help="remove records of photos that no longer exist on disk")
    p.add_argument("--input", type=existing_dir, default=None,
                   help="only check records under this folder (it must exist)")
    p.add_argument("--dry-run", action="store_true", help="list missing files, remove nothing")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")

    p = sub.add_parser("reset", parents=[common], help="clear the database and generated files")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    p.add_argument("--db-only", action="store_true", help="keep generated image files")
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    def opt(name: str):
        return getattr(args, name, None)

    base = Settings(workspace=args.workspace.expanduser().resolve())
    return base.with_overrides(
        workers=opt("workers"),
        batch_size=opt("batch_size"),
        cpu_limit=opt("cpu_limit") or None,
        cv_threads=opt("cv_threads"),
        confidence_threshold=opt("confidence"),
        detector_backend=opt("backend"),
        min_face_px=opt("min_face_px"),
        use_gpu=True if opt("gpu") else None,
        save_annotated=False if opt("no_annotated") else None,
        save_face_crops=False if opt("no_crops") else None,
        phash_near_threshold=opt("near_threshold"),
        event_gap_hours=opt("event_gap_hours"),
        gps_split_km=opt("gps_km"),
        visual_cluster_distance=opt("visual_distance"),
        min_group_size=opt("min_group_size"),
    )


def _require_db(settings: Settings) -> None:
    if not settings.db_path.is_file():
        raise CliError(
            f"No database at {settings.db_path}. Run 'scan' or 'process' with --input first "
            "(or pass the right --workspace).")


# ----------------------------------------------------------------------
# Commands (each returns an exit code)
# ----------------------------------------------------------------------
def cmd_scan(args: argparse.Namespace, settings: Settings) -> int:
    settings.ensure_dirs()
    with DatabaseManager(settings.db_path) as db:
        stats = scan_directory(settings, db, args.input)
        pending = db.count_pending()
    print(f"Found {stats.total} image(s): {stats.new} new, {stats.changed} changed, "
          f"{stats.unchanged} unchanged.")
    if pending:
        print(f"{pending} image(s) waiting. Run: python main.py process "
              f"--workspace \"{settings.workspace}\"")
    return 0


def cmd_process(args: argparse.Namespace, settings: Settings) -> int:
    if args.input is None:
        _require_db(settings)
    settings.ensure_dirs()
    with DatabaseManager(settings.db_path) as db:
        if args.input is not None:
            stats = scan_directory(settings, db, args.input)
            print(f"Scan: {stats.new} new, {stats.changed} changed, {stats.unchanged} unchanged.")
        summary = process_pending(
            settings, db, retry_failed=args.retry_failed, show_progress=not args.quiet)
        print(f"Processed {summary.processed}, failed {summary.failed}, "
              f"remaining {summary.remaining}.")
        if summary.interrupted:
            print("Interrupted. Progress is saved; run the same command again to continue.")
            return 130
        clusters = update_duplicates(settings, db)
        groups = update_groups(settings, db)
        print(f"Duplicate clusters: {clusters}. Groups: {groups}.")
    if summary.failed:
        print("Some images failed. See 'report' for the list, or fix them and use --retry-failed.")
    print("Run 'python main.py report' for the full summary.")
    return 0


def cmd_group(args: argparse.Namespace, settings: Settings) -> int:
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        count = update_groups(settings, db)
    print(f"Groups generated: {count}")
    print(f"Group list: {settings.grouped_dir / 'groups.csv'}")
    return 0


def cmd_duplicates(args: argparse.Namespace, settings: Settings) -> int:
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        if not args.no_recompute:
            update_duplicates(settings, db)
        print(format_duplicates(db, args.limit or None))
    return 0


def cmd_report(args: argparse.Namespace, settings: Settings) -> int:
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        print(format_report(db.report_stats()))
        failed = db.failed_images()
        if failed:
            print("\nFailed images (first 10):")
            for row in failed[:10]:
                print(f"  {row['path']}: {row['error']}")
            if len(failed) > 10:
                print(f"  ... and {len(failed) - 10} more (see the failed_*.csv report)")
        if not args.no_files:
            print("\nReport files:")
            for path in write_report_files(settings, db):
                print(f"  {path}")
    return 0


def cmd_search(args: argparse.Namespace, settings: Settings) -> int:
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        rows = db.search_images(
            min_faces=args.min_faces, max_faces=args.max_faces,
            taken_from=args.taken_from, taken_until=args.taken_until,
            group_id=args.group_id, path_contains=args.path_contains, limit=args.limit)
    for r in rows:
        print(f"{r['id']:>7}  {r['exif_ts'] or '-':19}  faces={r['face_count']:<2}  {r['path']}")
    print(f"{len(rows)} result(s)" + (f" (limit {args.limit})" if len(rows) == args.limit else ""))
    return 0

def cmd_prune(args: argparse.Namespace, settings: Settings) -> int:
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        checked, missing = find_missing_images(db, args.input)
        print(f"Checked {checked} record(s); {len(missing)} missing from disk.")
        if not missing:
            return 0
        for _, path in missing[:10]:
            print(f"  {path}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")
        if args.dry_run:
            print("Dry run: nothing removed.")
            return 0
        if len(missing) == checked:
            print("Warning: every checked file is missing. Is the drive connected?")
        if not args.yes:
            try:
                answer = input("Remove these records and their generated files? "
                               "Type 'yes' to continue: ").strip().lower()
            except EOFError:
                answer = ""
            if answer != "yes":
                print("Cancelled.")
                return 1
        removed = remove_images(settings, db, [i for i, _ in missing])
    print(f"Removed {removed} record(s). Your photos were not touched.")
    return 0

def cmd_reset(args: argparse.Namespace, settings: Settings) -> int:
    scope = "the database" if args.db_only else (
        "the database and generated files (thumbnails, face crops, annotated copies, "
        "group list)")
    if not args.yes:
        print(f"This clears {scope} in {settings.workspace}.\n"
              "Your original photos are not touched. Models and reports are kept.")
        try:
            answer = input("Type 'yes' to continue: ").strip().lower()
        except EOFError:
            answer = ""
        if answer != "yes":
            print("Cancelled.")
            return 1
    if settings.db_path.is_file():
        with DatabaseManager(settings.db_path) as db:
            db.reset()
    if not args.db_only:
        for target in (settings.thumbnails_dir, settings.face_crops_dir,
                       settings.annotated_dir, settings.grouped_dir):
            if target.is_dir() and is_within(target, settings.workspace):
                try:
                    shutil.rmtree(target)
                except OSError as exc:
                    print(f"warning: could not fully remove {target}: {exc}", file=sys.stderr)
        if settings.workspace.is_dir():
            settings.ensure_dirs()
    print("Reset complete.")
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace, Settings], int]] = {
    "scan": cmd_scan,
    "process": cmd_process,
    "group": cmd_group,
    "duplicates": cmd_duplicates,
    "report": cmd_report,
    "search": cmd_search,
    "reset": cmd_reset,
    "prune": cmd_prune,
}


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the command, and return the exit code."""
    args = build_parser().parse_args(argv)
    settings = _settings(args)
    write_log = args.command in ("scan", "process") or settings.workspace.is_dir()
    setup_logging(settings.log_path if write_log else None,
                  verbose=args.verbose, quiet=args.quiet)
    try:
        return COMMANDS[args.command](args, settings)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except (CliError, ValidationError, ModelDownloadError, DetectorUnavailableError,
            PipelineError, DatabaseError, sqlite3.Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1