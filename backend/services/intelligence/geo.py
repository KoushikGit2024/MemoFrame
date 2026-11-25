"""Offline place names: nearest city from a GeoNames-format file, or a tiny built-in list."""

from __future__ import annotations

from pathlib import Path

import numpy as np

_BUILTIN = [
    ("Imphal", "IN", 24.8170, 93.9368),
    ("Guwahati", "IN", 26.1445, 91.7362),
    ("Agartala", "IN", 23.8315, 91.2868),
    ("Kolkata", "IN", 22.5726, 88.3639),
    ("Delhi", "IN", 28.6139, 77.2090),
    ("Mumbai", "IN", 19.0760, 72.8777),
    ("Bengaluru", "IN", 12.9716, 77.5946),
    ("Chennai", "IN", 13.0827, 80.2707),
    ("Hyderabad", "IN", 17.3850, 78.4867),
    ("London", "GB", 51.5074, -0.1278),
    ("New York", "US", 40.7128, -74.0060),
    ("Paris", "FR", 48.8566, 2.3522),
    ("Tokyo", "JP", 35.6762, 139.6503),
    ("Singapore", "SG", 1.3521, 103.8198),
    ("Dubai", "AE", 25.2048, 55.2708),
    ("Sydney", "AU", -33.8688, 151.2093),
]
FILE_NAMES = ("cities.txt", "cities15000.txt", "cities5000.txt", "cities1000.txt")
_R_KM = 6371.0088


class PlaceIndex:
    def __init__(self, labels: list[str], lat: np.ndarray, lon: np.ndarray) -> None:
        self.labels, self.lat, self.lon = labels, np.radians(lat), np.radians(lon)

    @classmethod
    def builtin(cls) -> "PlaceIndex":
        return cls(
            [f"{n}, {c}" for n, c, _, _ in _BUILTIN],
            np.array([b[2] for b in _BUILTIN]),
            np.array([b[3] for b in _BUILTIN]),
        )

    @classmethod
    def from_file(cls, path: Path) -> "PlaceIndex":
        """GeoNames tab format: name = column 2, lat/lon = columns 5/6, country = column 9."""
        labels, lat, lon = [], [], []
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 9:
                    continue
                try:
                    la, lo = float(parts[4]), float(parts[5])
                except ValueError:
                    continue
                labels.append(f"{parts[1]}, {parts[8]}" if parts[8] else parts[1])
                lat.append(la)
                lon.append(lo)
        if not labels:
            raise ValueError(f"No places found in {path}")
        return cls(labels, np.array(lat), np.array(lon))

    def lookup_many(self, points: np.ndarray, max_km: float) -> list[str | None]:
        """Nearest place per ``(lat, lon)`` row, or ``None`` if farther than ``max_km``."""
        out: list[str | None] = []
        # Cap intermediate distance-matrix memory at ~32 MB (float64: 8 bytes per cell).
        step = max(1, min(256, (32 * 1024 * 1024) // (max(1, len(self.labels)) * 8)))
        for start in range(0, len(points), step):
            p = np.radians(np.asarray(points[start : start + step], dtype=np.float64))
            dlat = p[:, 0, None] - self.lat[None, :]
            dlon = p[:, 1, None] - self.lon[None, :]
            a = (
                np.sin(dlat / 2) ** 2
                + np.cos(p[:, 0, None]) * np.cos(self.lat)[None, :] * np.sin(dlon / 2) ** 2
            )
            dist = 2 * _R_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))
            nearest = dist.argmin(axis=1)
            out.extend(
                self.labels[j] if dist[i, j] <= max_km else None for i, j in enumerate(nearest)
            )
        return out


def load_place_index(data_dir: Path) -> PlaceIndex:
    """Use a GeoNames file from ``data_dir`` if present, else the built-in fallback."""
    for name in FILE_NAMES:
        candidate = Path(data_dir) / name
        if candidate.is_file():
            return PlaceIndex.from_file(candidate)
    return PlaceIndex.builtin()
