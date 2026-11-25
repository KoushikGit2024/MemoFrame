"""Tests for person clustering and face embedding pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from config import Settings
from services.face.clusterer import cluster_face_embeddings
from database import DatabaseManager
from services.pipeline import orchestrator as pipeline


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
            conn.execute(
                "INSERT INTO images (id, path, size, mtime_ns, status) VALUES (1, 'p1.jpg', 100, 100, 'done')"
            )
            conn.execute(
                "INSERT INTO images (id, path, size, mtime_ns, status) VALUES (2, 'p2.jpg', 100, 100, 'done')"
            )
            conn.execute(
                "INSERT INTO faces (id, image_id, label, x, y, w, h, confidence, embedding) "
                "VALUES (10, 1, 'Face 001', 0, 0, 50, 50, 0.9, ?)",
                (b"x" * 512,),
            )
            conn.execute(
                "INSERT INTO faces (id, image_id, label, x, y, w, h, confidence, embedding) "
                "VALUES (11, 2, 'Face 001', 0, 0, 50, 50, 0.9, ?)",
                (b"x" * 512,),
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


def test_person_names_survive_recluster(tmp_path):
    with DatabaseManager(tmp_path / "test.db") as db:
        with db._tx() as conn:
            conn.execute(
                "INSERT INTO images (id, path, size, mtime_ns, status) VALUES (1, 'p1.jpg', 100, 100, 'done')"
            )
            conn.execute(
                "INSERT INTO images (id, path, size, mtime_ns, status) VALUES (2, 'p2.jpg', 100, 100, 'done')"
            )
            conn.execute(
                "INSERT INTO images (id, path, size, mtime_ns, status) VALUES (3, 'p3.jpg', 100, 100, 'done')"
            )
            conn.execute(
                "INSERT INTO faces (id, image_id, label, x, y, w, h, confidence, embedding) VALUES (1, 1, 'Face 001', 0, 0, 50, 50, 0.9, ?)",
                (b"x" * 512,),
            )
            conn.execute(
                "INSERT INTO faces (id, image_id, label, x, y, w, h, confidence, embedding) VALUES (2, 2, 'Face 001', 0, 0, 50, 50, 0.9, ?)",
                (b"x" * 512,),
            )
            conn.execute(
                "INSERT INTO faces (id, image_id, label, x, y, w, h, confidence, embedding) VALUES (3, 3, 'Face 001', 0, 0, 50, 50, 0.9, ?)",
                (b"x" * 512,),
            )

        # Cluster 1: [1, 2], Cluster 2: [3]
        db.replace_person_clusters({1: [1, 2], 2: [3]})
        p1 = [
            p
            for p in db.list_persons()
            if 1
            in [r["id"] for r in db._query("SELECT id FROM faces WHERE person_id = ?", (p["id"],))]
        ][0]
        pid1 = p1["id"]
        db.rename_person(pid1, "Alice")
        assert db.get_person(pid1)["name"] == "Alice"

        rev_before = db.revision()
        # Re-cluster with re-ordered clusters and a new face
        db.replace_person_clusters({10: [3], 20: [1, 2]})
        # Alice should still be mapped to cluster containing [1, 2]
        p_alice = [p for p in db.list_persons() if p["name"] == "Alice"]
        assert len(p_alice) == 1
        alice_faces = [
            r["id"]
            for r in db._query("SELECT id FROM faces WHERE person_id = ?", (p_alice[0]["id"],))
        ]
        assert sorted(alice_faces) == [1, 2]
        # Revision should NOT have bumped (only persons_rev bumped)
        assert db.revision() == rev_before


def _vec(i):
    v = np.zeros(128, dtype=np.float32)
    v[i] = 1.0
    return v.tobytes()


def test_manual_corrections_survive_recluster(tmp_path):
    s = Settings(workspace=tmp_path)
    with DatabaseManager(tmp_path / "t.db") as db:
        with db._tx() as c:
            for i in range(1, 6):
                c.execute(
                    "INSERT INTO images (id, path, size, mtime_ns, status) "
                    "VALUES (?, ?, 1, 1, 'done')",
                    (i, f"p{i}.jpg"),
                )
            for fid, img, emb in (
                (10, 1, _vec(0)),
                (11, 2, _vec(0)),
                (12, 3, _vec(1)),
                (13, 4, _vec(1)),
                (14, 5, _vec(1)),
            ):
                c.execute(
                    "INSERT INTO faces (id, image_id, label, x, y, w, h, confidence, embedding) "
                    "VALUES (?, ?, 'Face 001', 0, 0, 60, 60, 0.95, ?)",
                    (fid, img, emb),
                )
        pid = lambda fid: db._query("SELECT person_id FROM faces WHERE id = ?", (fid,))[0][0]

        pipeline.update_persons(s, db, force=True)
        bob = db.create_person("Bob", [12])  # user pins one face
        pipeline.update_persons(s, db, force=True)
        assert pid(12) == pid(13) == pid(14) == bob  # Bob claims look-alikes
        assert pid(10) == pid(11) not in (None, bob)
        assert db.get_person(bob)["name"] == "Bob"

        db.assign_face(13, None)  # "not a person I care about"
        pipeline.update_persons(s, db, force=True)
        assert pid(13) is None and pid(14) == bob

        other = pid(10)
        db.merge_persons(bob, other)
        pipeline.update_persons(s, db, force=True)
        assert pid(10) == pid(11) == bob and db.get_person(other) is None
