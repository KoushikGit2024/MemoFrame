"""Shared fixtures: synthetic images, temporary settings, in-memory database."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # fallback if pytest.ini is ignored
    sys.path.insert(0, str(ROOT))

from memoframe_engine.core.config import Settings  # noqa: E402
from memoframe_engine.db import DatabaseManager  # noqa: E402


@pytest.fixture
def make_image():
    """Factory ``make(path, seed=0, size=(300, 200))`` -> path.

    Different seeds give visually different images (random colour blocks);
    the same seed gives identical pixels. Format follows the file suffix.
    """

    def _make(path: Path, seed: int = 0, size: tuple[int, int] = (300, 200)) -> Path:
        rng = np.random.default_rng(seed)
        block = rng.integers(0, 256, (4, 6, 3), dtype=np.uint8)
        image = Image.fromarray(block).resize(size, Image.Resampling.NEAREST)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return path

    return _make


@pytest.fixture
def db():
    """Fresh in-memory database."""
    manager = DatabaseManager(":memory:").open()
    yield manager
    manager.close()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Single-process settings with a small batch size and a temp workspace."""
    return Settings(workspace=tmp_path / "ws", workers=1, batch_size=2)
