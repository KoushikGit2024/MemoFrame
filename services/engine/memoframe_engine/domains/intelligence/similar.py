"""'Find similar' from stored whole-image embeddings (brute force, chunked)."""

from __future__ import annotations

import numpy as np

from memoframe_engine.db import DatabaseManager


def find_similar(db: DatabaseManager, image_id: int, limit: int = 20) -> list[tuple[int, float]]:
    """``[(image_id, cosine_similarity), ...]`` best first. Hidden, missing and Live-video rows are skipped.

    Raises:
        ValueError: the photo has no stored embedding.
    """
    q = db.get_embedding(image_id)
    if q is None:
        raise ValueError(
            "This photo has no stored embedding. Turn on store_embeddings and run tagging."
        )
    query = np.frombuffer(q["vec"], dtype=np.float16).astype(np.float32)
    query /= np.linalg.norm(query) or 1.0
    best: list[tuple[float, int]] = []
    after = 0
    while True:
        rows = db.embedding_rows(q["model"], after, 5000)
        if not rows:
            break
        after = int(rows[-1]["image_id"])
        mat = np.stack([np.frombuffer(r["vec"], dtype=np.float16) for r in rows]).astype(np.float32)
        norms = np.linalg.norm(mat, axis=1)
        norms[norms == 0] = 1.0
        scores = (mat / norms[:, None]) @ query
        best.extend(
            (float(s), int(r["image_id"]))
            for s, r in zip(scores, rows)
            if int(r["image_id"]) != image_id
        )
        best.sort(reverse=True)
        del best[limit:]
    return [(i, s) for s, i in best]
