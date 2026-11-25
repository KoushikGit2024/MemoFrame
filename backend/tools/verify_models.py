"""Print model hashes next to the pins in config.py:  python tools/verify_models.py [workspace]"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    DEFAULT_WORKSPACE,
    SFACE_FILENAME,
    SFACE_SHA256,  # noqa: E402
    YUNET_FILENAME,
    YUNET_SHA256,
    Settings,
)
from utils.file_utils import sha256_file  # noqa: E402


def main() -> int:
    ws = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WORKSPACE
    s, bad = Settings(workspace=ws.resolve()), 0
    for name, pin in ((YUNET_FILENAME, YUNET_SHA256), (SFACE_FILENAME, SFACE_SHA256)):
        path = s.models_dir / name
        if not path.is_file():
            print(f"{name}: missing")
            continue
        digest = sha256_file(path)
        match = bool(pin) and digest.lower() == pin.lower()
        bad += not match
        print(f"{name}\n  file: {digest}\n  pin : {pin}\n  -> {'MATCH' if match else 'DIFFERENT'}")
    print("\nCompare the file hash with the official opencv_zoo release before changing a pin.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
