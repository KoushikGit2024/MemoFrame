"""Synthetic 100k-record database: time the queries the app will run.

    python tools/bench_db.py --count 100000
"""
from __future__ import annotations

import argparse
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Settings                       # noqa: E402
from database import DatabaseManager              # noqa: E402
from services.pipeline.orchestrator import update_duplicates, update_groups  # noqa: E402


def timed(label, fn):
    t = time.perf_counter()
    out = fn()
    print(f"{label:28} {time.perf_counter() - t:7.2f}s")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100_000)
    n = ap.parse_args().count
    rng = random.Random(1)
    base = datetime(2020, 1, 1)
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(workspace=Path(tmp))
        with DatabaseManager(s.db_path) as db:
            timed("register", lambda: db.register_files((f"D:/p/{i}.jpg", 1000 + i, i) for i in range(n)))
            for start in range(0, n, 5000):
                rows = [{"image_id": i + 1, "width": 4000, "height": 3000, "sha256": f"{i:064x}",
                         "phash": f"{rng.getrandbits(64):016x}", "ts_source": "exif_original",
                         "exif_ts": (base + timedelta(minutes=i * 7)).strftime("%Y-%m-%dT%H:%M:%S"),
                         "faces": [{"x": 1, "y": 1, "w": 50, "h": 50, "confidence": 0.9}] * (i % 3)}
                        for i in range(start, min(n, start + 5000))]
                db.save_results(rows)
            print(f"rows saved: {n}")
            timed("search (faces>=2, 50)", lambda: db.search_images(min_faces=2, limit=50))
            timed("search (date range)", lambda: db.search_images(taken_from="2021-01-01", taken_until="2021-01-31"))
            timed("duplicates (full)", lambda: update_duplicates(s, db, force=True))
            timed("duplicates (skipped)", lambda: update_duplicates(s, db))
            timed("groups (full)", lambda: update_groups(s, db, force=True))
            timed("report_stats", db.report_stats)
            timed("analyze", db.analyze)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
