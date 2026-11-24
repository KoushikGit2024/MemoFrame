"""Offline face clustering algorithm.

Uses DBSCAN with cosine distance over 128-dimensional normalized SFace embeddings
to group appearances of the same person across photographs without any internet access.
"""
from __future__ import annotations

import numpy as np
from sklearn.cluster import DBSCAN

from memoframe.utils.logger import get_logger

log = get_logger("core.face_clusterer")

# SFace cosine distance threshold (~0.36 distance <=> 0.64 cosine similarity)
# Faces within this cosine distance belong to the same person.
DEFAULT_COSINE_DISTANCE_EPS = 0.38
DEFAULT_MIN_SAMPLES = 1


def cluster_face_embeddings(
    face_records: list[tuple[int, bytes]],
    eps: float = DEFAULT_COSINE_DISTANCE_EPS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> dict[int, list[int]]:
    """Cluster face embeddings into person groups.

    Args:
        face_records: list of (face_id, embedding_bytes)
        eps: maximum cosine distance between two samples for one to be considered as in the neighborhood
        min_samples: minimum faces to form a core person cluster

    Returns:
        dict mapping cluster_id (1-indexed) -> list of face_ids
    """
    if not face_records:
        return {}

    face_ids = [rec[0] for rec in face_records]
    vectors = []
    valid_face_ids = []

    for fid, emb_bytes in face_records:
        if not emb_bytes or len(emb_bytes) != 512:
            continue
        vec = np.frombuffer(emb_bytes, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        vectors.append(vec)
        valid_face_ids.append(fid)

    if not vectors:
        return {}

    X = np.array(vectors, dtype=np.float32)

    # DBSCAN with cosine metric
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
    labels = clustering.fit_predict(X)

    clusters: dict[int, list[int]] = {}
    noise_id = 100000

    for fid, label in zip(valid_face_ids, labels):
        if label == -1:
            # Unclustered outlier treated as individual singleton
            clusters[noise_id] = [fid]
            noise_id += 1
        else:
            cluster_id = int(label) + 1
            clusters.setdefault(cluster_id, []).append(fid)

    # Re-index clusters sequentially by size (largest person first)
    sorted_clusters = sorted(clusters.values(), key=len, reverse=True)
    reindexed: dict[int, list[int]] = {}
    for idx, fids in enumerate(sorted_clusters, start=1):
        reindexed[idx] = fids

    return reindexed
