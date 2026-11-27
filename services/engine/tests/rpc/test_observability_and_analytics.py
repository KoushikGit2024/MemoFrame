"""Functional and failure-simulation tests for ObservabilityStore, Analytics, Self-Healing & Timeline."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from memoframe_engine.core.observability import ObservabilityStore, make_fingerprint, redact_sensitive
from memoframe_engine.db.migrations import LATEST_VERSION, migrate
from memoframe_engine.rpc.handlers.collections import register_collection_handlers


def test_secret_and_path_redaction() -> None:
    raw = r"Auth failed token=supersecret123 Bearer abc.def.ghi at C:\Users\Rishabh\Photos\img.jpg"
    clean = redact_sensitive(raw)
    assert "supersecret123" not in clean
    assert "abc.def.ghi" not in clean
    assert "Rishabh" not in clean
    assert "<user>" in clean


def test_error_dedup_correlation_and_recovery_policy(tmp_path: Path) -> None:
    store = ObservabilityStore(tmp_path)
    try:
        # Fingerprinting normalizes volatile numbers
        assert make_fingerprint("frontend", "rpc", "photos.query", "Timeout 1234ms") == make_fingerprint(
            "frontend", "rpc", "photos.query", "Timeout 9876ms"
        )

        # Record two occurrences of same error + one correlated frontend error
        e1 = store.record_error(
            origin="backend",
            category="database_transient",
            module="photos.query",
            message="database is locked on row 101",
            correlation_id="corr-chain-1",
        )
        e2 = store.record_error(
            origin="backend",
            category="database_transient",
            module="photos.query",
            message="database is locked on row 205",
            correlation_id="corr-chain-1",
        )
        assert e1["id"] == e2["id"]
        assert e2["occurrence_count"] == 2
        assert e2["recovery_class"] == "auto_recoverable"

        fe = store.record_error(
            origin="frontend",
            category="rpc_failure",
            module="photos.query",
            message="Backend request failed after retries",
            correlation_id="corr-chain-1",
        )
        detail = store.get_error_detail(e1["id"])
        assert detail is not None
        assert len(detail["occurrences"]) == 2
        assert any(r["id"] == fe["id"] for r in detail["related"])

        # Controlled recovery succeeds and preserves original error record
        attempt = store.execute_recovery(
            e1["id"], "ensure_workspace_dirs", "manual", lambda: "Directories verified"
        )
        assert attempt["outcome"] == "succeeded"
        detail2 = store.get_error_detail(e1["id"])
        assert detail2 is not None
        assert detail2["error"]["status"] == "recovered"
        assert len(detail2["recoveries"]) == 1

        # Lifecycle transition to resolved + notes
        updated = store.update_error_status(e1["id"], "resolved", notes="Verified WAL checkpoint")
        assert updated is not None
        assert updated["status"] == "resolved"
        assert updated["notes"] == "Verified WAL checkpoint"
    finally:
        store.close()


def test_migration_v12_idempotent(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "photos.db"
    conn = sqlite3.connect(str(db_path))
    try:
        v = migrate(conn, str(db_path))
        assert v == LATEST_VERSION == 12
        # Running again is a safe no-op
        assert migrate(conn, str(db_path)) == 12
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(groups)")}
        assert "idx_groups_start_ts" in indexes
    finally:
        conn.close()


def test_timeline_utc_ordering_dedup_and_invalid_timestamps() -> None:
    class _StubEngine:
        def get_groups(self):
            return [
                {"id": 1, "name": "Invalid Date Event", "start_ts": "not-a-date", "end_ts": None, "image_count": 2},
                {"id": 2, "name": "IST Afternoon", "start_ts": "2026-05-01T15:30:00+05:30", "end_ts": None, "image_count": 3},
                {"id": 3, "name": "UTC Later", "start_ts": "2026-05-01T11:00:00Z", "end_ts": None, "image_count": 4},
                {"id": 4, "name": "EXIF Tie A", "start_ts": "2026-05-01 10:00:00", "end_ts": None, "image_count": 1},
                {"id": 5, "name": "EXIF Tie B", "start_ts": "2026-05-01:10:00:00".replace(":10", " 10"), "end_ts": None, "image_count": 1},
                {"id": 3, "name": "UTC Later Duplicate", "start_ts": "2026-05-01T11:00:00Z", "end_ts": None, "image_count": 4},
            ]

        def get_group_images(self, _gid: int, limit: int = 8):
            return []

    import threading

    class _StubCtx:
        lock = threading.RLock()
        engine = _StubEngine()

        def require_engine(self):
            return self.engine

    reg = {}
    register_collection_handlers(reg, _StubCtx())
    res = reg["timeline.groups"]({"limit": 20, "offset": 0, "order": "desc"})
    ids = [g["id"] for g in res["groups"]]
    # Deduplicated (5 unique), UTC Later (11:00Z) > Tie B/A & IST (10:00Z, tie-broken by id desc: 5, 4, 2), Invalid Date last (1)!
    assert ids == [3, 5, 4, 2, 1], f"Unexpected timeline order: {ids}"
    assert res["groups"][-1]["timestamp_valid"] is False

    # Date-range filter excludes undated/invalid
    filtered = reg["timeline.groups"]({"date_from": "2026-05-01", "date_to": "2026-05-01", "order": "asc"})
    assert [g["id"] for g in filtered["groups"]] == [2, 4, 5, 3]


def test_live_rpc_observability_and_failure_simulation(tmp_path: Path) -> None:
    eng_root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": str(eng_root), "MEMOFRAME_WORKSPACE": str(tmp_path)}

    # Create a stale .tmp model file to test safe self-healing recovery
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    stale_tmp = models_dir / "sface.tmp"
    stale_tmp.write_bytes(b"partial")

    proc = subprocess.Popen(
        [sys.executable, "-m", "memoframe_engine.rpc.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    reqs = [
        {"id": 1, "method": "system.init", "params": {"_correlation_id": "sim-1"}},
        {"id": 2, "method": "nonexistent.method", "params": {"_correlation_id": "sim-err"}},
        {
            "id": 3,
            "method": "errors.report",
            "params": {
                "origin": "frontend",
                "category": "model_download",
                "module": "ModelDownloadScreen",
                "message": "Model download interrupted leaving .tmp file",
                "severity": "error",
                "correlation_id": "sim-err",
            },
        },
        {"id": 4, "method": "prefs.set", "params": {"key": "timezone", "value": "Asia/Kolkata"}},
        {"id": 5, "method": "analytics.overview", "params": {"range": "all"}},
        {"id": 6, "method": "analytics.activity", "params": {"range": "all"}},
        {"id": 7, "method": "analytics.errors", "params": {"range": "all"}},
        {"id": 8, "method": "analytics.performance", "params": {"range": "all"}},
        {"id": 9, "method": "analytics.export", "params": {"format": "csv", "range": "all"}},
        {"id": 10, "method": "errors.list", "params": {"range": "all"}},
        {"id": 11, "method": "system.audit_log", "params": {"limit": 10}},
    ]
    raw_in = "".join(json.dumps(r) + "\n" for r in reqs)
    out, err = proc.communicate(raw_in, timeout=20)
    assert not err.strip(), f"Unexpected stderr: {err}"

    msgs = [json.loads(line) for line in out.splitlines() if line.strip()]
    resps = {m["id"]: m for m in msgs if "id" in m}
    assert resps[1]["ok"] is True
    assert resps[2]["ok"] is False  # intentional failure captured!
    assert resps[3]["ok"] is True
    reported_id = resps[3]["result"]["error"]["id"]
    assert resps[4]["ok"] is True
    assert resps[5]["ok"] is True and resps[5]["result"]["rpc"]["total_requests"] >= 2
    assert resps[6]["ok"] is True
    assert resps[7]["ok"] is True and resps[7]["result"]["unresolved_count"] >= 2
    assert resps[8]["ok"] is True and len(resps[8]["result"]["latency_histogram"]) == 5
    assert resps[9]["ok"] is True and "section,metric,value" in resps[9]["result"]["content"]
    assert resps[10]["ok"] is True and len(resps[10]["result"]["items"]) >= 2
    assert resps[11]["ok"] is True and any(r["key"] == "prefs.timezone" for r in resps[11]["result"]["items"])

    # Trigger safe recovery on reported model error and confirm stale .tmp is cleaned!
    proc2 = subprocess.Popen(
        [sys.executable, "-m", "memoframe_engine.rpc.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    out2, err2 = proc2.communicate(
        json.dumps({"id": 20, "method": "errors.recover", "params": {"error_id": reported_id, "strategy": "auto"}}) + "\n",
        timeout=15,
    )
    assert not err2.strip()
    r20 = [json.loads(l) for l in out2.splitlines() if l.strip() and '"id": 20' in l][0]
    assert r20["ok"] is True
    assert r20["result"]["attempt"]["outcome"] == "succeeded"
    assert not stale_tmp.exists()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        test_secret_and_path_redaction()
        test_error_dedup_correlation_and_recovery_policy(base / "obs")
        test_migration_v12_idempotent(base / "mig")
        test_timeline_utc_ordering_dedup_and_invalid_timestamps()
        test_live_rpc_observability_and_failure_simulation(base / "rpc")
    print("ALL OBSERVABILITY, ANALYTICS, SELF-HEALING & TIMELINE TESTS PASSED!")
