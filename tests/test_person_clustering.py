"""Tests for person clustering and face embedding pipeline."""
from __future__ import annotations

import numpy as np
import pytest

from memoframe.core.face_clusterer import cluster_face_embeddings
from memoframe.database import DatabaseManager


def test_cluster_face_embeddings():
    v1 = np.ones(128, dtype=np.float32)
    v1 /= np.linalg.norm(v1)
    
    # Very similar vector to v1 (same person)
    v2 = v1.copy()
    v2[0] += 0.05
    v2 /= np.linalg.norm(v2)

    # Orthogonal / different vector (different person)
    v3 = np.zeros(128, dtype=np.float32)
    v3[10] = 1.0

    records = [(101, v1.tobytes()), (102, v2.tobytes()), (103, v3.tobytes())]
    clusters = cluster_face_embeddings(records, eps=0.38)

    assert len(clusters) == 2
    # Largest cluster should have faces 101 and 102
    assert sorted(clusters[1]) == [101, 102]
    assert clusters[2] == [103]


def test_person_database_operations(tmp_path):
    with DatabaseManager(tmp_path / "test.db") as db:
        # Insert dummy image and faces
        with db._tx() as conn:
            conn.execute("INSERT INTO images (id, path, size, mtime_ns, status) VALUES (1, 'p1.jpg', 100, 100, 'done')")
            conn.execute("INSERT INTO images (id, path, size, mtime_ns, status) VALUES (2, 'p2.jpg', 100, 100, 'done')")
            conn.execute(
                "INSERT INTO faces (id, image_id, label, x, y, w, h, confidence, embedding) "
                "VALUES (10, 1, 'Face 001', 0, 0, 50, 50, 0.9, ?)",
                (b"x" * 512,)
            )
            conn.execute(
                "INSERT INTO faces (id, image_id, label, x, y, w, h, confidence, embedding) "
                "VALUES (11, 2, 'Face 001', 0, 0, 50, 50, 0.9, ?)",
                (b"x" * 512,)
            )

        # Cluster face 10 and 11 into Person 1
        clusters = {1: [10, 11]}
        count = db.replace_person_clusters(clusters)
        assert count == 1

        persons = db.list_persons()
        assert len(persons) == 1
        assert persons[0]["name"] == "Person 01"
        assert persons[0]["image_count"] == 2

        # Rename person
        renamed = db.rename_person(1, "Alice")
        assert renamed is True

        p = db.get_person(1)
        assert p["name"] == "Alice"

        # Search with person_id filter
        results = db.find_images(person_id=1)
        assert len(results) == 2
