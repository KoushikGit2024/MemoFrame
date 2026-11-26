"""Offline face clustering algorithm.

Uses DBSCAN with cosine distance over 128-dimensional normalized SFace embeddings
to group appearances of the same person across photographs without any internet access.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import DBSCAN

from utils.logger import get_logger

log = get_logger("core.face_clusterer")

# SFace cosine distance threshold (~0.36 distance <=> 0.64 cosine similarity)
# Faces within this cosine distance belong to the same person.
DEFAULT_COSINE_DISTANCE_EPS = 0.38
DEFAULT_MIN_SAMPLES = 2


def _unit(blob: bytes) -> np.ndarray | None:
    """128-d unit-length float32 vector from a 512-byte raw embedding."""
    if not blob or len(blob) != 512:
        return None
    v = np.frombuffer(blob, dtype=np.float32)
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else v


def attach_to_anchors(
    anchors: dict[int, list[bytes]],
    faces: list[tuple[int, bytes]],
    max_distance: float = DEFAULT_COSINE_DISTANCE_EPS,
    margin: float = 0.03,
) -> dict[int, list[int]]:
    """Give each free face to the person whose NEAREST confirmed face is within
    ``max_distance`` (cosine). Ambiguous faces (runner-up person within ``margin``
    similarity) are skipped and left for normal clustering.

    anchors: person_id -> embeddings of that person's locked faces.
    Returns person_id -> face_ids.
    """
    owners, vecs = [], []
    for pid, blobs in anchors.items():
        for blob in blobs:
            v = _unit(blob)
            if v is not None:
                owners.append(pid)
                vecs.append(v)
    cand = [(fid, v) for fid, blob in faces if (v := _unit(blob)) is not None]
    if not vecs or not cand:
        return {}
    matrix = np.stack(vecs).astype(np.float32)
    pids = sorted(set(owners))
    masks = [np.array([o == p for o in owners]) for p in pids]
    chunk = max(100, 4_000_000 // len(vecs))  # caps memory of one block
    out: dict[int, list[int]] = {}
    for start in range(0, len(cand), chunk):
        part = cand[start : start + chunk]
        sims = np.stack([v for _, v in part]) @ matrix.T  # (n, anchors)
        best = np.stack([sims[:, m].max(axis=1) for m in masks], axis=1)  # (n, people)
        order = np.argsort(-best, axis=1)
        for i, (fid, _) in enumerate(part):
            top = float(best[i, order[i, 0]])
            second = float(best[i, order[i, 1]]) if len(pids) > 1 else -1.0
            if 1.0 - top <= max_distance and (top - second) >= margin:
                out.setdefault(pids[int(order[i, 0])], []).append(fid)
    return out


def attach_faces(
    clusters: dict[int, list[int]],
    pool: list[tuple[int, bytes]],
    weak: list[tuple[int, bytes]],
    max_dist: float = DEFAULT_COSINE_DISTANCE_EPS,
) -> dict[int, list[int]]:
    """Greedily add weak faces to the nearest cluster centroid if within max_dist.

    Anti-chaining: centroids are computed ONLY from core pool faces, so weak
    faces never pull the centroid toward another person or chain two clusters.
    """
    if not clusters or not weak:
        return clusters

    emb_by_id = {fid: v for fid, b in pool if (v := _unit(b)) is not None}
    centroids: dict[int, np.ndarray] = {}
    for cidx, fids in clusters.items():
        vecs = [emb_by_id[f] for f in fids if f in emb_by_id]
        if vecs:
            c = np.mean(vecs, axis=0)
            norm = np.linalg.norm(c)
            centroids[cidx] = c / norm if norm > 0 else c

    if not centroids:
        return clusters

    c_keys = list(centroids.keys())
    C = np.array([centroids[k] for k in c_keys], dtype=np.float32)

    for fid, b in weak:
        v = _unit(b)
        if v is None:
            continue
        # Cosine distance = 1 - dot product (both unit vectors)
        dists = 1.0 - (C @ v)
        best_idx = int(np.argmin(dists))
        if dists[best_idx] <= max_dist:
            clusters[c_keys[best_idx]].append(fid)

    return clusters


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

    valid = [
        (fid, np.frombuffer(emb_bytes, dtype=np.float32))
        for fid, emb_bytes in face_records
        if emb_bytes and len(emb_bytes) == 512
    ]
    if not valid:
        return {}

    valid_face_ids = [fid for fid, _ in valid]
    X = np.stack([v for _, v in valid], axis=0).astype(np.float32)
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    X = np.where(norms > 0, X / norms, X)

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
