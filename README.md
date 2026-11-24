# MemoFrame

An offline-first, local photo organization and face clustering application built in Python.

MemoFrame turns unorganized photo folders into a structured, searchable local library with **offline face clustering and person recognition as its core feature**. It identifies individuals across your collection, groups their photos together, detects duplicates, clusters events, and lets you browse, filter, and rename people—**entirely on your own machine with zero cloud uploads**.

---

## Key Features

### 👤 Offline Face Recognition & Person Clustering (Core Feature)
- **Automatic Identity Matching**: Uses OpenCV's official **YuNet** detector paired with **SFace** (`cv2.FaceRecognizerSF`) to align face crops and extract 128-dimensional biometric embeddings.
- **DBSCAN Cosine Clustering**: Unsupervised clustering groups all appearances of the same person across thousands of photos into distinct individual profiles (`Person 01`, `Person 02`...).
- **Interactive Person Renaming**: Assign real names (e.g. "Alice", "Dad") to person clusters; user names are permanently preserved across future incremental rescans.
- **Face Navigation & Filtering**: Filter your photo library to instantly show all photos containing a specific person, solo portraits, or group photos with 2+ people.
- **Bounding Boxes & Face Avatars**: Renders detected face bounding boxes on thumbnails and generates individual circular face crops for person avatars.

### ⚡ On-Demand Offline Ingestion & Safety
- **No Background Polling / Daemons**: Strictly offline and on-demand. When you trigger a scan, it processes only new and modified files and terminates cleanly—zero lingering background CPU or battery drain.
- **Read-Only Guarantee**: Your original photos are **never** modified, renamed, moved, or deleted. All thumbnails, face crops, and SQLite databases live inside your isolated workspace.
- **Zero Heavy External Dependencies**: Built on standard libraries and OpenCV; no external cloud APIs or heavyweight frameworks needed.

### 🔍 Smart Organization, Duplicates & Search
- **Exact & Near-Duplicate Clustering**: Identifies identical photos via SHA-256 and similar/near-duplicate shots via DCT perceptual hashing (pHash) and dHash with transitive clustering.
- **Burst Detection & Best Shot**: Groups rapid burst shots and automatically identifies the sharpest image.
- **Event & Spatiotemporal Timeline**: Clusters photos into chronological events based on timestamps, reverse geocoded places (offline city/country lookup), and visual similarity.
- **Full-Text Search (SQLite FTS5)**: Search by year, month, city, country, tags, duplicate status, and person names.

---

## Architecture & Project Structure

The engine uses a modern `src/` layout:

```text
MemoFrame/
├── main.py                     # Root CLI entry point
├── src/
│   └── memoframe/
│       ├── config.py           # Application settings, paths, and model configs
│       ├── cli.py              # Command-line interface definitions
│       ├── core/               # Pure algorithms & processing modules
│       │   ├── face_detector.py      # YuNet & InsightFace face detection
│       │   ├── face_recognizer.py    # SFace 128-d face embedding extractor
│       │   ├── face_clusterer.py     # DBSCAN cosine face clustering
│       │   ├── duplicate_detector.py # pHash / dHash multi-index duplicate clustering
│       │   ├── image_loader.py       # Robust image decoding & EXIF auto-rotation
│       │   ├── metadata_extractor.py # EXIF timestamps, GPS, camera metadata
│       │   └── video_info.py         # Fast MP4/MOV header parser & poster extraction
│       ├── database/           # SQLite persistence layer (schema v8 with WAL mode)
│       │   ├── schema.sql            # Table definitions (images, faces, persons, groups)
│       │   ├── migrations.py         # Versioned schema migrations
│       │   └── db_manager.py         # Thread-safe database operations & FTS5 queries
│       ├── engine/             # High-level Engine API & exclusive workspace lock
│       │   ├── api.py                # Public Python SDK (Engine.find, Engine.rescan, etc.)
│       │   └── lock.py               # Cross-process workspace file locking
│       ├── processing/         # Pipeline stages & multiprocessing workers
│       │   ├── pipeline.py           # Master 8-stage ingestion pipeline
│       │   └── face_processor.py     # Face cropping, annotation & embedding computation
│       └── utils/              # Logging, system info, and model downloader
├── tests/                      # Full pytest test suite (194 tests)
└── workspace/                  # Default user workspace (database, models, thumbnails)
```

---

## 8-Stage Ingestion Pipeline

When scanning or rescanning, MemoFrame processes photos through 8 distinct, fault-tolerant offline stages:

1. **Directory Scan & Metadata Check (`scan`)**: Fast non-blocking walk finding new/modified files.
2. **Analysis & Face Detection (`process`)**: EXIF, blur score, color palette, YuNet face detection & SFace alignment.
3. **Duplicate Clustering (`duplicates`)**: Exact SHA-256 and perceptual hash (pHash/dHash) grouping.
4. **Offline Reverse Geocoding (`places`)**: Maps GPS coordinates to nearest city and country offline.
5. **Burst Identification & Best Shot (`bursts`)**: Temporal shot clustering and sharpness scoring.
6. **Event & Timeline Grouping (`groups`)**: Spatiotemporal and visual timeline grouping.
7. **Face Recognition & Person Clustering (`persons`)**: DBSCAN cosine clustering into named/unnamed person profiles.
8. **Search Index Update (`index`)**: SQLite FTS5 full-text indexing.

---

## Command Line Usage

### 1. Ingest & Organize a Photo Folder
```powershell
python main.py process --input "D:\Photos"
```
Scans `D:\Photos`, runs face detection and recognition, clusters people, finds duplicates, and builds event groups.

### 2. On-Demand Incremental Rescan
```powershell
python main.py rescan
```
Discovers any newly added or modified photos across all known source folders, updates face clusters and groups, and immediately terminates.

### 3. Search & Query Photos
```powershell
# Find photos with 2 or more people
python main.py search --min-faces 2

# Search by date range and location
python main.py search --from 2024-01-01 --until 2024-12-31 --path "Vacation"
```

### 4. Duplicate Check & Reporting
```powershell
# List duplicate clusters and suggested keepers
python main.py duplicates

# Generate comprehensive JSON and CSV statistics
python main.py report
```

---

## Offline Face Models

The engine downloads OpenCV Zoo models automatically into `workspace/models/` on first use, and functions completely offline thereafter:

- **YuNet** (`face_detection_yunet_2023mar.onnx`): High-speed face detection (~230 KB).
- **SFace** (`face_recognition_sface_2021dec.onnx`): 128-dimensional facial recognition & identity embedding (~38 MB).

---

## Testing

Run the full automated test suite:

```powershell
pytest
```
*Current test suite: 194 passed, 1 skipped.*

---

## Privacy & Guarantees

1. **100% Local**: No images, thumbnails, face crops, or biometric embeddings ever leave your device.
2. **Read-Only**: Original photos are never modified or written to.
3. **No Background Daemons**: MemoFrame only runs when you ask it to. Zero background battery or CPU drain.
