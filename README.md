# MemoFrame

An offline-first, local photo organization, scene tagging, and face clustering desktop application.

MemoFrame turns unorganized photo folders into a structured, searchable local library with **offline face clustering, person recognition, and scene tagging**. It identifies individuals across your collection, groups their photos together, detects duplicates and bursts, clusters events, and lets you browse, filter, and manage people—**entirely on your own machine with zero cloud uploads**.

---

## Key Features

### 👤 Offline Face Recognition & Person Management
- **Automatic Identity Matching**: Uses OpenCV's **YuNet** detector paired with **SFace** (`cv2.FaceRecognizerSF`) to align face crops and extract 128-dimensional biometric embeddings.
- **DBSCAN Cosine Clustering**: Groups appearances of the same person across thousands of photos into distinct individual profiles (`Person 01`, `Person 02`...).
- **Interactive Person & Face Controls**:
  - Rename, merge, and confirm person clusters; user-assigned names and locks are preserved across future rescans.
  - **Unused Faces Tab**: Dedicated gallery tab showing photos with unassigned faces, automatically zoomed/cropped to the unidentified face.
  - **Default (Cover) Face Selection**: Set any person's default avatar directly from the Gallery grid (when a person is selected) or from the Lightbox.
  - **Discard False Detections ("Not a Face")**: Dismiss false-positive face detections from the Lightbox so they are excluded from clustering, counts, and Unused Faces.

### 🏷️ Always-On Offline Scene Tagging
- **Automatic Scene Classification**: Uses **MobileNetV2** (`scene_model.onnx`, 1000 ImageNet classes) to tag photos offline during ingestion and background tagging.
- **Clickable Tag Pills & Filtering**: View amber scene tags in the Lightbox sidebar and filter the gallery by any tag.

### 🖼️ Modern Gallery & Lightbox
- **Flexible Layouts**: Switch between **Grid**, **Compact**, and **Table** views, or override column count with the **Columns slider** and **Per-page** input.
- **Info Overlay Toggle**: Show or hide filename/date/quality overlays and face-count badges on square photo cards.
- **Face Zoom**: Crop gallery cards to the largest detected face (or target person/unassigned face).
- **Rich Lightbox**: Zoom/pan, face bounding-box management (name, assign with avatar dropdown, remove from person, discard, set default), date correction, live photo playback, and similar-photo search.

### 🔍 Smart Organization, Duplicates & Search
- **Exact & Near-Duplicate Clustering**: Identifies identical photos via SHA-256 and similar/near-duplicate shots via DCT perceptual hashing (pHash) and dHash.
- **Burst Detection & Best Shot**: Groups rapid burst shots and automatically identifies the sharpest image.
- **Event & Spatiotemporal Timeline**: Clusters photos into chronological events based on timestamps, offline reverse-geocoded places, and visual similarity.
- **Full-Text Search (SQLite FTS5)**: Search by filename, person, place, date, tags, duplicate status, and minimum face count.

---

## Architecture & Project Structure

```text
MemoFrame/
├── backend/                    # Core organization, tagging, and face clustering engine
│   ├── config.py               # Settings, model URLs, derived directories
│   ├── cli.py                  # CLI entry point
│   ├── database/               # SQLite persistence, migrations, schema.sql
│   ├── engine/                 # Public Engine API, lock, contract, profiles
│   ├── services/               # Service modules
│   │   ├── face/               # YuNet detector, SFace recognizer, clustering
│   │   ├── intelligence/       # Scene tagger, reverse geocoding, quality, similarity
│   │   ├── organization/       # Duplicates, bursts, event grouper, live pairs
│   │   ├── pipeline/           # Pipeline orchestrator, watcher, scanner
│   │   └── vision/             # Image/video decoding, thumbnails, metadata
│   └── tests/                  # Backend pytest test suite
├── bridge/                     # Python JSON-RPC bridge for the Electron frontend
│   ├── handlers_library.py     # Photo queries, decode, thumbnails
│   ├── handlers_people.py      # People & face management RPCs
│   ├── handlers_collections.py # Duplicates, bursts, timeline, saved searches
│   ├── handlers_system.py      # Scan, tagging, diagnostics, model downloads
│   └── tests/                  # Bridge handler & integration tests
├── frontElectron/              # Electron + React + TypeScript + Vite desktop app
│   ├── src/views/              # GalleryView, PeopleView, DuplicatesView, BurstsView, TimelineView, SettingsView
│   ├── src/components/         # PhotoCard, PeopleStrip, PhotoTable, etc.
│   └── src/modals/             # LightboxModal, LightboxSidebar, DateModals, UtilityModals
└── README.md
```

---

## Getting Started

### 1. Desktop App (`frontElectron/`)
```powershell
npm --prefix frontElectron install
npm --prefix frontElectron run build:web
npm --prefix frontElectron start
```

### 2. Command Line Usage (`backend/`)
```powershell
# Scan and process a photo folder
python main.py process --input "D:\Photos"

# On-demand incremental rescan
python cli.py rescan

# Search photos with 2+ faces
python cli.py search --min-faces 2

# List duplicate clusters
python cli.py duplicates
```

---

## Offline Models

Models are stored locally in `workspace/models/` and run 100% offline:
- **YuNet** (`face_detection_yunet_2023mar.onnx`): High-speed face detection.
- **SFace** (`face_recognition_sface_2021dec.onnx`): 128-dimensional facial recognition & identity embedding.
- **MobileNetV2** (`tags/scene_model.onnx` + `tags/scene_labels.txt`): Offline scene tagging.

---

## Testing & Verification

```powershell
# Frontend typecheck & production build
npm --prefix frontElectron run build:web

# Backend & bridge test suite
pytest backend bridge/tests -q
```
*Current test suite: 212 passed, 2 skipped.*

---

## Privacy & Guarantees

1. **100% Local**: No images, thumbnails, face crops, tags, or biometric embeddings ever leave your device.
2. **Read-Only**: Original photos are never modified, renamed, moved, or deleted.
3. **No Background Daemons**: Scans and model passes only run on demand.
