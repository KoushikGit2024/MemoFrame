"""Phase F tests: scene tagging, similarity, schema guards, CLI tag."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from config import Settings
from services.intelligence.tagger import (
    SceneTagger,
    TaggerUnavailableError,
    clean_label,
    create_tagger,
    load_labels,
    load_tag_map,
)
from database.db_manager import DatabaseManager
from services.intelligence.similar import find_similar
from services.intelligence.tagging import tag_existing


# ----------------------------------------------------------------------
# Unit tests
# ----------------------------------------------------------------------
def test_clean_label():
    assert clean_label("golden retriever, dog") == "golden retriever"
    assert clean_label("n01440764 tench, Tinca tinca") == "tench"
    assert clean_label("tabby, tabby cat") == "tabby"
    assert clean_label("  desk  ") == "desk"
    assert clean_label("bad-word_123") == "bad-word_123"


def test_load_labels(tmp_path: Path):
    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("cat\ndog\nfish\n", encoding="utf-8")
    assert load_labels(labels_file) == ["cat", "dog", "fish"]


def test_load_tag_map(tmp_path: Path):
    map_file = tmp_path / "tag_map.txt"
    map_file.write_text("golden retriever => dog\ntabby => cat\n# comment\n", encoding="utf-8")
    assert load_tag_map(map_file) == {"golden retriever": "dog", "tabby": "cat"}


def test_tagger_missing_model_raises(tmp_path: Path):
    s = Settings(workspace=tmp_path, tagging_enabled=True)
    with pytest.raises(TaggerUnavailableError):
        create_tagger(s)


def test_scene_tagger_inference():
    labels = ["cat", "dog", "fish", "bird"]
    # 4 classes logits: cat=1.0, dog=4.0, fish=0.0, bird=2.0
    logits = np.array([[1.0, 4.0, 0.0, 2.0]], dtype=np.float32)

    def fake_forward(blob):
        return logits

    tagger = SceneTagger(
        fake_forward,
        labels,
        "sig123",
        top_k=2,
        min_score=0.1,
    )
    dummy_img = Image.new("RGB", (100, 100))
    tags, emb = tagger.tag(dummy_img)

    assert len(tags) == 2
    assert tags[0][0] == "dog"
    assert tags[1][0] == "bird"
    assert emb is not None


def test_scene_tagger_embedding_extraction():
    labels = ["cat", "dog"]
    logits = np.array([[1.0, 2.0]], dtype=np.float32)

    def fake_forward(blob):
        return logits

    tagger = SceneTagger(
        fake_forward,
        labels,
        "sig123",
        top_k=1,
        min_score=0.1,
    )
    dummy_img = Image.new("RGB", (100, 100))
    tags, emb = tagger.tag(dummy_img)

    assert len(tags) == 1
    assert emb is not None
    unpacked = np.frombuffer(emb, dtype=np.float16)
    assert len(unpacked) == 2
    # Probability vector norm after sqrt and unit normalization is 1.0
    assert abs(np.linalg.norm(unpacked) - 1.0) < 1e-3


# ----------------------------------------------------------------------
# Schema Guard: faces table has no embeddings
# ----------------------------------------------------------------------
def test_faces_table_has_person_and_embedding_columns(tmp_path: Path):
    s = Settings(workspace=tmp_path)
    s.ensure_dirs()
    with DatabaseManager(s.db_path) as db:
        cols = [r[1].lower() for r in db._conn.execute("PRAGMA table_info(faces)").fetchall()]
        assert "person_id" in cols
        assert "embedding" in cols


# ----------------------------------------------------------------------
# Integration: tag_existing and pipeline tagging
# ----------------------------------------------------------------------
def test_backfill_then_nothing_left_and_unreadable_skipped(tmp_path: Path, monkeypatch):
    s = Settings(workspace=tmp_path, tagging_enabled=True, store_embeddings=True)
    s.ensure_dirs()

    # Create dummy images
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    p1 = img_dir / "pic1.jpg"
    p2 = img_dir / "pic2.jpg"
    Image.new("RGB", (50, 50), color="red").save(p1)
    Image.new("RGB", (50, 50), color="blue").save(p2)

    with DatabaseManager(s.db_path) as db:
        db.register_files([(p1, p1.stat().st_size, int(p1.stat().st_mtime_ns)),
                           (p2, p2.stat().st_size, int(p2.stat().st_mtime_ns))])
        db.save_results([
            {"image_id": 1, "sha256": "fake1", "status": "done"},
            {"image_id": 2, "sha256": "fake2", "status": "done"},
        ])

        assert db.count_untagged("sig123") == 2

    # Mock create_tagger and image loader
    # Softmax([1.0, 5.0]): exp(1)=2.718, exp(5)=148.41 -> cat ~ 0.018, dog ~ 0.982
    # With min_score=0.01, both survive!
    logits = np.array([[1.0, 5.0]], dtype=np.float32)
    mock_tagger = SceneTagger(lambda b: logits, labels=["cat", "dog"], signature="sig123", min_score=0.01)

    monkeypatch.setattr("services.intelligence.tagging.create_tagger", lambda s: mock_tagger)
    real_open = Image.open

    def mock_open(fp, *args, **kwargs):
        if "pic2" in str(fp):
            raise OSError("Unreadable")
        return real_open(fp, *args, **kwargs)

    monkeypatch.setattr("PIL.Image.open", mock_open)

    with DatabaseManager(s.db_path) as db:
        tagged = tag_existing(s, db)
        assert tagged == 1  # p1 succeeded, p2 failed decode and remains untagged

        # Only 1 image is untagged (p2)
        assert db.count_untagged(mock_tagger.signature) == 1

        # Verify p1 tags and embeddings
        tags = db.get_tags(1)
        assert len(tags) == 2
        assert tags[0]["label"] == "dog"
        emb = db.get_embedding(1)
        assert emb is not None

        # Re-run does 0 (p2 still unreadable)
        tagged2 = tag_existing(s, db)
        assert tagged2 == 0


def test_changed_file_resets_tags_and_embeddings(tmp_path: Path):
    s = Settings(workspace=tmp_path)
    s.ensure_dirs()
    p = tmp_path / "img.jpg"
    p.write_bytes(b"dummy")

    with DatabaseManager(s.db_path) as db:
        db.register_files([(p, 5, 1000)])
        db.save_results([{"image_id": 1, "sha256": "hash1", "status": "done"}])
        db.save_tags([(1, {
            "tags": [("dog", 0.9)],
            "tag_model": "m1",
            "embedding": np.array([1.0, 0.0], dtype=np.float16).tobytes(),
        })])

        assert len(db.get_tags(1)) == 1
        assert db.get_embedding(1) is not None

        # Change file and re-register
        p.write_bytes(b"dummy_changed")
        db.register_files([(p, 13, 2000)])

        # Tags and embeddings should be cleared
        assert len(db.get_tags(1)) == 0
        assert db.get_embedding(1) is None


def test_similar_cosine_search(tmp_path: Path):
    s = Settings(workspace=tmp_path)
    s.ensure_dirs()

    # Vector 1: [1, 0], Vector 2: [0.8, 0.6], Vector 3: [0, 1]
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v2 = np.array([0.8, 0.6], dtype=np.float32)
    v3 = np.array([0.0, 1.0], dtype=np.float32)

    with DatabaseManager(s.db_path) as db:
        p1 = tmp_path / "1.jpg"
        p2 = tmp_path / "2.jpg"
        p3 = tmp_path / "3.jpg"
        for i, (path, v) in enumerate([(p1, v1), (p2, v2), (p3, v3)], start=1):
            path.write_bytes(b"x")
            db.register_files([(path, 1, 1)])
            db.save_results([{"image_id": i, "sha256": f"h{i}", "status": "done"}])
            db.save_tags([(i, {
                "tags": [],
                "tag_model": "m1",
                "embedding": v.astype(np.float16).tobytes(),
            })])

        # Search similar to image 1
        results = find_similar(db, image_id=1, limit=5)
        # Target itself is excluded; image 2 cosine = 0.8, image 3 cosine = 0.0
        assert len(results) == 2
        img_id, score = results[0]
        assert img_id == 2
        assert abs(score - 0.8) < 1e-3


def test_v6_to_v7_migration(tmp_path: Path):
    from database.migrations import migrate, LATEST_VERSION, MIGRATIONS
    db_file = tmp_path / "test_mig.db"
    conn = sqlite3.connect(str(db_file))
    try:
        # Run up to v6
        for v, sql in MIGRATIONS[:6]:
            conn.executescript(sql(conn))
            conn.execute(f"PRAGMA user_version = {v}")
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 6

        # Now migrate to latest (v8)
        ver = migrate(conn, backup_prefix=str(db_file))
        assert ver == LATEST_VERSION
        assert (tmp_path / "test_mig.db.bak-v6").is_file()

        # Check v7 & v8 tables and columns
        cols = {r[1] for r in conn.execute("PRAGMA table_info(images)")}
        assert "tagged_with" in cols
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "tags" in tables
        assert "persons" in tables
        assert "embeddings" in tables
    finally:
        conn.close()


def test_find_similar_raises_on_untagged_image(tmp_path: Path):
    s = Settings(workspace=tmp_path)
    s.ensure_dirs()
    with DatabaseManager(s.db_path) as db:
        p = tmp_path / "1.jpg"
        p.write_bytes(b"x")
        db.register_files([(p, 1, 1)])
        db.save_results([{"image_id": 1, "sha256": "h1", "status": "done"}])
        with pytest.raises(ValueError, match="no stored embedding"):
            find_similar(db, image_id=1)


def test_tagger_with_tag_map_groups_scores():
    labels = ["golden retriever", "labrador retriever", "tabby"]
    logits = np.array([[2.0, 3.0, 1.0]], dtype=np.float32)

    tagger = SceneTagger(
        lambda b: logits,
        labels,
        "sig_map",
        tag_map={"golden retriever": "dog", "labrador retriever": "dog", "tabby": "cat"},
        min_score=0.01,
    )
    dummy_img = Image.new("RGB", (64, 64))
    tags, emb = tagger.tag(dummy_img)
    tag_dict = dict(tags)
    assert "dog" in tag_dict
    assert "cat" in tag_dict
    assert tag_dict["dog"] > tag_dict["cat"]

