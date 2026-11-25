"""Benchmark scene tagging on real photos.

Reads each photo with cv2.imread, runs SceneTagger, and reports:
- inference time per photo (median and p95)
- top tags assigned
- failure count
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
from config import Settings  # noqa: E402
from services.intelligence.tagger import TaggerUnavailableError, create_tagger  # noqa: E402
from utils.file_utils import is_supported_image  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="folder of test photos")
    parser.add_argument("--workspace", type=Path, default=Path("workspace"),
                        help="workspace containing models/tagger/ (default: workspace)")
    parser.add_argument("--limit", type=int, default=50, help="max photos to benchmark (default 50)")
    args = parser.parse_args(argv)

    if not args.folder.is_dir():
        print(f"Error: {args.folder} is not a directory", file=sys.stderr)
        return 1

    settings = Settings(workspace=args.workspace.resolve(), tagging_enabled=True)
    try:
        tagger = create_tagger(settings)
    except TaggerUnavailableError as exc:
        print(f"Error: tagger not available: {exc}", file=sys.stderr)
        return 1

    files = [p for p in sorted(args.folder.rglob("*")) if is_supported_image(p)]
    if not files:
        print(f"No supported images found in {args.folder}")
        return 0

    files = files[:args.limit]
    print(f"Benchmarking {len(files)} photo(s)...")

    times: list[float] = []
    tag_counts: dict[str, int] = {}
    failed = 0

    for path in files:
        t0 = time.perf_counter()
        img = cv2.imread(str(path))
        if img is None:
            failed += 1
            continue
        tags, emb = tagger.tag(img)
        dt = (time.perf_counter() - t0) * 1000.0
        times.append(dt)
        for t in tags:
            tag_counts[t.label] = tag_counts.get(t.label, 0) + 1

    if not times:
        print(f"All {failed} image(s) failed to decode.")
        return 1

    times.sort()
    median = times[len(times) // 2]
    p95 = times[int(len(times) * 0.95)]

    print(f"\nResults ({len(times)} processed, {failed} failed):")
    print(f"  Median time: {median:.1f} ms / photo")
    print(f"  P95 time:    {p95:.1f} ms / photo")

    print("\nTop tags:")
    sorted_tags = sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    for label, count in sorted_tags:
        print(f"  {label:<20} {count:>3} photos")

    return 0


if __name__ == "__main__":
    sys.exit(main())
