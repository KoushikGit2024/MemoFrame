"""Exact and near-duplicate clustering, including a brute-force recall check."""
from __future__ import annotations

import random

import pytest

from memoframe.core.duplicate_detector import UnionFind, choose_keeper, find_duplicates
from memoframe.core.image_similarity import hamming

BASE = 0x0123456789ABCDEF


def _hex(value: int) -> str:
    return f"{value:016x}"


def _flip(value: int, bits: list[int]) -> int:
    for b in bits:
        value ^= 1 << b
    return value


def _clusters(rows):
    out: dict[int, set[int]] = {}
    for image_id, cluster_id, _ in rows:
        out.setdefault(cluster_id, set()).add(image_id)
    return list(out.values())


def test_exact_duplicates_by_sha():
    rows = find_duplicates([(1, "aaa", _hex(BASE)), (2, "aaa", _hex(BASE)), (3, "bbb", _hex(~BASE & (2**64 - 1)))])
    assert _clusters(rows) == [{1, 2}]
    assert {kind for _, _, kind in rows} == {"exact"}


def test_exact_by_sha_even_if_phash_missing():
    rows = find_duplicates([(1, "aaa", None), (2, "aaa", None)])
    assert _clusters(rows) == [{1, 2}]


def test_near_duplicate_within_threshold():
    rows = find_duplicates([(1, "a", _hex(BASE)), (2, "b", _hex(_flip(BASE, [0, 20, 40])))],
                           near_threshold=6)
    assert _clusters(rows) == [{1, 2}]
    assert {kind for _, _, kind in rows} == {"near"}


def test_not_duplicate_beyond_threshold():
    far = _flip(BASE, list(range(0, 20)))
    assert hamming(_hex(BASE), _hex(far)) == 20
    assert find_duplicates([(1, "a", _hex(BASE)), (2, "b", _hex(far))], near_threshold=6) == []


def test_threshold_zero_only_identical_hashes():
    close = _flip(BASE, [3])
    assert find_duplicates([(1, "a", _hex(BASE)), (2, "b", _hex(close))], near_threshold=0) == []
    assert _clusters(find_duplicates([(1, "a", _hex(BASE)), (2, "b", _hex(BASE))], 0)) == [{1, 2}]


def test_chaining_is_transitive():
    a = BASE
    b = _flip(a, [0, 1, 2, 3, 4])
    c = _flip(b, [10, 11, 12, 13, 14])         # 10 bits from a, 5 from b
    rows = find_duplicates([(1, "x", _hex(a)), (2, "y", _hex(b)), (3, "z", _hex(c))], near_threshold=6)
    assert _clusters(rows) == [{1, 2, 3}]


def test_singletons_and_missing_hashes_excluded():
    rows = find_duplicates([(1, "a", _hex(BASE)), (2, None, None), (3, "c", "not-a-hash")])
    assert rows == []


def test_many_identical_images_one_cluster():
    rows = find_duplicates([(i, f"s{i}", _hex(BASE)) for i in range(1, 501)])
    assert len(_clusters(rows)) == 1 and len(rows) == 500


def test_cluster_ids_ordered_by_smallest_member():
    other = ~BASE & (2**64 - 1)
    rows = find_duplicates([(5, "a", _hex(other)), (6, "b", _hex(other)),
                            (1, "c", _hex(BASE)), (2, "d", _hex(BASE))])
    by_image = {i: c for i, c, _ in rows}
    assert by_image[1] == by_image[2] == 1 and by_image[5] == by_image[6] == 2


def test_invalid_threshold_rejected():
    with pytest.raises(ValueError):
        find_duplicates([], near_threshold=17)
    with pytest.raises(ValueError):
        find_duplicates([], near_threshold=-1)


@pytest.mark.parametrize("threshold", [0, 2, 6])
def test_matches_brute_force(threshold):
    """The banded search must find exactly the pairs an O(n^2) comparison finds."""
    rng = random.Random(1)
    values: list[int] = []
    for _ in range(60):
        base = rng.getrandbits(64)
        values.append(base)
        for _ in range(2):
            values.append(_flip(base, rng.sample(range(64), rng.randint(0, 4))))

    uf = UnionFind(len(values))
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            if (values[i] ^ values[j]).bit_count() <= threshold:
                uf.union(i, j)
    comps: dict[int, set[int]] = {}
    for i in range(len(values)):
        comps.setdefault(uf.find(i), set()).add(i + 1)
    expected = {frozenset(c) for c in comps.values() if len(c) > 1}

    rows = find_duplicates([(i + 1, None, _hex(v)) for i, v in enumerate(values)], threshold)
    assert {frozenset(c) for c in _clusters(rows)} == expected


def test_choose_keeper_prefers_resolution_then_size_then_id():
    members = [
        {"id": 3, "width": 100, "height": 100, "size": 500},
        {"id": 1, "width": 200, "height": 100, "size": 100},
        {"id": 2, "width": 200, "height": 100, "size": 900},
    ]
    assert choose_keeper(members) == 2
    assert choose_keeper([{"id": 7, "width": 10, "height": 10, "size": 5},
                          {"id": 4, "width": 10, "height": 10, "size": 5}]) == 4