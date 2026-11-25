"""MemoFrame Desktop GUI Launcher."""
from __future__ import annotations

import logging
import multiprocessing
import os
import sys
import threading
import traceback
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent
BACKEND_DIR = FRONTEND_DIR.parent / "backend"
for _p in (FRONTEND_DIR, BACKEND_DIR):          # cheap; also needed in spawned workers
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def run() -> int:
    """Everything here must happen once, in the GUI process only (never in workers)."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "MemoFrame.PhotoOrganizer.Desktop.1.0")
        except Exception:
            pass

    from config import DEFAULT_WORKSPACE
    from utils.logger import install_crash_logging, setup_logging

    workspace = DEFAULT_WORKSPACE
    setup_logging(workspace / "photo_organizer.log")
    install_crash_logging(workspace)
    log = logging.getLogger("photo_organizer.gui")

    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
    from PyQt6.QtWidgets import QApplication, QMessageBox

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }
    qInstallMessageHandler(lambda t, ctx, msg: log.log(levels.get(t, logging.WARNING), "Qt: %s", msg))

    base_hook = sys.excepthook

    def dialog_hook(exc_type, exc, tb):
        base_hook(exc_type, exc, tb)
        if QApplication.instance() and not issubclass(exc_type, KeyboardInterrupt):
            box = QMessageBox(QMessageBox.Icon.Warning, "Something went wrong",
                              f"{exc_type.__name__}: {exc}\n\nDetails were saved to:\n"
                              f"{workspace / 'photo_organizer.log'}")
            box.setDetailedText("".join(traceback.format_exception(exc_type, exc, tb)))
            box.exec()

    sys.excepthook = dialog_hook
    threading.excepthook = lambda a: dialog_hook(a.exc_type, a.exc_value, a.exc_traceback)

    from gui.main_window import main
    try:
        code = main(workspace=workspace)
    except BaseException:
        log.critical("Fatal error during startup/run", exc_info=True)
        raise
    log.info("Exited with code %s", code)
    return code


if __name__ == "__main__":
    multiprocessing.freeze_support()            # required: workers re-launch this program
    sys.exit(run())
