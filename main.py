"""Entry point: ``python main.py <command> ...`` (see ``python main.py --help``)."""
from __future__ import annotations

import sys
from multiprocessing import freeze_support

from cli import main

if __name__ == "__main__":
    freeze_support()          # required for multiprocessing on Windows
    sys.exit(main())