"""Do YuNet and InsightFace landmarks give matching SFace embeddings?
python tools/check_landmarks.py photo.jpg   (expect similarity > 0.8)"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memoframe_engine.core.config import SFACE_SHA256, SFACE_URL, Settings  # noqa: E402
from memoframe_engine.domains.face.detector import create_detector  # noqa: E402
from memoframe_engine.domains.face.processor import _to_decoded  # noqa: E402
from memoframe_engine.domains.face.recognizer import FaceRecognizerSF  # noqa: E402
from memoframe_engine.domains.media.loader import load_image  # noqa: E402
from memoframe_engine.utils.model_downloader import ensure_model  # noqa: E402


def main(photo: str) -> int:
    base = Settings(workspace=Path("ws_bench").resolve())
    ensure_model(base.yunet_path)
    ensure_model(base.sface_path, SFACE_URL, SFACE_SHA256)
    rec = FaceRecognizerSF(base.sface_path)
    loaded = load_image(Path(photo), base.max_detect_side)
    bgr, vecs = loaded.to_bgr(), {}
    for backend in ("yunet", "insightface"):
        det = create_detector(base.with_overrides(detector_backend=backend))
        faces = det.detect(loaded)
        if not faces:
            print(f"{backend}: no face found")
            return 1
        face = max(faces, key=lambda f: f.area)
        blob = rec.embed_face(bgr, _to_decoded(face, loaded.scale))
        if blob is None:
            print(f"{backend}: no embedding (landmarks missing)")
            return 1
        vecs[backend] = np.frombuffer(blob, dtype=np.float32)
    sim = float(vecs["yunet"] @ vecs["insightface"])
    print(f"cosine similarity yunet vs insightface: {sim:.3f}")
    return 0 if sim > 0.8 else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
