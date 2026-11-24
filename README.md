# Local Photo Organizer

A command-line tool that organizes large photo collections **entirely on your own computer**:

- detects faces (boxes, confidence, per-image counts, thumbnails, annotated copies)
- finds exact and near-duplicate images
- groups photos into events using timestamps, EXIF/GPS and colour similarity
- stores everything in a local, searchable SQLite database

It does **not** recognise or match people. Faces are detected, never identified.

## Status

This code was written without being executed in the authoring environment. Run the test suite
and the end-to-end check below on your own machine before relying on it with a large collection.

## Privacy and safety

- **Everything runs locally.** No image, thumbnail or metadata is ever uploaded.
- **The only network access** is the one-time download of the face-detection model file
  (see [Model weights](#model-weights)). After that the tool works offline.
- **Originals are never modified, moved, copied or deleted.** They are opened read-only.
  All output goes to a separate workspace folder.
- **No biometric identity matching.** The detectors return boxes and confidence scores only.
  No face embeddings are computed or stored, and the database has no column for them.
  "Face 001", "Face 002" ... are positions within a single image (left to right). They say
  nothing about whether faces in different photos are the same person.
- Reported face counts are *detected faces*, not people.

## Requirements

- Python 3.11 or newer
- Windows 11 (also works on Linux and macOS)
- CPU only is fine; GPU is optional

## Installation

```powershell
cd photo_organizer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

For running the tests too: `pip install -r requirements-dev.txt`.

### Model weights

Face detection uses OpenCV's **YuNet** model (`face_detection_yunet_2023mar.onnx`, about 230 KB).
It is downloaded automatically into `workspace/models/` the first time `process` runs.

- Two values in `config.py` are unverified: `YUNET_URL`, which I could not confirm still
  resolves, and `YUNET_SHA256`, which is empty. With no hash pinned, the downloader checks
  only that the file has a plausible size, then logs the hash it computed. Paste that value into
  `YUNET_SHA256` to pin the file.
- **Offline or download fails?** The error message prints the URL and the exact destination.
  Download the file from the OpenCV Zoo (`opencv_zoo`, `models/face_detection_yunet`) on another
  machine and save it as `workspace/models/face_detection_yunet_2023mar.onnx`.

### Optional: InsightFace (SCRFD) backend

Not needed for normal use.

```powershell
pip install insightface onnxruntime
python main.py process --workspace workspace --backend insightface
```

- On Windows, `insightface` may need the Microsoft C++ Build Tools to install.
- On first use it downloads its `buffalo_sc` model pack (roughly 15 MB) into `workspace/models/insightface/`.
- Only the detection module is loaded. The pack also contains a recognition model file on disk, but this program never loads or calls it.

## Quick start

```powershell
python main.py process --input "D:\Photos"
python main.py report
```

`process --input` scans the folder, analyses every new or changed image, then rebuilds the
duplicate clusters and event groups. By default everything is written under `./workspace`.
Use `--workspace PATH` on any command to use a different location.

## Commands

Options such as `--workspace`, `-v` and `-q` go **after** the command name.

| Command | What it does |
|---|---|
| `scan --input DIR` | Find images recursively and register them. Unchanged files are skipped. |
| `process [--input DIR]` | Analyse all pending images. With `--input` it scans first; without it, it continues unfinished work (resume). Then rebuilds duplicates and groups. |
| `group` | Rebuild event groups from stored data (change grouping options without reprocessing). |
| `duplicates` | Recompute and list duplicate clusters, marking a suggested file to keep. Nothing is deleted. |
| `report` | Print statistics and write JSON/CSV reports. |
| `search` | Query processed images (see below). |
| `prune [--input DIR] [--dry-run] [--yes]` | Remove records (and generated thumbnails/crops) of photos that no longer exist on disk. Originals are never touched. With `--input`, only records under that folder are checked, and the folder must exist. |
| `reset` | Clear the database and generated files. |

### Useful options

```text
process:
  --workers N         worker processes (default: CPU count - 1, max 4)
  --batch-size N      images per database commit (default 64)
  --confidence X      face confidence threshold 0-1 (default 0.7)
  --min-face-px N     ignore faces smaller than N pixels (default 20)
  --backend NAME      yunet (default) or insightface
  --gpu               try GPU acceleration (falls back to CPU)
  --no-annotated      skip annotated copies
  --no-crops          skip face crops
  --retry-failed      re-queue images that failed earlier
  --near-threshold N  pHash Hamming distance for near duplicates, 0-16 (default 6)
  --event-gap-hours H new event after a gap longer than H hours (default 3)
  --gps-km K          new event after a GPS jump larger than K km; 0 disables (default 5)
  --visual-distance D colour distance for undated images (default 0.35)
  --min-group-size N  drop groups smaller than N (default 1)

duplicates:  --near-threshold N  --limit N (0 = all)  --no-recompute
report:      --no-files
reset:       --yes  --db-only
```

### Searching

```powershell
python main.py search --min-faces 2
python main.py search --from 2024-06-01 --until 2024-06-30 --path "Holiday"
python main.py search --group 7 --limit 100
```

Filters (`--min-faces`, `--max-faces`, `--from`, `--until`, `--group`, `--path`) are combined
with AND. Dates are `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`.

### Resuming and interrupting

Press **Ctrl+C** to stop cleanly: the current batch is saved and the command exits with
code 130. Run the same command again to continue. Each batch is committed atomically, so even
a hard kill loses at most one batch. Failed images stay failed until you run `process --retry-failed`.

### Exit codes

`0` success, `1` error (printed as `error: ...`; add `-v` for debug detail), `130` interrupted.

### What `reset` removes

It clears all database rows and the folders `thumbnails/`, `face_crops/`, `annotated/` and
`grouped_images/` inside the workspace. It keeps `models/`, `reports/` and the log file, and
never touches your photos. `--db-only` keeps the generated image files. It asks for
confirmation unless `--yes` is given.

## Output layout

```text
workspace/
├── photos.db              SQLite database (metadata only)
├── photo_organizer.log    rotating log
├── models/                downloaded model weights
├── thumbnails/            256 px thumbnails, sharded into 0000/, 0001/, ...
├── face_crops/            one crop per detected face
├── annotated/             copies (max 1600 px) with boxes and "Face 001 (0.93)" labels
├── grouped_images/        groups.csv: every group and its images (a list, not copies)
└── reports/               report_*.json, duplicates_*.csv, failed_*.csv
```

## How it works

1. **Scan.** Recursive, case-insensitive extension match (JPG, JPEG, PNG, WEBP, BMP, TIFF), with
   the workspace excluded. A `(size, mtime)` fingerprint decides whether a file is new, changed
   or unchanged. Only new and changed files are processed.
2. **Process (per image, decoded once).** Pillow decodes the file (large JPEGs are shrunk while
   decoding), applies EXIF rotation in memory, and downsizes it to at most 1280 px for detection.
   From that one decode it computes metadata, SHA-256, a 64-bit DCT perceptual hash, a colour
   histogram feature, face boxes and a thumbnail. Face crops are cut from a re-read of the
   full-resolution file, so they stay sharp. Corrupt files are recorded as `failed` and never
   stop the run.
3. **Duplicates.** Exact: identical SHA-256. Near: perceptual-hash Hamming distance up to the
   threshold, found with multi-index hashing (the hash is split into `threshold + 1` bands, so no
   qualifying pair is missed) and merged with union-find. Clusters are transitive.
4. **Grouping.** Photos with an EXIF date are sorted by time and split on gaps longer than the event
   gap, and on GPS jumps. Photos dated only by file modification time form separate "File date"
   events, because copying files changes that time. Undated photos are clustered by colour histogram
   (scikit-learn, average-linkage). Faces are never used.
5. **Persist.** The parent process is the only database writer (SQLite WAL mode), and one batch
   is one transaction.

### Project layout

```text
main.py, cli.py, config.py
core/        models, scanner, image_loader, metadata_extractor, face_detector,
             image_similarity, duplicate_detector       (no database access)
database/    schema.sql, db_manager.py
processing/  thumbnail_generator, face_processor, image_grouper, pipeline, reporter
utils/       logger, validators, file_utils, model_downloader
tests/       pytest suite
```

### Database tables

`images` (path, size, dimensions, SHA-256, pHash, EXIF timestamp and its source, GPS, colour
features, face count, status, error, group id), `faces` (box, confidence, label, crop path),
`groups`, `duplicates`. There is no face-embedding column.

## Testing

```powershell
pip install -r requirements-dev.txt
pytest                      # all tests
pytest -rs                  # also show why tests were skipped
pytest -x -vv               # stop at the first failure, full detail
```

Most tests use generated images and a fake detector, so they need no network, no model and no
photos. Two tests use the real YuNet detector and are skipped unless you provide the model and a
photo containing faces:

```powershell
$env:PHOTO_ORGANIZER_MODEL = "C:\path\to\face_detection_yunet_2023mar.onnx"
$env:PHOTO_ORGANIZER_TEST_IMAGE = "C:\path\to\group_photo.jpg"
$env:PHOTO_ORGANIZER_TEST_FACES = "3"
pytest tests/test_face_detector.py -rs
```

### End-to-end check on real photos

Use a copy of 10 to 30 photos, including one with faces and one duplicate:

```powershell
python main.py process --input "C:\path\to\test_photos" --workspace ws_test --workers 1
python main.py report --workspace ws_test
python main.py duplicates --workspace ws_test
python main.py search --workspace ws_test --min-faces 2
python main.py process --workspace ws_test          # should report 0 processed (resume check)
python main.py reset --workspace ws_test --yes
```

Then repeat with `--workers 2` and compare face counts with the single-worker run.

## Limitations

- **Face detection is imperfect.** Small, blurred, occluded, profile or heavily rotated faces can
  be missed, and non-faces can be detected. Tune with `--confidence` and `--min-face-px`.
- **Faces are not tracked across photos.** Counts are per image only. This is intentional.
- **Perceptual hashing is whole-image.** Crops, heavy edits and mirrored copies usually do not
  match. Flat images (for example black screens) hash identically and appear as duplicates.
  Clusters are transitive, so burst sequences can chain into one cluster. Review before deleting.
- **Timestamps.** EXIF times have no timezone and are stored as local time. File-modification times
  are less reliable and are grouped separately. Cameras with wrong clocks give wrong events.
- **Undated photos** are clustered by colour only, in windows of 2000 images, so those groups are
  rough.
- **Deleted source files stay in the database until you run `prune`.** `prune` only removes
  records and generated files. Edited files are reprocessed, but their old face crops may
  remain on disk until the image is pruned or you run `reset`.
- **Formats.** HEIC/HEIF is not supported. Animated files use their first frame. Images above
  Pillow's decompression-bomb limit are recorded as failed.
- **Windows multiprocessing** starts a full Python interpreter per worker (a few seconds each). For a
  few hundred photos, `--workers 1` can be faster.
- **Hard kills** (power loss, closing the terminal) lose at most one batch of work.

## Troubleshooting

| Problem | What to do |
|---|---|
| `Could not download the model` | Download the `.onnx` file manually (see [Model weights](#model-weights)). |
| `No database at ...` | Run `process --input DIR` first, or pass the same `--workspace` you used before. |
| `A worker process crashed` | Probably out of memory. Re-run with `--workers 1` or `--workers 2`. Progress is kept. |
| Images marked failed | See `report`. After fixing them, run `process --retry-failed`. |
| `InsightFace backend needs ...` | Install `insightface` and `onnxruntime`, or use the default `yunet` backend. |
| Anything else | Re-run with `-v` and check `workspace/photo_organizer.log`. |