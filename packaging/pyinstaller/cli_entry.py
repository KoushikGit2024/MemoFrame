"""Entry point for the packaged standalone CLI engine."""

import multiprocessing
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2] / "services" / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from memoframe_engine.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
