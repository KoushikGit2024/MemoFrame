"""Resource profiles. Each sets how hard the engine works."""

from __future__ import annotations

from memoframe_engine.core.config import Settings
from memoframe_engine.core.errors import EngineError, ErrorCode

PROFILES: dict[str, dict[str, object]] = {
    # Keeps a laptop usable while it works.
    "gentle": dict(workers=1, batch_size=16, cpu_limit=0.5, cv_threads=1, min_free_mem_mb=1500),
    "balanced": dict(workers=2, batch_size=32, cpu_limit=0.8, cv_threads=1, min_free_mem_mb=1024),
    # workers stays at the CPU-based default.
    "fast": dict(batch_size=64, cpu_limit=1.0, cv_threads=2, min_free_mem_mb=768),
}
DEFAULT_PROFILE = "balanced"


def apply_profile(settings: Settings, name: str) -> Settings:
    """Return ``settings`` with the named profile applied."""
    if name not in PROFILES:
        raise EngineError(
            ErrorCode.CONFIG_INVALID,
            f"Unknown profile {name!r}. Choose one of: {', '.join(PROFILES)}.",
        )
    return settings.with_overrides(**PROFILES[name])
