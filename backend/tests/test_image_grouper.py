"""Event, GPS and visual grouping (all non-biometric)."""

from __future__ import annotations

from PIL import Image

from services.organization.similarity import compute_features
from services.organization.grouper import group_images, haversine_km


def row(i, ts, lat=None, lon=None, source="exif_original", features=None):
    return {
        "id": i,
        "exif_ts": ts,
        "ts_source": source,
        "gps_lat": lat,
        "gps_lon": lon,
        "features": features,
    }


def ids(groups):
    return [g["image_ids"] for g in groups]


def test_haversine_one_degree_of_longitude_at_equator():
    assert abs(haversine_km(0, 0, 0, 1) - 111.19) < 0.1
    assert haversine_km(10, 10, 10, 10) == 0


def test_time_gap_splits_events():
    rows = [
        row(1, "2024-06-01T10:00:00"),
        row(2, "2024-06-01T10:30:00"),
        row(3, "2024-06-01T18:00:00"),
        row(4, "2024-06-02T09:00:00"),
    ]
    assert ids(group_images(rows)) == [[1, 2], [3], [4]]


def test_gap_threshold_is_configurable():
    rows = [row(1, "2024-06-01T10:00:00"), row(2, "2024-06-01T13:30:00")]
    assert ids(group_images(rows, event_gap_hours=3)) == [[1], [2]]
    assert ids(group_images(rows, event_gap_hours=4)) == [[1, 2]]


def test_input_order_does_not_matter():
    rows = [row(2, "2024-06-01T10:30:00"), row(1, "2024-06-01T10:00:00")]
    assert ids(group_images(rows)) == [[1, 2]]


def test_gps_jump_splits_event():
    rows = [row(1, "2024-06-02T09:00:00", 10.0, 10.0), row(2, "2024-06-02T09:10:00", 10.5, 10.5)]
    assert ids(group_images(rows, gps_split_km=5)) == [[1], [2]]


def test_gps_split_can_be_disabled():
    rows = [row(1, "2024-06-02T09:00:00", 10.0, 10.0), row(2, "2024-06-02T09:10:00", 10.5, 10.5)]
    assert ids(group_images(rows, gps_split_km=0)) == [[1, 2]]


def test_photo_without_gps_does_not_hide_a_jump():
    rows = [
        row(1, "2024-06-02T09:00:00", 10.0, 10.0),
        row(2, "2024-06-02T09:10:00"),
        row(3, "2024-06-02T09:20:00", 10.5, 10.5),
    ]
    assert ids(group_images(rows, gps_split_km=5)) == [[1, 2], [3]]


def test_mtime_dates_form_separate_groups():
    rows = [row(1, "2024-06-01T10:00:00"), row(2, "2024-06-01T10:05:00", source="file_mtime")]
    groups = group_images(rows)
    assert len(groups) == 2
    assert groups[0]["name"].startswith("Event") and groups[1]["name"].startswith("File date")


def test_min_group_size_drops_small_groups():
    rows = [
        row(1, "2024-06-01T10:00:00"),
        row(2, "2024-06-01T10:10:00"),
        row(3, "2024-06-03T10:00:00"),
    ]
    assert ids(group_images(rows, min_group_size=2)) == [[1, 2]]


def test_group_times_recorded():
    g = group_images([row(1, "2024-06-01T10:00:00"), row(2, "2024-06-01T10:30:00")])[0]
    assert (g["kind"], g["start_ts"], g["end_ts"]) == (
        "event",
        "2024-06-01T10:00:00",
        "2024-06-01T10:30:00",
    )


def test_undated_images_cluster_visually():
    feat = lambda colour: compute_features(Image.new("RGB", (64, 64), colour))
    rows = [
        row(1, None, source="none", features=feat("red")),
        row(2, None, source="none", features=feat((250, 5, 5))),
        row(3, None, source="none", features=feat("blue")),
    ]
    groups = group_images(rows)
    assert all(g["kind"] == "visual" for g in groups)
    assert sorted(sorted(g) for g in ids(groups)) == [[1, 2], [3]]


def test_undated_without_features_stay_ungrouped():
    assert group_images([row(1, None, source="none")]) == []


def test_empty_input():
    assert group_images([]) == []
