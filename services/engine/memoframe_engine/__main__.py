"""Run the engine as a child process of the app.

    python -m engine run --workspace W --input D [--profile gentle] [--retry-failed]
    python -m engine doctor --workspace W [--input D ...]
    python -m engine version
    python -m engine diagnostics --workspace W

stdout: one JSON object per line.
    {"type":"progress", "stage":..., "done":..., "total":..., "failed":..., "current":..., "message":...}
    {"type":"done", "processed":..., "failed":..., "remaining":..., "interrupted":..., "stats":{...}}
    {"type":"doctor", "ok":..., "checks":[...]}
    {"type":"version", "api_version":..., "methods":[...]}
    {"type":"diagnostics", "path":...}
    {"type":"error", "code":..., "message":..., "hint":...}
stdin: send a line ``cancel``, ``pause`` or ``resume``.
Logs go to stderr and to the workspace log file, never to stdout.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
import threading
from pathlib import Path

from memoframe_engine.api.engine import Engine
from memoframe_engine.core.contract import API_VERSION, describe
from memoframe_engine.core.errors import EngineError
from memoframe_engine.utils.logger import setup_logging


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _listen(engine: Engine) -> None:
    if sys.stdin is None:
        return
    for line in sys.stdin:
        command = line.strip().lower()
        if command == "cancel":
            engine.cancel()
        elif command == "pause":
            engine.pause()
        elif command == "resume":
            engine.resume()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    run = sub.add_parser("run")
    run.add_argument("--workspace", type=Path, required=True)
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--profile", choices=["gentle", "balanced", "fast"], default=None)
    run.add_argument("--retry-failed", action="store_true")
    rescan = sub.add_parser("rescan")
    rescan.add_argument("--workspace", type=Path, required=True)
    rescan.add_argument("--input", type=Path, default=None)
    rescan.add_argument("--profile", choices=["gentle", "balanced", "fast"], default=None)
    rescan.add_argument("--retry-failed", action="store_true")
    doc = sub.add_parser("doctor")
    doc.add_argument("--workspace", type=Path, required=True)
    doc.add_argument("--input", type=Path, action="append", default=[])
    diag = sub.add_parser("diagnostics")
    diag.add_argument("--workspace", type=Path, required=True)
    args = ap.parse_args(argv)

    for stream in (sys.stdin, sys.stdout, sys.stderr):  # pipes default to a legacy code page
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    if args.cmd == "version":
        _emit(
            {"type": "version", "api_version": API_VERSION, "methods": describe(Engine)["methods"]}
        )
        return 0

    setup_logging(args.workspace / "photo_organizer.log", quiet=True)
    try:
        with Engine(
            args.workspace,
            profile=getattr(args, "profile", None),
            on_event=lambda ev: _emit({"type": "progress", **ev.to_dict()}),
        ) as eng:
            if args.cmd == "doctor":
                _emit({"type": "doctor", **eng.doctor(args.input)})
                return 0
            if args.cmd == "diagnostics":
                _emit({"type": "diagnostics", "path": eng.export_diagnostics()})
                return 0
            threading.Thread(target=_listen, args=(eng,), daemon=True).start()
            if args.cmd == "rescan":
                result = eng.rescan(args.input, retry_failed=args.retry_failed)
            else:
                result = eng.run_all(args.input, retry_failed=args.retry_failed)
            _emit({"type": "done", **result})
            return 130 if result["interrupted"] else 0
    except EngineError as exc:
        _emit({"type": "error", **exc.to_dict()})
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
