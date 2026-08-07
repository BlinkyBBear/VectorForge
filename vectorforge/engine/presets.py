"""Quality presets + full custom parameter schema for VectorForge."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .memory import (
    DEFAULT_MAX_PROCESS_SIZE,
    FAST_MAX_PROCESS_SIZE,
    MAX_QUALITY_PROCESS_SIZE,
)

DEFAULT_PRESET_ID = "logo"

PARAM_SCHEMA = {
    "colormode": {"type": "choice", "choices": ["binary", "color"], "label": "Colour mode"},
    "hierarchical": {"type": "choice", "choices": ["stacked", "cutout"], "label": "Hierarchy"},
    "mode": {"type": "choice", "choices": ["spline", "polygon", "none"], "label": "Path mode"},
    "filter_speckle": {"type": "int", "min": 0, "max": 30, "label": "Filter speckles"},
    "color_precision": {"type": "int", "min": 1, "max": 10, "label": "Colour precision"},
    "layer_difference": {"type": "int", "min": 1, "max": 64, "label": "Layer difference"},
    "corner_threshold": {"type": "int", "min": 0, "max": 180, "label": "Corner threshold"},
    "length_threshold": {"type": "float", "min": 1.0, "max": 20.0, "label": "Length threshold"},
    "max_iterations": {"type": "int", "min": 1, "max": 30, "label": "Max iterations"},
    "splice_threshold": {"type": "int", "min": 0, "max": 180, "label": "Splice threshold"},
    "path_precision": {"type": "int", "min": 1, "max": 8, "label": "Path precision"},
    "max_process_size": {"type": "int", "min": 800, "max": 6000, "label": "Max process size (px)"},
    "threshold": {"type": "int", "min": 30, "max": 220, "label": "B&W threshold"},
    "force_mono": {"type": "bool", "label": "Force pure B&W"},
}

PRESETS: dict[str, dict[str, Any]] = {
    "laser": {
        "label": "Laser Optimized",
        "description": "Clean black fills for cutting. Good starting point for signs.",
        "params": {
            "colormode": "binary",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 6,
            "color_precision": 6,
            "layer_difference": 16,
            "corner_threshold": 60,
            "length_threshold": 4.0,
            "max_iterations": 12,
            "splice_threshold": 40,
            "path_precision": 3,
            "max_process_size": 2000,
            "threshold": 128,
            "force_mono": True,
        },
    },
    "logo": {
        "label": "Logo / Line Art",
        "description": "High detail solid fills and sharp corners — best for logos & signs.",
        "params": {
            "colormode": "binary",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 3,
            "color_precision": 6,
            "layer_difference": 14,
            "corner_threshold": 45,
            "length_threshold": 3.0,
            "max_iterations": 14,
            "splice_threshold": 35,
            "path_precision": 4,
            "max_process_size": 2400,
            "threshold": 120,
            "force_mono": True,
        },
    },
    "illustration": {
        "label": "Illustration (Colour)",
        "description": "Balanced colour compound vectors for flat artwork.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 2,
            "color_precision": 8,
            "layer_difference": 10,
            "corner_threshold": 40,
            "length_threshold": 2.8,
            "max_iterations": 14,
            "splice_threshold": 35,
            "path_precision": 4,
            "max_process_size": 2600,
            "threshold": 128,
            "force_mono": False,
        },
    },
    "photo": {
        "label": "High Detail Photo",
        "description": "More nodes and colours for photographic subjects.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 1,
            "color_precision": 9,
            "layer_difference": 6,
            "corner_threshold": 30,
            "length_threshold": 2.2,
            "max_iterations": 16,
            "splice_threshold": 30,
            "path_precision": 5,
            "max_process_size": 3200,
            "threshold": 128,
            "force_mono": False,
        },
    },
    "photo_max": {
        "label": "Photorealistic (Max)",
        "description": "Maximum detail. High node count. Use for photos that must import cleanly into xTool / Fusion.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 0,
            "color_precision": 10,
            "layer_difference": 4,
            "corner_threshold": 20,
            "length_threshold": 1.8,
            "max_iterations": 20,
            "splice_threshold": 25,
            "path_precision": 6,
            "max_process_size": 4000,
            "threshold": 128,
            "force_mono": False,
        },
    },
    "bw_compound": {
        "label": "B&W Compound",
        "description": "Multiple black tonal layers — good for engraving depth.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 2,
            "color_precision": 5,
            "layer_difference": 18,
            "corner_threshold": 50,
            "length_threshold": 3.2,
            "max_iterations": 14,
            "splice_threshold": 35,
            "path_precision": 4,
            "max_process_size": 2400,
            "threshold": 128,
            "force_mono": False,
        },
    },
}


def apply_preset(preset_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = PRESETS.get(preset_id) or PRESETS[DEFAULT_PRESET_ID]
    params = deepcopy(base["params"])
    if overrides:
        for k, v in overrides.items():
            if k in PARAM_SCHEMA or k in params:
                params[k] = v
    return params
