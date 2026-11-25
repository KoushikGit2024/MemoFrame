"""Smoke-test a packaged engine:  python tools/packaged_smoke.py dist/photo_engine/photo_engine.exe"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


def run(exe: str, *args: str) -> tuple[int, list[dict]]:
    p = subprocess.run([exe, *args], capture_output=True, timeout=600)
    lines = [json.loads(l) for l in p.stdout.decode("utf-8").splitlines() if l.strip()]
    return p.returncode, lines


def main(exe: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root, ws = Path(tmp) / "фото", Path(tmp) / "ws"
        root.mkdir()
        for i in range(3):
            Image.new("RGB", (640, 480), (i * 80, 50, 120)).save(root / f"ছবি{i}.jpg")
        code, out = run(exe, "version")
        assert code == 0 and out[-1]["type"] == "version", out
        print("version:", out[-1]["api_version"])
        code, out = run(exe, "doctor", "--workspace", str(ws))
        assert out[-1]["type"] == "doctor", out
        print(
            "doctor:", [(c["name"], c["status"]) for c in out[-1]["checks"] if c["status"] != "ok"]
        )
        code, out = run(
            exe, "run", "--workspace", str(ws), "--input", str(root), "--profile", "gentle"
        )
        print("run exit code:", code, "| last event:", out[-1])
        assert out[-1]["type"] in ("done", "error"), out
        if out[-1]["type"] == "done":
            assert out[-1]["processed"] == 3, out[-1]
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
