"""Engine package: the public API for the Windows app."""

from memoframe_engine.api.engine import Engine
from memoframe_engine.core.contract import API_VERSION
from memoframe_engine.core.errors import EngineError, ErrorCode
from memoframe_engine.domains.pipeline.control import ProgressEvent

__all__ = ["API_VERSION", "Engine", "EngineError", "ErrorCode", "ProgressEvent"]
