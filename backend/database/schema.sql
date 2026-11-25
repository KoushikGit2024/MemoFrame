-- Photo organizer schema, version 1.
-- Face rows store geometry, detector confidence, and 128-d SFace embeddings for offline person clustering.

CREATE TABLE IF NOT EXISTS groups (
    id           INTEGER PRIMARY KEY,
    kind         TEXT    NOT NULL CHECK (kind IN ('event', 'visual')),
    name         TEXT,
    start_ts     TEXT,
    end_ts       TEXT,
    image_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS images (
    id            INTEGER PRIMARY KEY,
    path          TEXT    NOT NULL UNIQUE,
    size          INTEGER NOT NULL,              -- file size in bytes
    mtime_ns      INTEGER NOT NULL,              -- with size: change fingerprint
    width         INTEGER,
    height        INTEGER,
    sha256        TEXT,                          -- exact-duplicate key
    phash         TEXT,                          -- 64-bit perceptual hash, 16 hex chars
    exif_ts       TEXT,                          -- ISO-8601 'YYYY-MM-DDTHH:MM:SS'
    ts_source     TEXT,                          -- exif_original | exif_datetime | file_mtime | none
    gps_lat       REAL,
    gps_lon       REAL,
    features      BLOB,                          -- colour-histogram bytes (non-biometric)
    thumb_path    TEXT,
    face_count    INTEGER NOT NULL DEFAULT 0,
    status        TEXT    NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'done', 'failed')),
    error         TEXT,
    group_id      INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    processed_at  TEXT
);

CREATE TABLE IF NOT EXISTS persons (
    id             INTEGER PRIMARY KEY,
    name           TEXT    NOT NULL,
    cover_face_id  INTEGER REFERENCES faces(id) ON DELETE SET NULL,
    image_count    INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS faces (
    id          INTEGER PRIMARY KEY,
    image_id    INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    person_id   INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    label       TEXT    NOT NULL,                -- 'Face 001': only meaningful within one image
    x           INTEGER NOT NULL,                -- full-resolution pixel coordinates
    y           INTEGER NOT NULL,
    w           INTEGER NOT NULL,
    h           INTEGER NOT NULL,
    confidence  REAL    NOT NULL,
    crop_path   TEXT,
    embedding   BLOB                             -- 128-d float32 L2-normalized feature vector (512 bytes)
);

-- One row per image that belongs to a duplicate cluster (cluster size >= 2).
CREATE TABLE IF NOT EXISTS duplicates (
    image_id    INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    cluster_id  INTEGER NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('exact', 'near'))
);

CREATE INDEX IF NOT EXISTS idx_images_status   ON images(status);
CREATE INDEX IF NOT EXISTS idx_images_sha256   ON images(sha256);
CREATE INDEX IF NOT EXISTS idx_images_exif_ts  ON images(exif_ts);
CREATE INDEX IF NOT EXISTS idx_images_group    ON images(group_id);
CREATE INDEX IF NOT EXISTS idx_faces_image     ON faces(image_id);
CREATE INDEX IF NOT EXISTS idx_faces_person    ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_dup_cluster     ON duplicates(cluster_id);