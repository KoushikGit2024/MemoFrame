"""Pipeline orchestration, background polling, and maintenance service."""
from .control import ProgressCallback, ProgressEvent, RunControl
from .enrich import enrich_existing
from .maintenance import (
    cache_info,
    clear_cache,
    enforce_cache_cap,
    forget_missing,
    get_thumbnail,
    refresh_states,
    run_maintenance,
)
from .reporter import format_duplicates, format_report, write_group_manifest, write_report_files
from .scanner import iter_image_files
from .watcher import FolderWatcher
from . import orchestrator
from .orchestrator import (
    PipelineError,
    ProcessSummary,
    find_missing_images,
    process_pending,
    remove_images,
    run_pipeline,
    scan_directory,
    update_bursts,
    update_duplicates,
    update_groups,
    update_persons,
    update_places,
    update_search_index,
    create_detector,
)

# Re-export orchestrator as pipeline attribute for compatibility with tests monkeypatching `pipeline.create_detector`
pipeline = orchestrator

__all__ = [
    "ProgressCallback",
    "ProgressEvent",
    "RunControl",
    "enrich_existing",
    "cache_info",
    "clear_cache",
    "enforce_cache_cap",
    "forget_missing",
    "get_thumbnail",
    "refresh_states",
    "run_maintenance",
    "format_duplicates",
    "format_report",
    "write_group_manifest",
    "write_report_files",
    "iter_image_files",
    "FolderWatcher",
    "PipelineError",
    "ProcessSummary",
    "find_missing_images",
    "process_pending",
    "remove_images",
    "run_pipeline",
    "scan_directory",
    "update_bursts",
    "update_duplicates",
    "update_groups",
    "update_persons",
    "update_places",
    "update_search_index",
    "create_detector",
    "orchestrator",
    "pipeline",
]
