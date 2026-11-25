"""Exact and near-duplicate detection (pure functions, no database access).

Exact: identical SHA-256. Near: perceptual-hash Hamming distance <= threshold.
Candidates come from multi-index hashing: the 64-bit hash is split into
``threshold + 1`` bands, and by the pigeonhole principle any two hashes within
the threshold must be identical on at least one band, so no pair is missed.
Clusters are merged transitively (union-find), so a cluster can chain
A~B~C even if A and C differ by more than the threshold.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

from services.organization.similarity import PHASH_BITS, parse_phash

MAX_THRESHOLD = 16
_MAX_BLOCK_CELLS = 4_000_000  # caps memory of one comparison block
_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


class UnionFind:
    """Disjoint sets with path halving and union by size."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.size = [1] * n

    def find(self, i: int) -> int:
        parent = self.parent
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]


def _popcount(x: np.ndarray) -> np.ndarray:
    """Per-element bit count of a contiguous uint64 array."""
    return _POPCOUNT[x.view(np.uint8)].reshape(*x.shape, 8).sum(axis=-1)


def _near_pairs(values: np.ndarray, threshold: int) -> Iterator[tuple[int, int]]:
    """Yield index pairs ``(i, j)``, i < j, of ``values`` within ``threshold`` bits."""
    bands = threshold + 1
    edges = np.linspace(0, PHASH_BITS, bands + 1).astype(int)
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = np.uint64((1 << int(hi - lo)) - 1)
        keys = (values >> np.uint64(lo)) & mask
        order = np.argsort(keys, kind="stable")
        sorted_keys = keys[order]
        cuts = np.flatnonzero(np.diff(sorted_keys)) + 1
        for bucket in np.split(order, cuts):
            m = len(bucket)
            if m < 2:
                continue
            h = values[bucket]
            block = max(1, _MAX_BLOCK_CELLS // m)
            for start in range(0, m, block):
                xor = h[start : start + block, None] ^ h[None, :]
                rows, cols = np.nonzero(_popcount(xor) <= threshold)
                rows = rows + start
                keep = cols > rows
                for r, c in zip(rows[keep], cols[keep]):
                    yield int(bucket[r]), int(bucket[c])


def find_duplicates(
    records: Iterable[Sequence[Any]],
    near_threshold: int = 6,
    dhash_threshold: int | None = None,
) -> list[tuple[int, int, str]]:
    """Cluster duplicates.

    Args:
        records: ``(image_id, sha256, phash_hex[, dhash_hex])`` per image.
        near_threshold: max pHash Hamming distance (0-16).
        dhash_threshold: if set, a pHash match is kept only when the dHash distance is
            at most this (missing dHash never vetoes; 64 disables the check).

    Returns ``(image_id, cluster_id, kind)`` rows for clusters of two or more.
    """
    if not 0 <= near_threshold <= MAX_THRESHOLD:
        raise ValueError(f"near_threshold must be between 0 and {MAX_THRESHOLD}")
    recs: list[tuple[int, str | None, str | None, int | None]] = [
        (
            int(r[0]),  # type: ignore[arg-type]
            str(r[1]) if r[1] is not None else None,
            str(r[2]) if r[2] is not None else None,
            parse_phash(str(r[3])) if len(r) > 3 and r[3] is not None else None,
        )
        for r in records
    ]
    uf = UnionFind(len(recs))

    def agree(i: int, j: int) -> bool:
        if dhash_threshold is None:
            return True
        a, b = recs[i][3], recs[j][3]
        return a is None or b is None or (a ^ b).bit_count() <= dhash_threshold

    first_by_sha: dict[str, int] = {}
    first_by_hash: dict[int, int] = {}
    for idx, (_, sha, phash, _) in enumerate(recs):
        if sha:
            other = first_by_sha.setdefault(sha, idx)
            if other != idx:
                uf.union(other, idx)
        value = parse_phash(phash)
        if value is not None:
            other = first_by_hash.setdefault(value, idx)
            if other != idx and agree(other, idx):
                uf.union(other, idx)

    if near_threshold > 0 and len(first_by_hash) > 1:
        values = np.array(list(first_by_hash.keys()), dtype=np.uint64)
        reps = list(first_by_hash.values())
        for a, b in _near_pairs(values, near_threshold):
            if agree(reps[a], reps[b]):
                uf.union(reps[a], reps[b])

    components: dict[int, list[int]] = {}
    for idx in range(len(recs)):
        components.setdefault(uf.find(idx), []).append(idx)
    clusters = [sorted(recs[i][0] for i in m) for m in components.values() if len(m) > 1]
    clusters.sort(key=lambda ids: ids[0])

    sha_of = {image_id: sha for image_id, sha, _, _ in recs}
    rows: list[tuple[int, int, str]] = []
    for cluster_id, ids in enumerate(clusters, start=1):
        shas = {sha_of[i] for i in ids}
        kind = "exact" if len(shas) == 1 and None not in shas else "near"
        rows.extend((image_id, cluster_id, kind) for image_id in ids)
    return rows


def choose_keeper(members: Sequence[Any]) -> int:
    """Suggest which member to keep: highest quality, then most pixels, then largest
    file, then lowest id. ``quality`` is optional (treated as 0 when absent). Accepts
    mappings or sqlite3.Row objects."""

    def get_val(m: Any, key: str) -> Any:
        try:
            return m[key]
        except (KeyError, IndexError, TypeError):
            return None

    def quality(m: Any) -> int:
        try:
            val = get_val(m, "quality")
            return round(float(val)) if val is not None else 0
        except (TypeError, ValueError):
            return 0

    def rank(m: Any) -> tuple[int, int, int, int]:
        w_val = get_val(m, "width")
        h_val = get_val(m, "height")
        s_val = get_val(m, "size")
        w = int(w_val) if w_val is not None else 0
        h = int(h_val) if h_val is not None else 0
        size = int(s_val) if s_val is not None else 0
        img_id = int(m["id"])
        return (-quality(m), -(w * h), -size, img_id)

    return int(min(members, key=rank)["id"])
