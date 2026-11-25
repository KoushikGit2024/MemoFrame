"""Tests for frontend face labeling and StageProgress calculation."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_DIR = REPO_ROOT / "backend"

for p in (FRONTEND_DIR, BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gui.face_labels import face_display_name
from gui.progress import StageProgress


def test_face_display_name_rules() -> None:
    # 1. Unlocked face -> None
    assert face_display_name({"locked": 0, "person_id": 1, "person_name": "Alice"}) is None
    assert face_display_name({"locked": None, "person_id": 1, "person_name": "Alice"}) is None

    # 2. No person_id -> None
    assert face_display_name({"locked": 1, "person_id": None, "person_name": "Alice"}) is None

    # 3. Default Person NN name -> None
    assert face_display_name({"locked": 1, "person_id": 1, "person_name": "Person 01"}) is None
    assert face_display_name({"locked": 1, "person_id": 1, "person_name": "Person 999"}) is None
    assert face_display_name({"locked": 1, "person_id": 1, "person_name": "person 42"}) is None

    # 4. Valid named person -> returns name
    assert face_display_name({"locked": 1, "person_id": 1, "person_name": "Alice"}) == "Alice"
    assert face_display_name({"locked": 1, "person_id": 1, "person_name": "Bob Smith"}) == "Bob Smith"


def test_stage_progress_calculation() -> None:
    prog = StageProgress()
    # 0.5 * 0.05 * 100 = 2.5% (round(2.5) in Python rounds to nearest even integer, which is 2)
    assert prog.update({"stage": "scan", "done": 50, "total": 100}) in (2, 3)
    assert prog.update({"stage": "detect", "done": 10, "total": 100}) >= 5
    
    # Progress never regresses
    p1 = prog.update({"stage": "detect", "done": 50, "total": 100})
    p2 = prog.update({"stage": "detect", "done": 40, "total": 100})
    assert p2 >= p1
