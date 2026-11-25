"""Tiny per-workspace GUI preferences (JSON file inside the workspace)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.file_utils import atomic_write_bytes


class Prefs:
    def __init__(self, workspace: Path) -> None:
        self.path = Path(workspace) / "gui_prefs.json"
        self._data: dict[str, Any] = {}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._data = loaded
        except (OSError, ValueError):
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if self._data.get(key) == value:
            return
        self._data[key] = value
        try:
            atomic_write_bytes(self.path, json.dumps(self._data, indent=2).encode("utf-8"))
        except OSError:
            pass
