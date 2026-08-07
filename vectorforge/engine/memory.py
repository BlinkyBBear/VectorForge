"""Memory / resolution safety helpers."""

from __future__ import annotations

# Soft defaults
DEFAULT_MAX_PROCESS_SIZE = 1800
FAST_MAX_PROCESS_SIZE = 1400

# Hard ceiling — raised significantly because user prioritises absolute quality
HARD_MAX_PROCESS_SIZE = 6000
MAX_QUALITY_PROCESS_SIZE = 4000


def clamp_process_size(value: float | int) -> int:
    """Clamp requested process size into safe but high-quality range."""
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        v = DEFAULT_MAX_PROCESS_SIZE
    return max(400, min(HARD_MAX_PROCESS_SIZE, v))
