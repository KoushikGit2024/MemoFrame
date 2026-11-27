"""Entry point: ``python main.py <command> ...`` (see ``python main.py --help``)."""

from __future__ import annotations

import sys
from multiprocessing import freeze_support
from pathlib import Path

# Add src and src/memoframe to sys.path so both 'memoframe.x' and local relative imports work seamlessly
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memoframe_engine.cli.cli import main

if __name__ == "__main__":
    freeze_support()  # required for multiprocessing on Windows
    sys.exit(main())
