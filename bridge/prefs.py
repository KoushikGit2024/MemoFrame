"""Atomic per-workspace GUI preferences stored as JSON inside the workspace."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_bytes(target: Path, payload: bytes) -> None:
    """Write bytes to a temp file in the same directory then atomically replace target."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


class Prefs:
    """Read and atomically persist UI preferences in workspace/gui_prefs.json."""

    def __init__(self, workspace: Path) -> None:
        self.path = Path(workspace) / "gui_prefs.json"
        self._data: dict[str, Any] = {}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._data = loaded
        except (OSError, ValueError):
            pass

    def all(self) -> dict[str, Any]:
        return dict(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> dict[str, Any]:
        if self._data.get(key) == value:
            return dict(self._data)
        self._data[key] = value
        atomic_write_bytes(self.path, json.dumps(self._data, indent=2).encode("utf-8"))
        return dict(self._data)
