"""MemoFrame Engine — local photo & face intelligence."""

from __future__ import annotations

from typing import Any

__all__ = ["Engine"]


def __getattr__(name: str) -> Any:
    if name == "Engine":
        from memoframe_engine.api.engine import Engine
        return Engine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
