"""Clean all Python cache files (__pycache__, *.pyc, *.pyo, .pytest_cache) in the repository.
Leaves the entire workspace directory (database, models, thumbnails, crops, config) completely untouched.

Usage:
    python clear_cache.py
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def human_size(n_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def purge_pycache() -> tuple[int, int, int]:
    """Recursively delete all __pycache__ directories, *.pyc files, and .pytest_cache.
    Skips the workspace directory completely.
    """
    cleaned_dirs = 0
    cleaned_files = 0
    total_bytes = 0

    workspace_dir = REPO_ROOT / "workspace"

    for root, dirs, files in os.walk(REPO_ROOT, topdown=False):
        current_path = Path(root)

        # Skip entire workspace directory
        if workspace_dir in current_path.parents or current_path == workspace_dir:
            continue

        # Skip node_modules and .git for speed
        if "node_modules" in current_path.parts or ".git" in current_path.parts:
            continue

        # Check files for .pyc or .pyo
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                fp = current_path / f
                try:
                    total_bytes += fp.stat().st_size
                    fp.unlink()
                    cleaned_files += 1
                except OSError:
                    pass

        # Check directories for __pycache__ or .pytest_cache
        for d in dirs:
            if d == "__pycache__" or d == ".pytest_cache":
                dp = current_path / d
                try:
                    for sub_file in dp.rglob("*"):
                        if sub_file.is_file():
                            total_bytes += sub_file.stat().st_size
                            cleaned_files += 1
                    shutil.rmtree(dp, ignore_errors=True)
                    cleaned_dirs += 1
                except OSError:
                    pass

    return cleaned_dirs, cleaned_files, total_bytes


def main() -> None:
    print("=" * 60)
    print(" MemoFrame Python Cache Cleanup Tool")
    print(" (Preserves workspace, photos.db, models, and config)")
    print("=" * 60)

    dirs_cleaned, files_cleaned, bytes_freed = purge_pycache()

    print(f"Removed {dirs_cleaned} cache directories (__pycache__ / .pytest_cache)")
    print(f"Deleted {files_cleaned} compiled files (.pyc / .pyo)")
    print(f"Freed space: {human_size(bytes_freed)}")
    print("-" * 60)
    print("Workspace preserved intact: workspace/ untouched.")
    print("=" * 60)


if __name__ == "__main__":
    main()
