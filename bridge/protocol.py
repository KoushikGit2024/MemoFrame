"""NDJSON-RPC framing and error serialization for the Electron-Python bridge."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


class BridgeError(Exception):
    """Structured RPC error returned to the Electron frontend."""

    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "hint": self.hint}


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if isinstance(obj, set):
        return list(obj)
    return str(obj)


def encode_line(payload: dict[str, Any]) -> str:
    """Serialize a response or event dict as a single newline-delimited JSON line."""
    return json.dumps(payload, default=_json_default, ensure_ascii=True) + "\n"


def decode_line(raw: str) -> dict[str, Any]:
    """Parse a single NDJSON request line and validate minimal structure."""
    data = json.loads(raw)
    if not isinstance(data, dict) or "method" not in data:
        raise BridgeError("INVALID_REQUEST", "Request must be a JSON object with a 'method' field.")
    return data


def make_ok(req_id: Any, result: Any) -> dict[str, Any]:
    return {"id": req_id, "ok": True, "result": result}


def make_err(req_id: Any, exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, BridgeError):
        err = exc.to_dict()
    elif hasattr(exc, "to_dict") and callable(exc.to_dict):
        raw = exc.to_dict()
        err = {
            "code": str(raw.get("code", exc.__class__.__name__)),
            "message": str(raw.get("message", str(exc))),
            "hint": str(raw.get("hint", "")),
        }
    else:
        err = {
            "code": exc.__class__.__name__,
            "message": str(exc) or exc.__class__.__name__,
            "hint": str(getattr(exc, "hint", "") or ""),
        }
    return {"id": req_id, "ok": False, "error": err}


def make_event(event: str, data: Any) -> dict[str, Any]:
    return {"event": event, "data": data}
