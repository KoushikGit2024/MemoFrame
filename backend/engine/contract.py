"""Public API version. MAJOR = breaking change, MINOR = new methods or fields."""

from __future__ import annotations

import inspect

API_VERSION = "1.2.0"
EVENT_FIELDS = ("stage", "done", "total", "failed", "current", "message")


def describe(engine_cls: type) -> dict:
    """Version and the sorted list of public methods of the engine class."""
    methods = set()
    for cls in engine_cls.__mro__:
        if cls is object:
            continue
        for n, v in vars(cls).items():
            if (inspect.isfunction(v) or inspect.ismethod(v)) and not n.startswith("_"):
                methods.add(n)
    return {"api_version": API_VERSION, "methods": sorted(methods)}
