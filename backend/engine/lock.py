"""Exclusive workspace lock so two processes can't use one database."""
from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from engine.errors import EngineError, ErrorCode


class WorkspaceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh: BinaryIO | None = None

    def __enter__(self) -> WorkspaceLock:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()

    def acquire(self) -> None:
        if self._fh is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            fh.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise EngineError(ErrorCode.WORKSPACE_LOCKED,
                              f"This workspace is already open in another window or process: "
                              f"{self.path.parent}",
                              "Close the other instance and try again.") from exc
        self._fh = fh

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            self._fh.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._fh.close()
            self._fh = None
