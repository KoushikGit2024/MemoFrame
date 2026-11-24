"""Exact and near-duplicate detection (pure functions, no database access).

Exact: identical SHA-256. Near: perceptual-hash Hamming distance <= threshold.
Candidates come from multi-index hashing: the 64-bit hash is split into
``threshold + 1`` bands, and by the pigeonhole principle any two hashes within
the threshold must be identical on at least one band, so no pair is missed.
Clusters are merged transitively (union-find), so a cluster can chain
A~B~C even if A and C differ by more than the threshold.
"""
from __future__ import annotations

from typing import Iterable, Iterator, Mapping, Sequence

import numpy as np

from core.image_similarity import PHASH_BITS, parse_phash

MAX_THRESHOLD = 16
_MAX_BLOCK_CELLS = 4_000_000     # caps memory of one comparison block
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
                xor = h[start:start + block, None] ^ h[None, :]
                rows, cols = np.nonzero(_popcount(xor) <= threshold)
                rows = rows + start
                keep = cols > rows
                for r, c in zip(rows[keep], cols[keep]):
                    yield int(bucket[r]), int(bucket[c])


def find_duplicates(
    records: Iterable[tuple[int, str | None, str | None]],
    near_threshold: int = 6,
) -> list[tuple[int, int, str]]:
    """Cluster duplicates.

    Args:
        records: ``(image_id, sha256, phash_hex)`` per image (either hash may be None).
        near_threshold: max Hamming distance for near duplicates (0 = identical
            pHash only; at most 16).

    Returns:
        ``(image_id, cluster_id, kind)`` rows for every image in a cluster of
        two or more, ready for ``DatabaseManager.replace_duplicates``. ``kind``
        is ``'exact'`` if all members share one SHA-256, else ``'near'``.
        Cluster ids start at 1, ordered by each cluster's smallest image id.
    """
    if not 0 <= near_threshold <= MAX_THRESHOLD:
        raise ValueError(f"near_threshold must be between 0 and {MAX_THRESHOLD}")
    recs = [(int(i), sha, ph) for i, sha, ph in records]
    uf = UnionFind(len(recs))

    first_by_sha: dict[str, int] = {}
    first_by_hash: dict[int, int] = {}
    for idx, (_, sha, phash) in enumerate(recs):
        if sha:
            other = first_by_sha.setdefault(sha, idx)
            if other != idx:
                uf.union(other, idx)
        value = parse_phash(phash)
        if value is not None:
            other = first_by_hash.setdefault(value, idx)
            if other != idx:
                uf.union(other, idx)

    # Near search runs over UNIQUE hash values only (identical ones are merged above).
    if near_threshold > 0 and len(first_by_hash) > 1:
        values = np.array(list(first_by_hash.keys()), dtype=np.uint64)
        reps = list(first_by_hash.values())
        for a, b in _near_pairs(values, near_threshold):
            uf.union(reps[a], reps[b])

    components: dict[int, list[int]] = {}
    for idx in range(len(recs)):
        components.setdefault(uf.find(idx), []).append(idx)
    clusters = [sorted(recs[i][0] for i in m) for m in components.values() if len(m) > 1]
    clusters.sort(key=lambda ids: ids[0])

    sha_of = {image_id: sha for image_id, sha, _ in recs}
    rows: list[tuple[int, int, str]] = []
    for cluster_id, ids in enumerate(clusters, start=1):
        shas = {sha_of[i] for i in ids}
        kind = "exact" if len(shas) == 1 and None not in shas else "near"
        rows.extend((image_id, cluster_id, kind) for image_id in ids)
    return rows


def choose_keeper(members: Sequence[Mapping[str, object]]) -> int:
    """Suggest which cluster member to keep: most pixels, then largest file,
    then lowest id. Members need ``id``, ``width``, ``height``, ``size``
    (e.g. rows from ``DatabaseManager.get_duplicate_clusters``)."""
    def rank(m: Mapping[str, object]) -> tuple[int, int, int]:
        pixels = int(m["width"] or 0) * int(m["height"] or 0)
        return (-pixels, -int(m["size"] or 0), int(m["id"]))
    return int(min(members, key=rank)["id"])