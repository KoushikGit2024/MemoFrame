"""Entry point for the packaged engine (python -m engine does not exist in a frozen build)."""
import multiprocessing
import sys
from pathlib import Path

# Ensure src and src/memoframe are in sys.path when running from source
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()      # required: workers are re-launches of this exe
    sys.exit(main())

