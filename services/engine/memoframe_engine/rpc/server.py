"""Stdio NDJSON-RPC bridge server connecting Electron to MemoFrame's Python Engine."""

from __future__ import annotations

import multiprocessing
import os
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, TextIO

from memoframe_engine.core.observability import ObservabilityStore
from memoframe_engine.rpc.handlers.analytics import register_analytics_handlers
from memoframe_engine.rpc.handlers.collections import register_collection_handlers
from memoframe_engine.rpc.handlers.errors import register_error_handlers
from memoframe_engine.rpc.handlers.library import register_library_handlers
from memoframe_engine.rpc.handlers.people import register_people_handlers
from memoframe_engine.rpc.handlers.system import register_system_handlers
from memoframe_engine.rpc.prefs import Prefs
from memoframe_engine.rpc.protocol import (
    BridgeError,
    decode_line,
    encode_line,
    make_err,
    make_event,
    make_ok,
)


class BridgeContext:
    """Shared state, ObservabilityStore, and Engine lifecycle for all RPC handlers."""

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
        self.observability = ObservabilityStore(self.workspace)
        self.lock = threading.RLock()
        self.scan_thread: threading.Thread | None = None
        self._emit_fn = emit_fn or (lambda _ev, _data: None)

        if backend_error:
            self.observability.record_error(
                origin="backend",
                category="startup",
                module="rpc.server",
                message=backend_error,
                severity="critical",
                code="BACKEND_INIT_FAILED",
                recovery_class="dev_action",
            )

    def require_engine(self) -> Any:
        if self.engine is None:
            raise BridgeError(
                "BACKEND_NOT_CONNECTED",
                self.backend_error or "Python backend engine is not connected.",
                "Ensure MemoFrame's engine dependencies are installed in the active Python environment.",
            )
        return self.engine

    def emit_event(self, event: str, data: Any) -> None:
        self._emit_fn(event, data)

    def close(self) -> None:
        if self.engine is not None:
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
        self.observability.close()


def build_registry(ctx: BridgeContext) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Assemble the complete RPC method dispatch table."""
    registry: dict[str, Callable[[dict[str, Any]], Any]] = {}
    register_library_handlers(registry, ctx)
    register_people_handlers(registry, ctx)
    register_collection_handlers(registry, ctx)
    register_system_handlers(registry, ctx)
    register_analytics_handlers(registry, ctx)
    register_error_handlers(registry, ctx)
    return registry


class BridgeServer:
    """Concurrent NDJSON-RPC server with per-request correlation, latency metrics, and error capture."""

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
                if hasattr(self._out, "buffer"):
                    self._out.buffer.write(line.encode("utf-8"))
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
        method = "unknown"
        corr_id = f"srv-{uuid.uuid4().hex[:10]}"
        t0 = time.perf_counter()
        try:
            req = decode_line(raw_line)
            req_id = req.get("id")
            method = str(req["method"])
            params = dict(req.get("params") or {})
            if params.get("_correlation_id"):
                corr_id = str(params.pop("_correlation_id"))
            result = self.dispatch(method, params)
            dur_ms = (time.perf_counter() - t0) * 1000.0
            if not method.startswith("analytics.") and method != "errors.report":
                self.ctx.observability.record_rpc_metric(corr_id, method, "ok", dur_ms)
            return make_ok(req_id, result)
        except Exception as exc:
            dur_ms = (time.perf_counter() - t0) * 1000.0
            err_code = getattr(exc, "code", exc.__class__.__name__)
            self.ctx.observability.record_rpc_metric(corr_id, method, "error", dur_ms, str(err_code))
            if method != "errors.report":
                rec = self.ctx.observability.record_error(
                    origin="bridge" if isinstance(exc, BridgeError) else "backend",
                    category="rpc",
                    module=method,
                    code=str(err_code),
                    message=str(exc),
                    severity="warning" if isinstance(exc, BridgeError) else "error",
                    stack_trace="" if isinstance(exc, BridgeError) else traceback.format_exc(),
                    correlation_id=corr_id,
                    context={"method": method, "duration_ms": round(dur_ms, 2)},
                )
                self.emit_event("error.captured", {"error": rec})
            return make_err(req_id, exc)

    def serve(self, in_stream: TextIO | None = None) -> None:
        stream = in_stream or sys.stdin
        self.emit_event("bridge.ready", {"connected": self.ctx.engine is not None})
        pool = ThreadPoolExecutor(
            max_workers=min(16, (os.cpu_count() or 2) * 2),
            thread_name_prefix="MemoFrameRPC",
        )
        try:
            for raw in stream:
                line = raw.strip()
                if not line:
                    continue
                pool.submit(lambda raw_msg=line: self._write(self.handle_line(raw_msg)))
        finally:
            pool.shutdown(wait=True, cancel_futures=False)
            self.ctx.close()


def _default_writable_workspace() -> Path:
    env_ws = os.environ.get("MEMOFRAME_WORKSPACE", "").strip()
    if env_ws:
        return Path(env_ws).resolve()
    if getattr(sys, "frozen", False):
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        else:
            base = Path.home() / ".local" / "share"
        return (base / "MemoFrame" / "workspace").resolve()
    return (Path(__file__).resolve().parents[4] / "workspace").resolve()


def _resolve_backend_and_open() -> BridgeContext:
    default_ws = _default_writable_workspace()
    try:
        from memoframe_engine.api import Engine
        from memoframe_engine.core.config import DEFAULT_WORKSPACE

        env_ws = os.environ.get("MEMOFRAME_WORKSPACE", "").strip()
        workspace = (
            Path(env_ws).resolve()
            if env_ws
            else (default_ws if getattr(sys, "frozen", False) else Path(DEFAULT_WORKSPACE).resolve())
        )
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
    multiprocessing.freeze_support()
    raise SystemExit(main())
