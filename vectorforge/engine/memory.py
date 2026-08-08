"""Resolution limits — v1.0 allows up to 6000px for quality."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_PROCESS_SIZE = 3600
FAST_MAX_PROCESS_SIZE = 2400
MAX_QUALITY_PROCESS_SIZE = 4800
HARD_MAX_PROCESS_SIZE = 6000
WARN_MEGAPIXELS = 24
MAX_FILE_BYTES = 150 * 1024 * 1024


@dataclass(frozen=True)
class SizePlan:
    source_width: int
    source_height: int
    process_width: int
    process_height: int
    scale: float
    megapixels: float
    downsampled: bool
    forced: bool
    warning: str | None
    label: str


def clamp_process_size(requested: int | float) -> int:
    try:
        n = int(round(float(requested)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_PROCESS_SIZE
    if n < 256:
        return DEFAULT_MAX_PROCESS_SIZE
    return max(256, min(HARD_MAX_PROCESS_SIZE, n))


def plan_processing_size(
    width: int,
    height: int,
    max_process_size: int = DEFAULT_MAX_PROCESS_SIZE,
) -> SizePlan:
    max_side = clamp_process_size(max_process_size)
    long = max(width, height)
    megapixels = (width * height) / 1_000_000.0
    scale = 1.0
    forced = False
    warning = None

    if long > max_side:
        scale = max_side / long
        forced = True
        warning = (
            f"Source {width}×{height} ({megapixels:.1f} MP) → "
            f"working {int(round(width * scale))}×{int(round(height * scale))} "
            f"(max {max_side}px)."
        )
    elif megapixels >= WARN_MEGAPIXELS:
        warning = f"Large image ({megapixels:.1f} MP). Working at native {width}×{height}."

    pw = max(1, int(round(width * scale)))
    ph = max(1, int(round(height * scale)))
    label = f"{pw}×{ph}{' (downsampled)' if forced else ' (native)'}"

    return SizePlan(
        source_width=width,
        source_height=height,
        process_width=pw,
        process_height=ph,
        scale=scale,
        megapixels=megapixels,
        downsampled=scale < 1.0,
        forced=forced,
        warning=warning,
        label=label,
    )
