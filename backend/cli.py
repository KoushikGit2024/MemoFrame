"""Command-line interface: scan, process, group, report, duplicates, search, reset."""
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Callable

from config import DEFAULT_WORKSPACE, Settings
from services.face.detector import DetectorUnavailableError
from services.intelligence.tagger import TaggerUnavailableError
from database import DatabaseError, DatabaseManager
from services.pipeline.orchestrator import (
    PipelineError,
    find_missing_images,
    process_pending,
    remove_images,
    scan_directory,
    update_bursts,
    update_duplicates,
    update_groups,
    update_persons,
    update_places,
    update_search_index,
)
from services.pipeline.reporter import format_duplicates, format_report, write_report_files
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
    common.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE,
                        help=f"folder for the database and generated files (default: {DEFAULT_WORKSPACE})")
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
    proc_opts.add_argument("--storage", choices=["hdd", "ssd"], default=None,
                           help="drive type; hdd limits parallel reads (default hdd)")
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
    proc_opts.add_argument("--tiled", action="store_true",
                           help="extra small-face pass on large photos (slower)")
    proc_opts.add_argument("--no-annotated", action="store_true",
                           help="do not write annotated copies")
    proc_opts.add_argument("--no-crops", action="store_true", help="do not write face crops")
    proc_opts.add_argument("--tags", action="store_true",
                           help="tag photos with scene labels (needs scene_model.onnx)")
    proc_opts.add_argument("--store-embeddings", action="store_true",
                           help="save tagger embeddings for 'find similar' search")
    proc_opts.add_argument("--retry-failed", action="store_true",
                           help="re-queue images that failed earlier")

    parser = argparse.ArgumentParser(
        prog="photo_organizer",
        description="Local photo organizer: face detection and offline person clustering, "
                    "duplicates and event grouping. Original photos are never modified.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("scan", parents=[common], help="discover images and register them")
    p.add_argument("--input", type=existing_dir, required=True, help="photo folder (recursive)")

    p = sub.add_parser("process", parents=[common, proc_opts, dup_opts, group_opts],
                       help="analyse pending images, then rebuild duplicates and groups")
    p.add_argument("--input", type=existing_dir, default=None,
                   help="photo folder to scan first (omit to continue pending work)")

    p = sub.add_parser("rescan", parents=[common, proc_opts, dup_opts, group_opts],
                       help="trigger an on-demand rescan of a folder or known sources (offline, no background polling)")
    p.add_argument("--input", type=existing_dir, default=None,
                   help="folder to rescan (omit to rescan all previously known sources)")

    sub.add_parser("group", parents=[common, group_opts], help="rebuild event groups")

    p = sub.add_parser("duplicates", parents=[common, dup_opts],
                       help="find and list duplicate images")
    p.add_argument("--limit", type=_int_between(0), default=50,
                   help="clusters to show, 0 = all (default 50)")
    p.add_argument("--no-recompute", action="store_true", help="list stored clusters only")

    p = sub.add_parser("people", parents=[common], help="list or recompute people clusters")
    p.add_argument("--recompute", action="store_true", help="force re-clustering people")
    p.add_argument("--rename", nargs=2, metavar=("PERSON_ID", "NAME"),
                   help="rename a person: --rename 1 'Alice'")

    p = sub.add_parser("report", parents=[common], help="print statistics and write report files")
    p.add_argument("--no-files", action="store_true", help="print only, write no files")

    p = sub.add_parser("search", parents=[common], help="search processed images")
    p.add_argument("--text", default=None, help="words to find (file, folder, place, event, date)")
    p.add_argument("--kind", choices=["photo", "video"], default=None, help="filter by kind")
    p.add_argument("--type", dest="content_type", choices=["photo", "screenshot", "document"], default=None)
    p.add_argument("--min-quality", type=positive_float, default=None)
    p.add_argument("--place", dest="place", default=None, help="place contains this text")
    p.add_argument("--tag", dest="tag", default=None, help="tagged with this label")
    p.add_argument("--mark", choices=["keep", "reviewed", "favourite", "hidden"], default=None)
    p.add_argument("--duplicate", choices=["none", "any", "exact", "near"], default=None)
    p.add_argument("--sort", choices=["date", "date_desc", "quality", "path", "size"], default="date")
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

    p = sub.add_parser("doctor", parents=[common], help="check the environment")
    p.add_argument("--input", type=Path, action="append", default=[],
                   help="a photo folder to check is reachable (repeatable)")

    p = sub.add_parser("maintain", parents=[common], help="database and cache maintenance")
    p.add_argument("--check-files", action="store_true", help="mark photos ok / offline / missing")
    p.add_argument("--forget-missing", action="store_true",
                   help="drop records of photos confirmed missing (database only)")
    p.add_argument("--clear-thumbnails", action="store_true", help="delete cached thumbnails")
    p.add_argument("--repair", action="store_true", help="fix inconsistencies after a crash")
    p.add_argument("--vacuum", action="store_true", help="compact the database (slow)")

    p = sub.add_parser("analyze", parents=[common],
                       help="fill quality/dHash/content type for photos processed earlier")
    p.add_argument("--refresh-places", action="store_true", help="re-resolve all place names")

    p = sub.add_parser("tag", parents=[common],
                       help="tag already-processed photos with scene labels")
    p.add_argument("--store-embeddings", action="store_true",
                   help="save embeddings for 'find similar' search")
    p.add_argument("--retag", action="store_true",
                   help="re-tag photos that already have tags")

    p = sub.add_parser("watch", parents=[common],
                       help="watch folders and process new photos (read-only, gentle)")
    p.add_argument("--input", type=existing_dir, action="append", default=[],
                   help="folder to watch (repeatable; default: folders scanned before)")
    p.add_argument("--interval", type=positive_float, default=None, help="seconds between checks (30)")
    p.add_argument("--settle", type=_non_negative_float, default=None,
                   help="seconds a file must be unchanged (10)")
    p.add_argument("--allow-battery", action="store_true", help="keep working on battery power")

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
        storage_type=opt("storage"),
        cpu_limit=opt("cpu_limit") or None,
        cv_threads=opt("cv_threads"),
        confidence_threshold=opt("confidence"),
        detector_backend=opt("backend"),
        min_face_px=opt("min_face_px"),
        use_gpu=True if opt("gpu") else None,
        tiled_detection=True if opt("tiled") else None,
        save_annotated=False if opt("no_annotated") else None,
        save_face_crops=False if opt("no_crops") else None,
        tagging_enabled=True if opt("tags") else None,
        store_embeddings=True if opt("store_embeddings") else None,
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
        update_places(settings, db)
        update_bursts(settings, db)
        groups = update_groups(settings, db)
        persons = update_persons(settings, db)
        update_search_index(settings, db)
        print(f"Duplicate clusters: {clusters}. Groups: {groups}. People: {persons}.")
    if summary.failed:
        print("Some images failed. See 'report' for the list, or fix them and use --retry-failed.")
    print("Run 'python main.py report' for the full summary.")
    return 0


def cmd_rescan(args: argparse.Namespace, settings: Settings) -> int:
    return cmd_process(args, settings)


def cmd_group(args: argparse.Namespace, settings: Settings) -> int:
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        count = update_groups(settings, db, force=True)
    print(f"Groups generated: {count}")
    print(f"Group list: {settings.grouped_dir / 'groups.csv'}")
    return 0


def cmd_duplicates(args: argparse.Namespace, settings: Settings) -> int:
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        if not args.no_recompute:
            update_duplicates(settings, db, force=True)
        print(format_duplicates(db, args.limit or None))
    return 0


def cmd_people(args: argparse.Namespace, settings: Settings) -> int:
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        if args.rename:
            pid_str, new_name = args.rename
            try:
                pid = int(pid_str)
            except ValueError:
                raise CliError(f"Person ID must be an integer: {pid_str!r}")
            if not new_name.strip():
                raise CliError("Person name cannot be empty.")
            if not db.rename_person(pid, new_name.strip()):
                raise CliError(f"No person with ID {pid}.")
            update_search_index(settings, db)
            print(f"Renamed person {pid} to {new_name.strip()!r}.")
            return 0

        if args.recompute:
            count = update_persons(settings, db, force=True)
            update_search_index(settings, db)
            print(f"People clusters recomputed: {count}.")

        persons = db.list_persons()
        if not persons:
            print("No people found.")
            return 0
        print(f"Found {len(persons)} person(s):")
        for p in persons:
            print(f"  [{p['id']}] {p['name']} ({p['image_count']} photos)")
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
    wanted = dict(
        text=args.text, min_faces=args.min_faces, max_faces=args.max_faces,
        taken_from=args.taken_from, taken_until=args.taken_until, group_id=args.group_id,
        path_contains=args.path_contains, place_contains=getattr(args, "place", None),
        content_type=getattr(args, "content_type", None), kind=getattr(args, "kind", None),
        min_quality=getattr(args, "min_quality", None), mark=args.mark, duplicate=args.duplicate,
        tag=getattr(args, "tag", None))
    filters = {k: v for k, v in wanted.items() if v is not None}
    with DatabaseManager(settings.db_path) as db:
        if args.text:
            update_search_index(settings, db)
        rows = db.find_images(sort=args.sort, limit=args.limit, **filters)
    for r in rows:
        print(f"{r['id']:>7}  {r['effective_ts'] or '-':19}  faces={r['face_count']:<2}  {r['path']}")
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

def cmd_doctor(args: argparse.Namespace, settings: Settings) -> int:
    from engine.doctor import run_checks
    checks = run_checks(settings, args.input)
    for c in checks:
        print(f"[{c.status.upper():4}] {c.name}: {c.detail}")
        if c.fix and c.status != "ok":
            print(f"       fix: {c.fix}")
    return 1 if any(c.status == "fail" for c in checks) else 0


def cmd_maintain(args: argparse.Namespace, settings: Settings) -> int:
    from services.pipeline import maintenance as m
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        if args.check_files:
            print("File states:", m.refresh_states(db))
        if args.forget_missing:
            n = m.forget_missing(settings, db)
            print(f"Forgot {n} missing record(s). Photos were not touched.")
            if n:
                update_duplicates(settings, db)
                update_groups(settings, db)
                update_persons(settings, db)
        if args.clear_thumbnails:
            print("Cleared thumbnails (MB freed):", m.clear_cache(settings, db, ("thumbnails",)))
        if args.repair:
            print("Repair:", db.repair())
        print("Maintenance:", m.run_maintenance(settings, db, vacuum=args.vacuum))
    return 0


def cmd_analyze(args: argparse.Namespace, settings: Settings) -> int:
    from services.pipeline.enrich import enrich_existing
    _require_db(settings)
    with DatabaseManager(settings.db_path) as db:
        print(f"Analysed {enrich_existing(settings, db)} photo(s).")
        named = update_places(settings, db, force=args.refresh_places)
        persons = update_persons(settings, db)
        print(f"Places named: {named}. Duplicate clusters: {update_duplicates(settings, db)}. "
              f"Bursts: {update_bursts(settings, db)}. Groups: {update_groups(settings, db)}. "
              f"People: {persons}.")
        update_search_index(settings, db)
    return 0


def cmd_tag(args: argparse.Namespace, settings: Settings) -> int:
    from services.intelligence.tagging import tag_existing
    _require_db(settings)
    if args.store_embeddings:
        settings = settings.with_overrides(store_embeddings=True)
    with DatabaseManager(settings.db_path) as db:
        if args.retag:
            db.clear_tags()
        tagged = tag_existing(settings, db)
        print(f"Tagged {tagged} photo(s).")
        if tagged:
            update_search_index(settings, db)
    return 0


def cmd_watch(args: argparse.Namespace, settings: Settings) -> int:
    from engine.profiles import apply_profile
    from services.pipeline.control import RunControl
    from services.pipeline.watcher import FolderWatcher

    settings = apply_profile(settings, "gentle").with_overrides(
        watch_interval_s=args.interval, watch_settle_s=args.settle,
        watch_pause_on_battery=False if args.allow_battery else None)
    settings.ensure_dirs()

    def show(ev) -> None:
        if ev.stage in ("watch", "waiting"):
            print(f"[{ev.stage}] {ev.message}", flush=True)

    control = RunControl(show, settings.min_free_mem_mb)
    with DatabaseManager(settings.db_path) as db:
        roots = list(args.input) or [Path(s) for s in db.list_sources()]
        if not roots:
            raise CliError("Nothing to watch. Pass --input FOLDER (repeatable).")
        print("Watching (Ctrl+C to stop). Photos are only read, never changed.")
        try:
            FolderWatcher(settings, db, roots, control).run()
        except KeyboardInterrupt:
            print("\nStopped.")
            return 130
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
    "rescan": cmd_rescan,
    "group": cmd_group,
    "duplicates": cmd_duplicates,
    "people": cmd_people,
    "report": cmd_report,
    "search": cmd_search,
    "analyze": cmd_analyze,
    "tag": cmd_tag,
    "watch": cmd_watch,
    "reset": cmd_reset,
    "prune": cmd_prune,
    "doctor": cmd_doctor,
    "maintain": cmd_maintain,
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
            TaggerUnavailableError, PipelineError, DatabaseError, sqlite3.Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1