"""Quality presets for VectorForge desktop."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .memory import (
    DEFAULT_MAX_PROCESS_SIZE,
    FAST_MAX_PROCESS_SIZE,
    MAX_QUALITY_PROCESS_SIZE,
)

DEFAULT_PRESET_ID = "logo"

# Shared param schema used by UI + vectorize engine
PRESETS: dict[str, dict[str, Any]] = {
    "logo": {
        "label": "Logo / Line Art",
        "description": "Maximum precision, minimal simplification — sharp corners, clean shapes.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 4,
            "color_precision": 6,
            "layer_difference": 16,
            "corner_threshold": 60,
            "length_threshold": 4.0,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 3,
            "palette_hint": 8,
            "max_process_size": 1800,
            "detail": 0.92,
            "simplify_strength": 0.14,
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
            "palette_hint": 16,
            "max_process_size": 1700,
            "detail": 0.78,
            "simplify_strength": 0.28,
        },
    },
    "photo": {
        "label": "High Detail Photo",
        "description": "Higher resolution + more colors + light simplification.",
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
            "palette_hint": 24,
            "max_process_size": 1800,
            "detail": 0.84,
            "simplify_strength": 0.30,
        },
    },
    "laser": {
        "label": "Laser Optimized",
        "description": "Balanced quality with stronger cleanup for cutting.",
        "params": {
            "colormode": "binary",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 8,
            "color_precision": 6,
            "layer_difference": 16,
            "corner_threshold": 60,
            "length_threshold": 5.0,
            "max_iterations": 10,
            "splice_threshold": 45,
            "path_precision": 2,
            "palette_hint": 2,
            "max_process_size": FAST_MAX_PROCESS_SIZE,
            "detail": 0.68,
            "simplify_strength": 0.36,
        },
    },
    "max": {
        "label": "Maximum Quality",
        "description": "Experimental: highest fidelity. Slower, more memory.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 2,
            "color_precision": 8,
            "layer_difference": 10,
            "corner_threshold": 40,
            "length_threshold": 3.0,
            "max_iterations": 14,
            "splice_threshold": 35,
            "path_precision": 3,
            "palette_hint": 40,
            "max_process_size": MAX_QUALITY_PROCESS_SIZE,
            "detail": 0.97,
            "simplify_strength": 0.15,
        },
    },
}


def apply_preset(preset_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = PRESETS.get(preset_id) or PRESETS[DEFAULT_PRESET_ID]
    params = deepcopy(base["params"])
    if overrides:
        params.update(overrides)
    # Map detail/simplify into vtracer-ish knobs when user moves sliders
    detail = float(params.get("detail", 0.8))
    strength = float(params.get("simplify_strength", 0.25))
    # Higher detail → lower filter_speckle, higher precision
    params["filter_speckle"] = max(1, int(round(2 + (1 - detail) * 10 + strength * 6)))
    params["path_precision"] = 3 if detail >= 0.75 else 2
    params["length_threshold"] = max(2.5, 3.0 + (1 - detail) * 3 + strength * 2)
    params["max_process_size"] = int(
        params.get("max_process_size", DEFAULT_MAX_PROCESS_SIZE)
    )
    return params
