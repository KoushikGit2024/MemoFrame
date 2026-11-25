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

The project is organized into `backend` and `frontend`:

```text
MemoFrame/
├── backend/                    # Core organization and face clustering engine
│   ├── config.py               # Settings, model URLs, derived directories
│   ├── cli.py                  # CLI entry point (memoframe command)
│   ├── database/               # SQLite persistence, migrations, schema.sql
│   ├── engine/                 # Public Engine API, lock, contract, profiles
│   ├── services/               # Service modules
│   │   ├── face/               # YuNet detector, SFace recognizer, clustering
│   │   ├── intelligence/       # Scene tagger, reverse geocoding, quality
│   │   ├── organization/       # Duplicates, bursts, event grouper
│   │   ├── pipeline/           # Pipeline orchestrator, watcher, scanner
│   │   └── vision/             # Image/video decoding, thumbnails, metadata
│   ├── tests/                  # Backend pytest test suite
│   └── workspace/              # Default user workspace (database, models, thumbnails)
├── frontend/                   # Modern PyQt6 desktop application
│   ├── gui/                    # UI views (gallery, people, duplicates, timeline, settings)
│   ├── tests/                  # Frontend tests (test_gui.py)
│   ├── run_gui.py              # GUI launcher script
│   └── requirements.txt        # Frontend dependencies
└── README.md
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

Run commands from the `backend/` directory:

### 1. Ingest & Organize a Photo Folder
```powershell
python main.py scan --input "D:\Photos"
python main.py process
```
Or run the all-in-one pipeline:
```powershell
python main.py process --input "D:\Photos"   # scan + analyse in one go
```

### 2. On-Demand Incremental Rescan
```powershell
python cli.py rescan
```

### 3. Search & Query Photos
```powershell
# Find photos with 2 or more people
python cli.py search --min-faces 2

# Search by date range and location
python cli.py search --from 2024-01-01 --until 2024-12-31 --path "Vacation"
```

### 4. Duplicate Check & Reporting
```powershell
# List duplicate clusters and suggested keepers
python cli.py duplicates

# Generate comprehensive JSON and CSV statistics
python cli.py report
```

### 5. Desktop GUI
Run the graphical interface from the `frontend/` directory:
```powershell
python run_gui.py
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
