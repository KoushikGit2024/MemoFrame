"""Face DETECTION backends (boxes + confidence only).

No backend here computes, stores or compares face embeddings, so identifying
or matching people across photographs is not possible with this module.
Detectors are not thread-safe: create one per worker process.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np

from config import Settings
from services.vision.loader import LoadedImage
from models import FaceBox
from utils.logger import get_logger

log = get_logger("core.face_detector")

# (x, y, w, h, score) in the pixel space of the array that was analysed.
RawBox = tuple[float, float, float, float, float]


class DetectorUnavailableError(RuntimeError):
    """The requested backend (or its model file) cannot be used."""


class FaceDetector(ABC):
    """Common interface: ``detect(loaded_image) -> list[FaceBox]``."""

    name: str = "base"

    def __init__(self, confidence_threshold: float, min_face_px: int) -> None:
        self.confidence_threshold = confidence_threshold
        self.min_face_px = min_face_px

    @abstractmethod
    def _detect_bgr(self, bgr: np.ndarray) -> list[RawBox]:
        """Run the backend on a BGR uint8 array."""

    def detect(self, loaded: LoadedImage) -> list[FaceBox]:
        """Detect faces; boxes in FULL-resolution coordinates, left-to-right."""
        return self._finalize(self._detect_bgr(loaded.to_bgr()),
                              loaded.scale, loaded.width, loaded.height)

    def detect_tiled(self, loaded: LoadedImage, tile: int = 960, overlap: float = 0.25) -> list[FaceBox]:
        """Run the detector on overlapping tiles (finds small faces in large photos).

        ``loaded`` should be a LARGER decode than the normal pass (e.g. 3200 px).
        Duplicates from overlapping tiles are merged.
        """
        bgr = loaded.to_bgr()
        h, w = bgr.shape[:2]
        step = max(1, int(tile * (1 - overlap)))
        raw: list[RawBox] = []
        for y0 in _starts(h, tile, step):
            for x0 in _starts(w, tile, step):
                crop = np.ascontiguousarray(bgr[y0:y0 + tile, x0:x0 + tile])
                for x, y, bw, bh, s, *extra in self._detect_bgr(crop):
                    lm = (tuple(v + (x0 if i % 2 == 0 else y0) for i, v in enumerate(extra[0]))
                          if extra and extra[0] else None)
                    raw.append((x + x0, y + y0, bw, bh, s, lm))
        return merge_faces(self._finalize(raw, loaded.scale, loaded.width, loaded.height))

    def _finalize(self, raw: list[Any], scale: float, width: int, height: int) -> list[FaceBox]:
        boxes: list[FaceBox] = []
        for x, y, w, h, score, *extra in raw:
            if score < self.confidence_threshold:
                continue
            x0, y0 = max(0.0, x * scale), max(0.0, y * scale)
            x1, y1 = min(float(width), (x + w) * scale), min(float(height), (y + h) * scale)
            if (x1 - x0) < self.min_face_px or (y1 - y0) < self.min_face_px:
                continue
            lm = tuple(round(float(v) * scale, 2) for v in extra[0]) if extra and extra[0] else None
            boxes.append(FaceBox(x=int(round(x0)), y=int(round(y0)),
                                 w=int(round(x1 - x0)), h=int(round(y1 - y0)),
                                 confidence=round(float(score), 4), landmarks=lm))
        boxes.sort(key=lambda b: (b.x, b.y))
        return boxes

    def close(self) -> None:
        """Release backend resources (optional)."""


class YuNetDetector(FaceDetector):
    """OpenCV YuNet (``cv2.FaceDetectorYN``): small, fast, CPU-friendly."""

    name = "yunet"

    def __init__(
        self,
        model_path: Path,
        confidence_threshold: float = 0.7,
        nms_threshold: float = 0.3,
        min_face_px: int = 20,
        use_gpu: bool = False,
    ) -> None:
        super().__init__(confidence_threshold, min_face_px)
        if not hasattr(cv2, "FaceDetectorYN"):
            raise DetectorUnavailableError(
                "This OpenCV build has no FaceDetectorYN. Install opencv-python>=4.8."
            )
        if not model_path.is_file():
            raise DetectorUnavailableError(f"YuNet model not found: {model_path}")
        self._model_path = model_path
        self._conf, self._nms = confidence_threshold, nms_threshold
        self._detector = self._create(use_gpu)

    def _create(self, use_gpu: bool):
        attempts = [(cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)]
        if use_gpu:
            attempts.insert(0, (cv2.dnn.DNN_BACKEND_CUDA, cv2.dnn.DNN_TARGET_CUDA))
        last_error: Exception | None = None
        for backend, target in attempts:
            # Buffer overload first: cv2 cannot open non-ASCII Windows paths.
            data = np.frombuffer(self._model_path.read_bytes(), dtype=np.uint8)
            creators = (
                lambda: cv2.FaceDetectorYN.create(
                    "onnx", data, np.empty(0, np.uint8), (320, 320),
                    self._conf, self._nms, 5000, backend, target),
                lambda: cv2.FaceDetectorYN.create(
                    str(self._model_path), "", (320, 320),
                    self._conf, self._nms, 5000, backend, target),
            )
            for create in creators:
                try:
                    return create()
                except (cv2.error, TypeError) as exc:
                    last_error = exc
            if use_gpu and backend == cv2.dnn.DNN_BACKEND_CUDA:
                log.warning("CUDA backend unavailable, falling back to CPU.")
        raise DetectorUnavailableError(f"Could not create YuNet detector: {last_error}")

    def _detect_bgr(self, bgr: np.ndarray) -> list[RawBox]:
        h, w = bgr.shape[:2]
        try:
            self._detector.setInputSize((w, h))
            _, rows = self._detector.detect(bgr)
        except cv2.error as exc:
            log.warning("YuNet failed on a %dx%d image: %s", w, h, exc)
            return []
        if rows is None:
            return []
        # Row layout: x, y, w, h, 10 landmark values, score.
        return [(float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[14]),
                 tuple(float(v) for v in r[4:14])) for r in rows]


class InsightFaceDetector(FaceDetector):
    """Optional SCRFD detector via InsightFace (DETECTION module only)."""

    name = "insightface"

    def __init__(
        self,
        root: Path,
        confidence_threshold: float = 0.7,
        min_face_px: int = 20,
        use_gpu: bool = False,
    ) -> None:
        super().__init__(confidence_threshold, min_face_px)
        try:
            import importlib
            insightface_app = importlib.import_module("insightface.app")
            FaceAnalysis = getattr(insightface_app, "FaceAnalysis")
        except (ImportError, AttributeError) as exc:
            raise DetectorUnavailableError(
                "InsightFace backend needs: pip install insightface onnxruntime "
                "(on Windows this may require MSVC Build Tools)."
            ) from exc
        providers = ["CPUExecutionProvider"]
        if use_gpu:
            providers.insert(0, "CUDAExecutionProvider")
        root.mkdir(parents=True, exist_ok=True)
        # allowed_modules=["detection"]: the recognition model is never loaded.
        self._app = FaceAnalysis(
            name="buffalo_sc", root=str(root),
            allowed_modules=["detection"], providers=providers,
        )
        self._app.prepare(
            ctx_id=0 if use_gpu else -1,
            det_thresh=confidence_threshold,
            det_size=(640, 640),
        )

    def _detect_bgr(self, bgr: np.ndarray) -> list[RawBox]:
        try:
            faces = self._app.get(bgr)
        except Exception as exc:  # noqa: BLE001 - onnxruntime raises varied errors
            log.warning("InsightFace failed: %s", exc)
            return []
        out: list[RawBox] = []
        for f in faces:
            x1, y1, x2, y2 = (float(v) for v in f.bbox)
            out.append((x1, y1, x2 - x1, y2 - y1, float(f.det_score)))
        return out


def create_detector(settings: Settings) -> FaceDetector:
    """Build the backend named in ``settings.detector_backend``.

    The YuNet weights must already exist (the pipeline calls
    ``utils.model_downloader.ensure_model`` once in the parent process, which
    avoids download races between workers).
    """
    backend = settings.detector_backend.lower()
    if backend == "yunet":
        return YuNetDetector(
            settings.yunet_path,
            confidence_threshold=settings.confidence_threshold,
            nms_threshold=settings.nms_threshold,
            min_face_px=settings.min_face_px,
            use_gpu=settings.use_gpu,
        )
    if backend == "insightface":
        return InsightFaceDetector(
            settings.models_dir / "insightface",
            confidence_threshold=settings.confidence_threshold,
            min_face_px=settings.min_face_px,
            use_gpu=settings.use_gpu,
        )
    raise DetectorUnavailableError(
        f"Unknown detector backend {settings.detector_backend!r} (use 'yunet' or 'insightface')."
    )


def _starts(n: int, tile: int, step: int) -> list[int]:
    if n <= tile:
        return [0]
    return list(range(0, n - tile, step)) + [n - tile]


def merge_faces(faces: list[FaceBox], overlap: float = 0.6) -> list[FaceBox]:
    """Drop lower-confidence boxes that overlap a kept box (intersection / smaller area)."""
    kept: list[FaceBox] = []
    for f in sorted(faces, key=lambda b: -b.confidence):
        dup = False
        for k in kept:
            iw = min(f.x + f.w, k.x + k.w) - max(f.x, k.x)
            ih = min(f.y + f.h, k.y + k.h) - max(f.y, k.y)
            if iw > 0 and ih > 0 and iw * ih / max(1, min(f.area, k.area)) > overlap:
                dup = True
                break
        if not dup:
            kept.append(f)
    return sorted(kept, key=lambda b: (b.x, b.y))