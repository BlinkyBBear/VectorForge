"""Memory / resolution safety helpers."""

from __future__ import annotations

from dataclasses import dataclass

# Soft defaults
DEFAULT_MAX_PROCESS_SIZE = 1800
FAST_MAX_PROCESS_SIZE = 1400

# Hard ceiling — raised for maximum quality work
HARD_MAX_PROCESS_SIZE = 6000
MAX_QUALITY_PROCESS_SIZE = 4000

# Reject extremely large files early (bytes)
MAX_FILE_BYTES = 120 * 1024 * 1024  # 120 MB


@dataclass
class SizePlan:
    original_width: int
    original_height: int
    process_width: int
    process_height: int
    downsampled: bool
    label: str
    warning: str | None = None


def clamp_process_size(value: float | int) -> int:
    """Clamp requested process size into safe but high-quality range."""
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        v = DEFAULT_MAX_PROCESS_SIZE
    return max(400, min(HARD_MAX_PROCESS_SIZE, v))


def plan_processing_size(
    width: int,
    height: int,
    max_side: int,
) -> SizePlan:
    """
    Decide whether to downsample and return a SizePlan.
    Never upsamples.
    """
    max_side = clamp_process_size(max_side)
    long_side = max(width, height)

    if long_side <= max_side:
        return SizePlan(
            original_width=width,
            original_height=height,
            process_width=width,
            process_height=height,
            downsampled=False,
            label=f"{width}×{height}",
            warning=None,
        )

    scale = max_side / long_side
    pw = max(1, int(round(width * scale)))
    ph = max(1, int(round(height * scale)))

    return SizePlan(
        original_width=width,
        original_height=height,
        process_width=pw,
        process_height=ph,
        downsampled=True,
        label=f"{pw}×{ph} (from {width}×{height})",
        warning=f"Downsampled to {max_side}px long side for processing",
    )
