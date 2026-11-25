"""Deterministic unit tests for bridge protocol, atomic prefs, and monotonic progress."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.prefs import Prefs
from bridge.progress import StageProgress, describe
from bridge.protocol import BridgeError, decode_line, encode_line, make_err, make_ok


def test_protocol_roundtrip_and_errors(tmp_path: Path) -> None:
    line = encode_line(make_ok(1, {"path": tmp_path / "a.jpg", "tags": {"beach"}}))
    parsed = json.loads(line)
    assert parsed["id"] == 1
    assert parsed["ok"] is True
    assert parsed["result"]["path"].endswith("a.jpg")
    assert parsed["result"]["tags"] == ["beach"]

    req = decode_line('{"id": 7, "method": "system.stats", "params": {}}')
    assert req["method"] == "system.stats"

    raised = False
    try:
        decode_line('{"id": 2}')
    except BridgeError:
        raised = True
    assert raised, "Expected BridgeError for missing method field"

    err_payload = make_err(3, BridgeError("TEST_ERR", "Something failed", "Try again"))
    assert err_payload["ok"] is False
    assert err_payload["error"]["code"] == "TEST_ERR"
    assert err_payload["error"]["hint"] == "Try again"


def test_prefs_atomic_persistence(tmp_path: Path) -> None:
    prefs = Prefs(tmp_path)
    assert prefs.get("theme") is None
    prefs.set("theme", "Light Canvas")
    prefs.set("last_dark_theme", "Emerald Forest")

    reloaded = Prefs(tmp_path)
    assert reloaded.get("theme") == "Light Canvas"
    assert reloaded.get("last_dark_theme") == "Emerald Forest"
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".tmp_")]
    assert leftovers == []


def test_stage_progress_monotonic_and_describe() -> None:
    sp = StageProgress()
    p1 = sp.update({"stage": "scan", "done": 1, "total": 2})
    p2 = sp.update({"stage": "process", "done": 5, "total": 10})
    p3 = sp.update({"stage": "scan", "done": 0, "total": 2})
    p4 = sp.update({"stage": "index", "done": 1, "total": 1})

    assert 0 < p1 < p2
    assert p3 == p2
    assert p4 == 100

    label = describe({"stage": "process", "done": 3, "total": 10, "current": "IMG_001.jpg"})
    assert "Analysing photos: 3 of 10" in label
    assert "IMG_001.jpg" in label
