"""Multi-stage progress tracking for scanning and analysis."""
from __future__ import annotations

from typing import Any, Mapping

STAGE_WEIGHTS: dict[str, float] = {
    "scan": 0.05,
    "detect": 0.45,
    "embed": 0.20,
    "cluster": 0.10,
    "analyze": 0.10,
    "duplicates": 0.10,
}


class StageProgress:
    """Calculates overall progress percent (0-100) across pipeline stages."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or STAGE_WEIGHTS
        self._max_pct: float = 0.0

    def update(self, event: Mapping[str, Any]) -> int:
        stage = event.get("stage", "")
        done = int(event.get("done") or 0)
        total = int(event.get("total") or 0)

        # Sum completed prior stages
        base = 0.0
        stage_weight = 0.0
        found = False
        for s, w in self.weights.items():
            if s == stage:
                stage_weight = w
                found = True
                break
            base += w

        if not found or total <= 0:
            stage_fraction = 0.0
        else:
            stage_fraction = min(1.0, max(0.0, done / total))

        current_pct = (base + stage_fraction * stage_weight) * 100.0
        # Progress must never go backward
        self._max_pct = max(self._max_pct, current_pct)
        return min(100, int(round(self._max_pct)))

    def reset(self) -> None:
        self._max_pct = 0.0
