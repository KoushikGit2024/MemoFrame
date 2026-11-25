"""Stdio NDJSON-RPC bridge server connecting Electron to MemoFrame's Python Engine."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, TextIO

from bridge.handlers_collections import register_collection_handlers
from bridge.handlers_library import register_library_handlers
from bridge.handlers_people import register_people_handlers
from bridge.handlers_system import register_system_handlers
from bridge.prefs import Prefs
from bridge.protocol import BridgeError, decode_line, encode_line, make_err, make_event, make_ok


class BridgeContext:
    """Shared state and Engine lifecycle for all RPC handlers."""

    def __init__(
        self,
        workspace: Path,
        engine: Any | None = None,
        backend_error: str | None = None,
        emit_fn: Callable[[str, Any], None] | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.engine = engine
        self.backend_error = backend_error
        self.prefs = Prefs(self.workspace)
        self.lock = threading.RLock()
        self.scan_thread: threading.Thread | None = None
        self._emit_fn = emit_fn or (lambda _ev, _data: None)

    def require_engine(self) -> Any:
        if self.engine is None:
            raise BridgeError(
                "BACKEND_NOT_CONNECTED",
                self.backend_error or "Python backend engine is not connected.",
                "Ensure MemoFrame's backend/ dependencies are installed in the active Python environment.",
            )
        return self.engine

    def emit_event(self, event: str, data: Any) -> None:
        self._emit_fn(event, data)

    def close(self) -> None:
        if self.engine is None:
            return
        try:
            if self.scan_thread is not None and self.scan_thread.is_alive():
                self.engine.control.cancel()
                self.scan_thread.join(timeout=5.0)
        except Exception:
            pass
        with self.lock:
            try:
                self.engine.close()
            except Exception:
                pass
            self.engine = None


def build_registry(ctx: BridgeContext) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Assemble the complete RPC method dispatch table."""
    registry: dict[str, Callable[[dict[str, Any]], Any]] = {}
    register_library_handlers(registry, ctx)
    register_people_handlers(registry, ctx)
    register_collection_handlers(registry, ctx)
    register_system_handlers(registry, ctx)
    return registry


class BridgeServer:
    """Concurrent NDJSON-RPC server reading requests from stdin and writing responses to stdout."""

    def __init__(self, ctx: BridgeContext, out_stream: TextIO | None = None) -> None:
        self.ctx = ctx
        self._out = out_stream or sys.stdout
        self._write_lock = threading.Lock()
        self.ctx._emit_fn = self.emit_event
        self.registry = build_registry(self.ctx)

    def _write(self, payload: dict[str, Any]) -> None:
        line = encode_line(payload)
        with self._write_lock:
            try:
                if hasattr(self._out, 'buffer'):
                    self._out.buffer.write(line.encode('utf-8'))
                    self._out.buffer.flush()
                else:
                    self._out.write(line)
                    self._out.flush()
            except OSError:
                pass

    def emit_event(self, event: str, data: Any) -> None:
        self._write(make_event(event, data))

    def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        handler = self.registry.get(method)
        if handler is None:
            raise BridgeError("METHOD_NOT_FOUND", f"Unknown RPC method: {method}")
        return handler(params)

    def handle_line(self, raw_line: str) -> dict[str, Any]:
        req_id: Any = None
        try:
            req = decode_line(raw_line)
            req_id = req.get("id")
            result = self.dispatch(str(req["method"]), dict(req.get("params") or {}))
            return make_ok(req_id, result)
        except Exception as exc:
            return make_err(req_id, exc)

    def serve(self, in_stream: TextIO | None = None) -> None:
        stream = in_stream or sys.stdin
        self.emit_event("bridge.ready", {"connected": self.ctx.engine is not None})
        pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="MemoFrameRPC")
        try:
            for raw in stream:
                line = raw.strip()
                if not line:
                    continue
                pool.submit(lambda raw_msg=line: self._write(self.handle_line(raw_msg)))
        finally:
            pool.shutdown(wait=False)
            self.ctx.close()


def _find_backend_dir() -> Path | None:
    env_dir = os.environ.get("MEMOFRAME_BACKEND_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (repo_root / "backend", repo_root.parent / "backend"):
        if candidate.is_dir():
            return candidate.resolve()
    return None


def _resolve_backend_and_open() -> BridgeContext:
    backend_dir = _find_backend_dir()
    if backend_dir is not None and str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    env_ws = os.environ.get("MEMOFRAME_WORKSPACE")
    default_ws = Path(env_ws) if env_ws else (Path(__file__).resolve().parent.parent / "workspace")
    try:
        from config import DEFAULT_WORKSPACE
        from engine import Engine

        workspace = Path(env_ws or DEFAULT_WORKSPACE).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        engine = Engine(workspace, strict_config=False).open()
        return BridgeContext(workspace=workspace, engine=engine)
    except Exception as exc:
        return BridgeContext(
            workspace=default_ws,
            engine=None,
            backend_error=f"Backend unavailable ({exc.__class__.__name__}: {exc})",
        )


def main() -> int:
    ctx = _resolve_backend_and_open()
    server = BridgeServer(ctx)
    server.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
