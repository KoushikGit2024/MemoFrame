"""Accuracy on YOUR labelled data (I cannot supply labels).

  detector:   python tools/bench_accuracy.py detector --folder F --labels labels.json [--iou 0.4]
      labels.json: {"img1.jpg": [[x, y, w, h], ...], "img2.jpg": []}   (full-resolution pixels)
  duplicates: python tools/bench_accuracy.py duplicates --folder F --truth truth.json
      truth.json:  {"clusters": [["a.jpg", "a_copy.jpg"], ["b.jpg", "b_resized.jpg", "b.png"]]}
      Every other image in the folder is treated as unique.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Settings                                # noqa: E402
from services.intelligence.analysis import compute_dhash                    # noqa: E402
from services.organization.duplicates import find_duplicates        # noqa: E402
from services.face.detector import create_detector             # noqa: E402
from services.vision.loader import load_image                   # noqa: E402
from services.organization.similarity import compute_phash            # noqa: E402
from utils.model_downloader import ensure_model            # noqa: E402


def iou(a, b) -> float:
    iw = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    ih = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    inter = max(0, iw) * max(0, ih)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0


def ratio(a: int, b: int) -> float:
    return a / b if b else float("nan")


def detector(args) -> None:
    s = Settings(workspace=Path("ws_bench"))
    ensure_model(s.yunet_path)
    det = create_detector(s)
    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    tp = fp = fn = 0
    for name, truth in labels.items():
        found = det.detect(load_image(Path(args.folder) / name, s.max_detect_side))
        open_truth = list(range(len(truth)))
        for f in found:
            best, best_iou = None, args.iou
            for j in open_truth:
                v = iou((f.x, f.y, f.w, f.h), truth[j])
                if v >= best_iou:
                    best, best_iou = j, v
            if best is None:
                fp += 1
            else:
                tp += 1
                open_truth.remove(best)
        fn += len(open_truth)
    print(f"images={len(labels)} true_faces={tp + fn} detected_ok={tp} missed={fn} false_alarms={fp}")
    print(f"recall={ratio(tp, tp + fn):.3f} precision={ratio(tp, tp + fp):.3f} "
          f"(IoU>={args.iou}, confidence>={s.confidence_threshold})")


def duplicates(args) -> None:
    s = Settings(workspace=Path("ws_bench"))
    folder = Path(args.folder)
    truth = json.loads(Path(args.truth).read_text(encoding="utf-8"))["clusters"]
    records, names = [], {}
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in s.extensions)
    for i, p in enumerate(files, start=1):
        li = load_image(p, s.max_detect_side)
        records.append((i, hashlib.sha256(p.read_bytes()).hexdigest(),
                        compute_phash(li.pil), compute_dhash(li.pil)))
        names[i] = p.name
    rows = find_duplicates(records, s.phash_near_threshold, s.dhash_confirm_threshold)
    clusters: dict[int, list[str]] = {}
    for image_id, cid, _ in rows:
        clusters.setdefault(cid, []).append(names[image_id])
    pairs = lambda groups: {frozenset(p) for g in groups for p in itertools.combinations(sorted(g), 2)}
    want, got = pairs(truth), pairs(clusters.values())
    tp = len(want & got)
    print(f"images={len(files)} true_pairs={len(want)} found_pairs={len(got)} correct={tp}")
    print(f"pair recall={ratio(tp, len(want)):.3f} pair precision={ratio(tp, len(got)):.3f}")
    for pair in sorted(map(sorted, got - want))[:10]:
        print("  false pair:", pair)
    for pair in sorted(map(sorted, want - got))[:10]:
        print("  missed pair:", pair)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detector")
    d.add_argument("--folder", required=True)
    d.add_argument("--labels", required=True)
    d.add_argument("--iou", type=float, default=0.4)
    u = sub.add_parser("duplicates")
    u.add_argument("--folder", required=True)
    u.add_argument("--truth", required=True)
    a = ap.parse_args()
    (detector if a.cmd == "detector" else duplicates)(a)
