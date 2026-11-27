"""Input validation helpers, including argparse ``type=`` callables."""

from __future__ import annotations

import argparse
from pathlib import Path


class ValidationError(ValueError):
    """Raised when user-supplied input is invalid."""


def validate_input_dir(path: str | Path) -> Path:
    """Return the resolved directory, or raise :class:`ValidationError`."""
    p = Path(path).expanduser()
    if not p.exists():
        raise ValidationError(f"Input directory does not exist: {p}")
    if not p.is_dir():
        raise ValidationError(f"Input path is not a directory: {p}")
    return p.resolve()


def validate_range(value: float, name: str, low: float, high: float) -> float:
    """Check ``low <= value <= high``."""
    if not (low <= value <= high):
        raise ValidationError(f"{name} must be between {low} and {high}, got {value}")
    return value


def validate_positive_int(value: int, name: str) -> int:
    """Check ``value >= 1``."""
    if value < 1:
        raise ValidationError(f"{name} must be a positive integer, got {value}")
    return value


# ---- argparse adapters ---------------------------------------------------


def _wrap(func, *args):
    try:
        return func(*args)
    except ValidationError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def existing_dir(value: str) -> Path:
    """argparse type: an existing directory."""
    return _wrap(validate_input_dir, value)


def unit_float(value: str) -> float:
    """argparse type: float in [0, 1] (e.g. confidence thresholds)."""
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from exc
    return _wrap(validate_range, number, "value", 0.0, 1.0)


def positive_int(value: str) -> int:
    """argparse type: integer >= 1."""
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from exc
    return _wrap(validate_positive_int, number, "value")


def positive_float(value: str) -> float:
    """argparse type: float > 0."""
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0, got {number}")
    return number
