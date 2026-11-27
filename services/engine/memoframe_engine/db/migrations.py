"""Versioned schema migrations with an automatic backup before upgrading.

To change the schema later: append ``(N, lambda: "SQL ...")`` to MIGRATIONS.
Use ``IF NOT EXISTS`` so a migration can safely be re-run after a crash.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Callable

from memoframe_engine.utils.logger import get_logger

log = get_logger("memoframe_engine.db.migrations")

_SCHEMA_V1 = (
    Path(getattr(sys, "_MEIPASS")) / "memoframe_engine" / "db" / "schema.sql"
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
    else Path(__file__).with_name("schema.sql")
)

_V2 = """
CREATE TABLE IF NOT EXISTS marks (
    image_id    INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL CHECK (kind IN ('keep', 'reviewed', 'favourite', 'hidden')),
    note        TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (image_id, kind)
);
CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT
);
"""


def _v3(conn: sqlite3.Connection) -> str:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(images)")}
    alter = (
        "" if "state" in cols else "ALTER TABLE images ADD COLUMN state TEXT NOT NULL DEFAULT 'ok';"
    )
    return (
        alter
        + """
CREATE TABLE IF NOT EXISTS sources (
    path       TEXT PRIMARY KEY,
    last_seen  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_images_state ON images(state);
"""
    )


def _v4(conn: sqlite3.Connection) -> str:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(images)")}
    stmts = [
        f"ALTER TABLE images ADD COLUMN {name} {ddl};"
        for name, ddl in (
            ("kind", "TEXT NOT NULL DEFAULT 'photo'"),
            ("duration_s", "REAL"),
            ("format", "TEXT"),
            ("pair_id", "INTEGER"),
        )
        if name not in cols
    ]
    stmts.append("CREATE INDEX IF NOT EXISTS idx_images_kind ON images(kind);")
    return "\n".join(stmts)


def _v5(conn: sqlite3.Connection) -> str:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(images)")}
    wanted = (
        ("quality", "REAL"),
        ("sharpness", "REAL"),
        ("brightness", "REAL"),
        ("dhash", "TEXT"),
        ("content_type", "TEXT NOT NULL DEFAULT 'photo'"),
        ("place", "TEXT"),
        ("burst_id", "INTEGER"),
        ("date_flag", "TEXT"),
    )
    stmts = [f"ALTER TABLE images ADD COLUMN {n} {d};" for n, d in wanted if n not in cols]
    stmts.append("""
CREATE TABLE IF NOT EXISTS bursts (
    id INTEGER PRIMARY KEY, best_image_id INTEGER, image_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS date_overrides (
    image_id INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    exif_ts TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS idx_images_burst ON images(burst_id);
CREATE INDEX IF NOT EXISTS idx_images_content ON images(content_type);
""")
    return "\n".join(stmts)


def _v6(conn: sqlite3.Connection) -> str:
    return """
CREATE TABLE IF NOT EXISTS marks_archive (
    sha256 TEXT NOT NULL, kind TEXT NOT NULL, note TEXT, path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (sha256, kind, path));
CREATE TABLE IF NOT EXISTS saved_searches (
    name TEXT PRIMARY KEY, filters TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS idx_marks_kind ON marks(kind);
CREATE INDEX IF NOT EXISTS idx_images_format ON images(format);
INSERT OR IGNORE INTO marks_archive (sha256, kind, note, path)
    SELECT i.sha256, m.kind, m.note, i.path FROM marks m
    JOIN images i ON i.id = m.image_id WHERE i.sha256 IS NOT NULL;
"""


def _v7(conn: sqlite3.Connection) -> str:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(images)")}
    alter = "" if "tagged_with" in cols else "ALTER TABLE images ADD COLUMN tagged_with TEXT;"
    return (
        alter
        + """
CREATE TABLE IF NOT EXISTS tags (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    label    TEXT NOT NULL,
    score    REAL NOT NULL,
    source   TEXT NOT NULL DEFAULT 'scene',
    PRIMARY KEY (image_id, label, source));
CREATE TABLE IF NOT EXISTS embeddings (
    image_id INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    model    TEXT NOT NULL,
    vec      BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tags_label ON tags(label);
"""
    )


def _v8(conn: sqlite3.Connection) -> str:
    face_cols = {r[1] for r in conn.execute("PRAGMA table_info(faces)")}
    stmts = []
    if "person_id" not in face_cols:
        stmts.append(
            "ALTER TABLE faces ADD COLUMN person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL;"
        )
    if "embedding" not in face_cols:
        stmts.append("ALTER TABLE faces ADD COLUMN embedding BLOB;")

    stmts.append("""
CREATE TABLE IF NOT EXISTS persons (
    id             INTEGER PRIMARY KEY,
    name           TEXT    NOT NULL,
    cover_face_id  INTEGER REFERENCES faces(id) ON DELETE SET NULL,
    image_count    INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
""")
    return "\n".join(stmts)


def _v9(conn: sqlite3.Connection) -> str:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(faces)")}
    alter = (
        ""
        if "locked" in cols
        else "ALTER TABLE faces ADD COLUMN locked INTEGER NOT NULL DEFAULT 0;"
    )
    return (
        alter + "\nCREATE INDEX IF NOT EXISTS idx_faces_locked ON faces(locked) WHERE locked = 1;"
    )


def _v10(_conn: sqlite3.Connection) -> str:
    return "CREATE INDEX IF NOT EXISTS idx_marks_id_kind ON marks(image_id, kind);"


def _v11(conn: sqlite3.Connection) -> str:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(faces)")}
    alter = (
        ""
        if "ignored" in cols
        else "ALTER TABLE faces ADD COLUMN ignored INTEGER NOT NULL DEFAULT 0;"
    )
    return alter


def _v12(_conn: sqlite3.Connection) -> str:
    return """
CREATE INDEX IF NOT EXISTS idx_groups_start_ts ON groups(start_ts);
CREATE INDEX IF NOT EXISTS idx_images_exif_ts ON images(exif_ts);
"""


MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], str]]] = [
    (1, lambda c: _SCHEMA_V1.read_text(encoding="utf-8")),
    (2, lambda c: _V2),
    (3, _v3),
    (4, _v4),
    (5, _v5),
    (6, _v6),
    (7, _v7),
    (8, _v8),
    (9, _v9),
    (10, _v10),
    (11, _v11),
    (12, _v12),
]
LATEST_VERSION = MIGRATIONS[-1][0]


class MigrationError(RuntimeError):
    """The database cannot be upgraded or is newer than this program."""


def migrate(conn: sqlite3.Connection, backup_prefix: str | None = None) -> int:
    """Bring the database to the latest schema and return the version.

    An existing database (version > 0) is copied to ``<prefix>.bak-v<old>`` first.
    """
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current > LATEST_VERSION:
        raise MigrationError(
            f"Database schema v{current} is newer than this program (v{LATEST_VERSION}). "
            "Update the application."
        )
    if current == LATEST_VERSION:
        return current

    backup_path: str | None = None
    if current > 0 and backup_prefix:
        backup_path = f"{backup_prefix}.bak-v{current}"
        target = sqlite3.connect(backup_path)
        try:
            conn.backup(target)
        finally:
            target.close()
        log.info("Database backed up to %s", backup_path)

    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        try:
            conn.executescript(sql(conn))
            conn.execute(f"PRAGMA user_version = {version}")
        except sqlite3.Error as exc:
            hint = f" Your backup is {backup_path}." if backup_path else ""
            raise MigrationError(f"Upgrade to schema v{version} failed: {exc}.{hint}") from exc
        log.info("Database upgraded to schema v%d", version)
    return LATEST_VERSION
