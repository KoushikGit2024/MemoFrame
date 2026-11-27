"""Format checker: measure decode times and compare pHash across formats.

Usage:
    python tools/check_formats.py <folder_with_photos>
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from memoframe_engine.domains.media.loader import load_image_bytes  # noqa: E402
from memoframe_engine.domains.organization.similarity import compute_phash, hamming  # noqa: E402


def check_folder(folder: Path) -> int:
    files = [p for p in folder.rglob("*") if p.is_file() and not p.name.startswith(".")]
    if not files:
        print(f"No files found under {folder}")
        return 1

    by_stem: dict[str, list[Path]] = {}
    for f in files:
        by_stem.setdefault(f.stem.lower(), []).append(f)

    pairs = [paths for paths in by_stem.values() if len(paths) >= 2]
    print(f"Found {len(files)} files, {len(pairs)} candidate pairs with matching stem.")

    for paths in pairs:
        print(f"\n--- Pair: {paths[0].stem} ---")
        hashes = {}
        for p in paths:
            t0 = time.perf_counter()
            try:
                data = p.read_bytes()
                loaded = load_image_bytes(data, p.name, 1280)
                dt = (time.perf_counter() - t0) * 1000
                h = compute_phash(loaded.pil)
                hashes[p.name] = (h, dt, loaded.format)
                print(f"  {p.name:<30} fmt={loaded.format:<6} decode={dt:>6.1f}ms  phash={h}")
            except Exception as exc:
                print(f"  {p.name:<30} FAILED: {exc}")

        names = list(hashes.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                d = hamming(hashes[names[i]][0], hashes[names[j]][0])
                print(f"    Distance({names[i]} <-> {names[j]}): {d} bits")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check format decoding and pHash distances")
    parser.add_argument("folder", type=Path, help="Folder containing images to check")
    args = parser.parse_args()
    sys.exit(check_folder(args.folder))
