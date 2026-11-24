"""Stable error codes for the app, and translation of internal exceptions."""
from __future__ import annotations

import sqlite3
from enum import Enum


class ErrorCode(str, Enum):
    DRIVE_OFFLINE = "DRIVE_OFFLINE"
    MODEL_MISSING = "MODEL_MISSING"
    MODEL_DOWNLOAD_FAILED = "MODEL_DOWNLOAD_FAILED"
    DETECTOR_UNAVAILABLE = "DETECTOR_UNAVAILABLE"
    TAGGER_UNAVAILABLE = "TAGGER_UNAVAILABLE"
    CONFIG_INVALID = "CONFIG_INVALID"
    DB_ERROR = "DB_ERROR"
    WORKER_CRASH = "WORKER_CRASH"
    INVALID_INPUT = "INVALID_INPUT"
    IO_ERROR = "IO_ERROR"
    NOT_OPEN = "NOT_OPEN"
    WORKSPACE_LOCKED = "WORKSPACE_LOCKED"
    UNKNOWN = "UNKNOWN"


class EngineError(Exception):
    """An error the app can show: stable ``code``, readable ``message``, optional ``hint``."""

    def __init__(self, code: ErrorCode, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message, "hint": self.hint}


def translate(exc: BaseException) -> EngineError:
    """Map any internal exception to an :class:`EngineError`."""
    from memoframe.core.face_detector import DetectorUnavailableError
    from memoframe.core.tagger import TaggerUnavailableError
    from memoframe.database import DatabaseError
    from memoframe.processing.pipeline import PipelineError
    from memoframe.utils.model_downloader import ModelDownloadError
    from memoframe.utils.validators import ValidationError

    text = str(exc)
    if isinstance(exc, EngineError):
        return exc
    if isinstance(exc, ModelDownloadError):
        return EngineError(ErrorCode.MODEL_DOWNLOAD_FAILED, text,
                           "Check the internet connection once, or place the model file manually.")
    if isinstance(exc, TaggerUnavailableError):
        return EngineError(ErrorCode.TAGGER_UNAVAILABLE, text,
                           "Check the tag model and labels files (run doctor).")
    if isinstance(exc, DetectorUnavailableError):
        code = ErrorCode.MODEL_MISSING if "not found" in text else ErrorCode.DETECTOR_UNAVAILABLE
        return EngineError(code, text, "Run the environment check (doctor).")
    if isinstance(exc, PipelineError):
        if "Folder not found" in text:
            return EngineError(ErrorCode.DRIVE_OFFLINE, text, "Reconnect the drive and try again.")
        return EngineError(ErrorCode.WORKER_CRASH, text, "Use the gentle profile or fewer workers.")
    if isinstance(exc, (DatabaseError, sqlite3.Error)):
        return EngineError(ErrorCode.DB_ERROR, text)
    if isinstance(exc, (ValidationError, ValueError, TypeError)):
        return EngineError(ErrorCode.INVALID_INPUT, text)
    if isinstance(exc, FileNotFoundError):
        return EngineError(ErrorCode.DRIVE_OFFLINE, text, "Is the drive connected?")
    if isinstance(exc, OSError):
        return EngineError(ErrorCode.IO_ERROR, text)
    return EngineError(ErrorCode.UNKNOWN, f"{type(exc).__name__}: {text}")
