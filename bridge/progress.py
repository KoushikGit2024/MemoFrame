"""Multi-stage monotonic progress tracking for folder scanning and analysis."""
from __future__ import annotations

from typing import Any, Mapping

STAGE_WEIGHTS: dict[str, float] = {
    "scan": 0.05,
    "process": 0.75,
    "duplicates": 0.05,
    "places": 0.02,
    "bursts": 0.03,
    "groups": 0.04,
    "persons": 0.04,
    "index": 0.02,
}

STAGE_LABELS: dict[str, str] = {
    "scan": "Scanning folders",
    "process": "Analysing photos",
    "duplicates": "Finding duplicates",
    "places": "Naming places",
    "bursts": "Detecting bursts",
    "groups": "Grouping events",
    "persons": "Clustering people",
    "index": "Updating search index",
    "analyze": "Scoring quality",
    "tag": "Tagging scenes",
    "waiting": "Waiting",
}


def describe(ev: Mapping[str, Any]) -> str:
    """Format a human-readable single-line status string for a progress event."""
    stage = str(ev.get("stage", "") or "")
    name = STAGE_LABELS.get(stage, stage.title() if stage else "Working")
    done, total = int(ev.get("done") or 0), int(ev.get("total") or 0)
    if total:
        text = f"{name}: {done:,} of {total:,}"
    elif ev.get("message"):
        text = f"{name} — {ev['message']}"
    else:
        text = name
    return f"{text} · {ev['current']}" if ev.get("current") else text


class StepProgress:
    """Calculates step-wise progress percentage (0-100) that restarts for each pipeline stage."""

    def __init__(self) -> None:
        self.current_stage: str = ""
        self.current_pct: int = 0

    def update(self, event: Mapping[str, Any]) -> int:
        stage = str(event.get("stage", "") or "")
        done = int(event.get("done") or 0)
        total = int(event.get("total") or 0)

        # If a new stage starts, restart progress from 0
        if stage != self.current_stage:
            self.current_stage = stage
            self.current_pct = 0

        if total > 0:
            pct = int(min(100, max(0, (done / total) * 100)))
            self.current_pct = max(self.current_pct, pct)
        elif event.get("message") and "done" in str(event.get("message", "")).lower():
            self.current_pct = 100

        return self.current_pct

    def reset(self) -> None:
        self.current_stage = ""
        self.current_pct = 0


class StageProgress:
    """Calculates monotonic overall progress percentage (0-100) across pipeline stages."""

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        only: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        w = dict(weights or STAGE_WEIGHTS)
        if only:
            w = {k: v for k, v in w.items() if k in only} or {s: 1.0 for s in only}
        total = sum(w.values()) or 1.0
        self.weights = {k: v / total for k, v in w.items()}
        self._max_pct: float = 0.0

    def update(self, event: Mapping[str, Any]) -> int:
        stage = str(event.get("stage", "") or "")
        done = int(event.get("done") or 0)
        total = int(event.get("total") or 0)

        base = 0.0
        stage_weight = 0.0
        found = False
        for s, w in self.weights.items():
            if s == stage:
                stage_weight = w
                found = True
                break
            base += w

        stage_fraction = min(1.0, max(0.0, done / total)) if (found and total > 0) else 0.0
        current_pct = (base + stage_fraction * stage_weight) * 100.0
        self._max_pct = max(self._max_pct, current_pct)
        return min(100, int(round(self._max_pct)))

    def reset(self) -> None:
        self._max_pct = 0.0
