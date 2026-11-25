"""100k-record search timings: python tools/bench_search.py --count 100000"""

from __future__ import annotations

import argparse
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Settings  # noqa: E402
from database import DatabaseManager  # noqa: E402
from services.pipeline.orchestrator import update_search_index  # noqa: E402


def timed(label, fn):
    t = time.perf_counter()
    out = fn()
    print(f"{label:30} {time.perf_counter() - t:7.3f}s")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100_000)
    args = ap.parse_args()
    n = args.count
    rng, base = random.Random(1), datetime(2020, 1, 1)
    places = ["Imphal, IN", "Delhi, IN", "London, GB", "Paris, FR", ""]
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(workspace=Path(tmp))
        with DatabaseManager(s.db_path) as db:
            db.register_files((f"D:/Photos/trip{i % 300}/IMG_{i:06d}.jpg", 1, i) for i in range(n))
            for start in range(0, n, 5000):
                db.save_results(
                    [
                        {
                            "image_id": i + 1,
                            "format": "JPEG",
                            "quality": rng.random() * 100,
                            "exif_ts": (base + timedelta(minutes=i * 7)).strftime(
                                "%Y-%m-%dT%H:%M:%S"
                            ),
                            "ts_source": "exif_original",
                        }
                        for i in range(start, min(n, start + 5000))
                    ]
                )
            db.set_places([(i + 1, rng.choice(places)) for i in range(n)])
            print("fts available:", db.ensure_fts())
            timed("index build", lambda: update_search_index(s, db, force=True))
            timed("text: trip42 june", lambda: db.find_images(text="trip42 june", limit=50))
            timed("text: imphal 2021", lambda: db.find_images(text="imphal 2021", limit=50))
            timed(
                "filters + sort quality",
                lambda: db.find_images(min_quality=90, sort="quality", limit=50),
            )
            timed("count (text)", lambda: db.count_images(text="london"))
            timed("timeline month", lambda: db.timeline("month"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
