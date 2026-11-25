# Engine API (version 1.1.0)

Versioning: MAJOR = breaking change, MINOR = additions. `Engine.api_version` and
`python -m engine version` report it.

## Rules
- The engine only READS photos. All writes go to the workspace.
- One `Engine` per workspace at a time (OS file lock; otherwise `WORKSPACE_LOCKED`).
- Run long calls (`run_all`, `process`, `analyze_existing`) on a worker thread. Call one
  long operation at a time. `cancel`, `pause`, `resume` may be called from any thread.
  Queries from another thread are allowed but may wait briefly during a batch commit.
- Every method returns plain dicts, lists and numbers. Errors raise `EngineError`
  with `.code`, `.message`, `.hint` (`.to_dict()`).

## Lifecycle
```python
with Engine(workspace, profile="gentle", on_event=callback) as eng:
    eng.run_all(folder)
```
Profiles: `gentle`, `balanced`, `fast`. Settings: `<workspace>/config.toml`.
`on_event` receives `ProgressEvent(stage, done, total, failed, current, message)` on the
worker thread. Stages: `scan`, `process`, `duplicates`, `places`, `bursts`, `groups`, `persons`, `index`, `analyze`, `tag`, `watch`, `waiting`
(`message` = `paused` / `low memory` / `resumed` / `on battery`), `done`.

## Error codes
DRIVE_OFFLINE, MODEL_MISSING, MODEL_DOWNLOAD_FAILED, DETECTOR_UNAVAILABLE, TAGGER_UNAVAILABLE, CONFIG_INVALID,
DB_ERROR, WORKER_CRASH, INVALID_INPUT, IO_ERROR, NOT_OPEN, WORKSPACE_LOCKED, UNKNOWN.
Per-photo failures are not exceptions: see `failed_images()`; `error` starts with
FILE_MISSING, FILE_UNREADABLE, CORRUPT_IMAGE, CORRUPT_VIDEO or UNSUPPORTED_FORMAT.

## Methods
| Area | Methods |
|---|---|
| Work | `scan`, `process`, `run_all`, `analyze_existing`, `recognize_existing(force=False)`, `rebuild`, `cancel`, `pause`, `resume`, `watch`, `reset_workspace(keep_generated=False, clear_sources=False, clear_saved_searches=False)` |
| Query | `find`, `count`, `timeline`, `search`, `get_image`, `get_faces`, `get_faces_many`, `get_groups`, `get_group_images`, `get_duplicate_clusters`, `get_bursts`, `get_burst_images`, `failed_images`, `live_video`, `low_confidence_faces`, `stats` |
| People | `get_persons`, `get_person`, `rename_person(person_id, new_name, confirm_faces=False)`, `name_face`, `get_person_faces`, `get_unassigned_faces`, `assign_face`, `create_person`, `merge_persons`, `confirm_person`, `unlock_face` |
| Saved searches | `save_search`, `list_saved_searches`, `run_saved_search`, `delete_saved_search` |
| Marks and dates | `set_mark`, `clear_mark`, `get_marks`, `suspicious_dates`, `set_date_override`, `clear_date_override`, `moves` |
| Files and cache | `check_files`, `forget_missing`, `thumbnail`, `cache_info`, `clear_cache`, `maintenance`, `repair` |
| Environment | `doctor`, `export_diagnostics`, `api_version` |

`find` filters: text, min_faces, max_faces, taken_from, taken_until, group_id,
path_contains, place_contains, content_type, kind, format, min_quality, burst_id, in_burst,
duplicate (none/any/exact/near), mark, no_mark, include_missing, include_live_video,
include_hidden. `sort`: date, date_desc, quality, path, size.
Faces are boxes in full-resolution pixels with a per-image label. Locked faces (`locked: 1` in face rows) are user decisions and are never changed by rebuilds.

## Child-process runner (JSON lines on stdout, UTF-8)
```
photo_engine.exe version
photo_engine.exe doctor --workspace W [--input D]
photo_engine.exe run --workspace W --input D [--profile gentle] [--retry-failed]
photo_engine.exe diagnostics --workspace W
```
Lines: `{"type":"progress",...}`, `{"type":"done",...}`, `{"type":"doctor",...}`,
`{"type":"version",...}`, `{"type":"diagnostics","path":...}`, `{"type":"error","code":...}`.
Write `cancel`, `pause` or `resume` + newline to stdin. Exit code: 0 ok, 1 error, 130 cancelled.
