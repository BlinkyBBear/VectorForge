"""Quality presets for VectorForge desktop — tuned for tight laser-ready paths."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .memory import (
    DEFAULT_MAX_PROCESS_SIZE,
    FAST_MAX_PROCESS_SIZE,
    MAX_QUALITY_PROCESS_SIZE,
)

DEFAULT_PRESET_ID = "laser"

# Shared param schema used by UI + vectorize engine
PRESETS: dict[str, dict[str, Any]] = {
    "laser": {
        "label": "Laser Optimized (recommended)",
        "description": "Tight black fills, clean edges, minimal islands — best for cutting & engraving signs.",
        "params": {
            "colormode": "binary",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 12,
            "color_precision": 6,
            "layer_difference": 16,
            "corner_threshold": 80,
            "length_threshold": 5.5,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 2,
            "palette_hint": 2,
            "max_process_size": 1400,
            "detail": 0.55,
            "simplify_strength": 0.55,
            "force_mono": True,
            "threshold": 140,
        },
    },
    "logo": {
        "label": "Logo / Line Art",
        "description": "Very tight paths, sharp corners, clean solid fills for logos and icons.",
        "params": {
            "colormode": "binary",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 8,
            "color_precision": 6,
            "layer_difference": 16,
            "corner_threshold": 70,
            "length_threshold": 4.5,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 2,
            "palette_hint": 4,
            "max_process_size": 1600,
            "detail": 0.72,
            "simplify_strength": 0.38,
            "force_mono": True,
            "threshold": 128,
        },
    },
    "illustration": {
        "label": "Illustration",
        "description": "Balanced detail for drawings and flat artwork.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 6,
            "color_precision": 6,
            "layer_difference": 14,
            "corner_threshold": 55,
            "length_threshold": 4.0,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 3,
            "palette_hint": 12,
            "max_process_size": 1600,
            "detail": 0.78,
            "simplify_strength": 0.30,
            "force_mono": False,
        },
    },
    "photo": {
        "label": "High Detail Photo",
        "description": "More colors + detail. Use only when you need photographic shading.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 4,
            "color_precision": 8,
            "layer_difference": 12,
            "corner_threshold": 50,
            "length_threshold": 3.5,
            "max_iterations": 12,
            "splice_threshold": 40,
            "path_precision": 3,
            "palette_hint": 20,
            "max_process_size": 1700,
            "detail": 0.84,
            "simplify_strength": 0.28,
            "force_mono": False,
        },
    },
    "max": {
        "label": "Maximum Quality",
        "description": "Highest fidelity (slower). Prefer Laser or Logo for cutting.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 3,
            "color_precision": 8,
            "layer_difference": 10,
            "corner_threshold": 40,
            "length_threshold": 3.0,
            "max_iterations": 14,
            "splice_threshold": 35,
            "path_precision": 3,
            "palette_hint": 32,
            "max_process_size": MAX_QUALITY_PROCESS_SIZE,
            "detail": 0.92,
            "simplify_strength": 0.18,
            "force_mono": False,
        },
    },
}


def apply_preset(preset_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = PRESETS.get(preset_id) or PRESETS[DEFAULT_PRESET_ID]
    params = deepcopy(base["params"])
    if overrides:
        params.update(overrides)

    detail = float(params.get("detail", 0.7))
    strength = float(params.get("simplify_strength", 0.4))

    # Higher simplify_strength + lower detail → much cleaner / tighter paths
    params["filter_speckle"] = max(2, int(round(4 + (1 - detail) * 14 + strength * 10)))
    params["path_precision"] = 2 if strength > 0.35 or detail < 0.7 else 3
    params["length_threshold"] = max(3.0, 3.5 + (1 - detail) * 4 + strength * 3)
    params["corner_threshold"] = max(40, min(90, int(params.get("corner_threshold", 60) + strength * 25)))
    params["max_process_size"] = int(
        params.get("max_process_size", DEFAULT_MAX_PROCESS_SIZE)
    )
    return params
