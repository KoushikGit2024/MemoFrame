"""Public API version. MAJOR = breaking change, MINOR = new methods or fields."""
from __future__ import annotations

import inspect

API_VERSION = "1.2.0"
EVENT_FIELDS = ("stage", "done", "total", "failed", "current", "message")


def describe(engine_cls: type) -> dict:
    """Version and the sorted list of public methods of the engine class."""
    return {"api_version": API_VERSION,
            "methods": sorted(n for n, v in vars(engine_cls).items()
                              if inspect.isfunction(v) and not n.startswith("_"))}
