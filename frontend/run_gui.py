"""MemoFrame Desktop GUI Launcher."""
import os
import sys
from pathlib import Path

# On Windows, register unique AppUserModelID so taskbar displays MemoFrame correctly
if os.name == "nt":
    try:
        import ctypes
        app_id = "MemoFrame.PhotoOrganizer.Desktop.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

# Add frontend and backend to sys.path so engine and gui are cleanly resolvable
FRONTEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = FRONTEND_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"

for p in (FRONTEND_DIR, BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gui.main_window import main

if __name__ == "__main__":
    sys.exit(main())
