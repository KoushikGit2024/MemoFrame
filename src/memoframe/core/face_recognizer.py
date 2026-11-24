"""SFace face recognition embedding extractor (cv2.FaceRecognizerSF).

Companion to YuNet. Extracts 128-dimensional L2-normalized float32 feature
vectors used for person clustering and face matching across photos.
"""
from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np

from memoframe.utils.logger import get_logger

log = get_logger("core.face_recognizer")


class FaceRecognizerSF:
    """Wrapper around cv2.FaceRecognizerSF for robust feature extraction."""

    def __init__(self, model_path: Path, use_gpu: bool = False) -> None:
        self.model_path = model_path
        self._recognizer = self._create(use_gpu)

    def _create(self, use_gpu: bool):
        attempts = [(cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)]
        if use_gpu:
            attempts.insert(0, (cv2.dnn.DNN_BACKEND_CUDA, cv2.dnn.DNN_TARGET_CUDA))
        
        data = np.frombuffer(self.model_path.read_bytes(), dtype=np.uint8)
        last_error = None
        for backend, target in attempts:
            creators = (
                lambda: cv2.FaceRecognizerSF.create("onnx", data, np.empty(0, np.uint8), backend, target),
                lambda: cv2.FaceRecognizerSF.create(str(self.model_path), "", backend, target),
            )
            for create in creators:
                try:
                    return create()
                except (cv2.error, TypeError) as exc:
                    last_error = exc
        raise RuntimeError(f"Could not initialize SFace recognizer: {last_error}")

    def extract_feature(self, bgr_img: np.ndarray, face_row: np.ndarray) -> bytes | None:
        """Align face crop and extract 128-d L2-normalized embedding bytes.

        face_row: 15-element array from YuNet [x, y, w, h, x1, y1, ... x5, y5, score]
        Returns 512 bytes (float32 array of shape (128,)), or None on failure.
        """
        try:
            aligned = self._recognizer.alignCrop(bgr_img, face_row)
            if aligned is None or aligned.size == 0:
                return None
            feat = self._recognizer.feature(aligned)
            if feat is None:
                return None
            # feat shape is (1, 128), float32
            feat_arr = np.ascontiguousarray(feat.reshape(-1), dtype=np.float32)
            # L2 normalize
            norm = np.linalg.norm(feat_arr)
            if norm > 0:
                feat_arr = feat_arr / norm
            return feat_arr.tobytes()
        except Exception as exc:
            log.debug("Face feature extraction failed: %s", exc)
            return None
