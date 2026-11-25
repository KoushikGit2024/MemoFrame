"""Face biometric and identity service."""
from .clusterer import (
    DEFAULT_COSINE_DISTANCE_EPS,
    DEFAULT_MIN_SAMPLES,
    attach_faces,
    attach_to_anchors,
    cluster_face_embeddings,
)
from .detector import (
    FaceDetector,
    YuNetDetector,
    create_detector,
    merge_faces,
    DetectorUnavailableError,
)
from .processor import (
    assign_labels,
    draw_annotations,
    expand_box,
    process_faces,
)
from .recognizer import FaceRecognizerSF

__all__ = [
    "DEFAULT_COSINE_DISTANCE_EPS",
    "DEFAULT_MIN_SAMPLES",
    "attach_faces",
    "attach_to_anchors",
    "cluster_face_embeddings",
    "FaceDetector",
    "YuNetDetector",
    "create_detector",
    "merge_faces",
    "DetectorUnavailableError",
    "assign_labels",
    "draw_annotations",
    "expand_box",
    "process_faces",
    "FaceRecognizerSF",
]
