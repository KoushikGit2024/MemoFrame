"""MemoFrame: Local, offline-first photo organizer and facial/scene analysis engine."""
import sys
from pathlib import Path

# Ensure backend root is always on sys.path when imported as a package
_BACKEND_ROOT = str(Path(__file__).resolve().parent)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from .engine.api import Engine
from .engine.contract import API_VERSION
from .engine.errors import EngineError, ErrorCode
from .services.pipeline.control import ProgressEvent

__all__ = ["API_VERSION", "Engine", "EngineError", "ErrorCode", "ProgressEvent"]
