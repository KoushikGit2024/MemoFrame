"""Time a run on a sample folder.

python tools/sample_run.py "D:\\sample500" --workspace ws_sample --workers 1
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memoframe_engine.core.config import Settings  # noqa: E402
from memoframe_engine.db import DatabaseManager  # noqa: E402
from memoframe_engine.domains.pipeline.orchestrator import run_pipeline  # noqa: E402


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--workspace", type=Path, default=Path("ws_sample"))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--target", type=int, default=15000, help="library size to extrapolate to")
    args = ap.parse_args()

    s = Settings(
        workspace=args.workspace.resolve(),
        workers=args.workers,
        save_annotated=False,
        save_face_crops=False,
    )
    start = time.perf_counter()
    with DatabaseManager(s.db_path) as db:
        run_pipeline(s, db, args.input.resolve())
        stats = db.report_stats()
    secs = time.perf_counter() - start
    n = max(1, stats["processed"])
    size_mb = dir_size(s.workspace) / 1e6
    print(f"\nprocessed={stats['processed']} failed={stats['failed']} faces={stats['total_faces']}")
    print(f"time={secs:.0f}s  per_image={secs / n:.2f}s  workspace={size_mb:.0f} MB")
    print(
        f"extrapolated to {args.target} photos: "
        f"{secs / n * args.target / 3600:.1f} h, {size_mb / n * args.target:.0f} MB"
    )
    print("Peak memory: watch Task Manager > Details (python.exe rows) while it runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
