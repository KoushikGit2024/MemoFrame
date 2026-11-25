"""Diagnostics bundle: versions, checks, stats, settings and the log tail (no photos)."""
from __future__ import annotations

import json
import platform
import sys
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from config import Settings
from engine.contract import API_VERSION

LOG_TAIL_BYTES = 500_000
KEEP = 5


def _jsonable(value: Any) -> Any:
    if isinstance(value, (Path, frozenset, set)):
        return sorted(map(str, value)) if isinstance(value, (frozenset, set)) else str(value)
    return value


def build_bundle(settings: Settings, doctor: dict, stats: dict, include_log: bool = True) -> Path:
    """Create ``<workspace>/diagnostics/diagnostics-<time>.zip`` and return its path.

    Contains NO photos or thumbnails. The log tail contains file paths: review it
    before sharing.
    """
    folder = settings.workspace / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"diagnostics-{datetime.now():%Y%m%d_%H%M%S}.zip"
    info = {"api_version": API_VERSION, "python": sys.version, "platform": platform.platform(),
            "frozen": bool(getattr(sys, "frozen", False)), "created": datetime.now().isoformat()}
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.json", json.dumps(info, indent=2))
        z.writestr("doctor.json", json.dumps(doctor, indent=2, ensure_ascii=False))
        z.writestr("stats.json", json.dumps(stats, indent=2))
        z.writestr("settings.json", json.dumps(
            {k: _jsonable(v) for k, v in asdict(settings).items()}, indent=2, ensure_ascii=False))
        config = settings.workspace / "config.toml"
        if config.is_file():
            z.write(config, "config.toml")
        log = settings.log_path
        if include_log and log.is_file():
            with log.open("rb") as fh:
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - LOG_TAIL_BYTES))
                z.writestr("photo_organizer.log.tail", fh.read())
        for extra in ("photo_organizer.workers.log", "native_crash.log"):
            p = settings.workspace / extra
            if include_log and p.is_file():
                with p.open("rb") as fh:
                    fh.seek(0, 2)
                    fh.seek(max(0, fh.tell() - LOG_TAIL_BYTES))
                    z.writestr(extra + ".tail", fh.read())
    for old in sorted(folder.glob("diagnostics-*.zip"))[:-KEEP]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest
