"""v0.5 quality presets — tuned for laser / CAD quality targets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .memory import (
    DEFAULT_MAX_PROCESS_SIZE,
    FAST_MAX_PROCESS_SIZE,
    MAX_QUALITY_PROCESS_SIZE,
)

DEFAULT_PRESET_ID = "logo"

# Each preset: UI label/description + full pipeline params
PRESETS: dict[str, dict[str, Any]] = {
    "laser_pro": {
        "label": "Laser Pro",
        "description": "Tightest clean black fills for cutting. Adaptive threshold + morphology.",
        "params": {
            "colormode": "binary",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 6,
            "color_precision": 6,
            "layer_difference": 16,
            "corner_threshold": 50,
            "length_threshold": 3.5,
            "max_iterations": 12,
            "splice_threshold": 40,
            "path_precision": 3,
            "max_process_size": 2800,
            "preprocess_mode": "laser_bw",
            "edge_strength": 0.7,
            "denoise": 0.4,
            "contrast": 0.65,
            "threshold_bias": 0.45,
            "invert": False,
            "color_compound": False,
        },
    },
    "logo": {
        "label": "Logo / Line Art",
        "description": "High-detail solid shapes, sharp corners, clean outer/inner edges.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 3,
            "color_precision": 7,
            "layer_difference": 12,
            "corner_threshold": 40,
            "length_threshold": 3.0,
            "max_iterations": 12,
            "splice_threshold": 35,
            "path_precision": 3,
            "max_process_size": 3200,
            "preprocess_mode": "logo",
            "edge_strength": 0.75,
            "denoise": 0.25,
            "contrast": 0.7,
            "threshold_bias": 0.5,
            "invert": False,
            "color_compound": True,
        },
    },
    "illustration": {
        "label": "Illustration Colour",
        "description": "Flat colour artwork with coherent regions and smooth boundaries.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 5,
            "color_precision": 6,
            "layer_difference": 14,
            "corner_threshold": 50,
            "length_threshold": 3.5,
            "max_iterations": 11,
            "splice_threshold": 40,
            "path_precision": 3,
            "max_process_size": 2800,
            "preprocess_mode": "illustration",
            "edge_strength": 0.5,
            "denoise": 0.45,
            "contrast": 0.55,
            "threshold_bias": 0.5,
            "invert": False,
            "color_compound": True,
        },
    },
    "photo": {
        "label": "High Detail Photo",
        "description": "Photos with strong structure retained — good for multi-layer colour.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 3,
            "color_precision": 8,
            "layer_difference": 10,
            "corner_threshold": 45,
            "length_threshold": 3.0,
            "max_iterations": 14,
            "splice_threshold": 35,
            "path_precision": 3,
            "max_process_size": 3600,
            "preprocess_mode": "photo",
            "edge_strength": 0.45,
            "denoise": 0.3,
            "contrast": 0.55,
            "threshold_bias": 0.5,
            "invert": False,
            "color_compound": True,
        },
    },
    "photoreal": {
        "label": "Photorealistic Max",
        "description": "Maximum nodes/detail for CAD import. Slow, high fidelity.",
        "params": {
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 1,
            "color_precision": 8,
            "layer_difference": 8,
            "corner_threshold": 30,
            "length_threshold": 2.5,
            "max_iterations": 16,
            "splice_threshold": 30,
            "path_precision": 3,
            "max_process_size": MAX_QUALITY_PROCESS_SIZE,
            "preprocess_mode": "photoreal",
            "edge_strength": 0.35,
            "denoise": 0.15,
            "contrast": 0.5,
            "threshold_bias": 0.5,
            "invert": False,
            "color_compound": True,
        },
    },
    "bw_compound": {
        "label": "B&W Compound",
        "description": "Tonal gray layers for engraving depth (LightBurn / xTool).",
        "params": {
            "colormode": "color",  # multi-gray layers
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 4,
            "color_precision": 6,
            "layer_difference": 12,
            "corner_threshold": 45,
            "length_threshold": 3.2,
            "max_iterations": 12,
            "splice_threshold": 38,
            "path_precision": 3,
            "max_process_size": 3000,
            "preprocess_mode": "bw_compound",
            "compound_levels": 6,
            "edge_strength": 0.5,
            "denoise": 0.35,
            "contrast": 0.6,
            "threshold_bias": 0.5,
            "invert": False,
            "color_compound": True,
        },
    },
}

# Back-compat aliases
PRESETS["laser"] = PRESETS["laser_pro"]
PRESETS["max"] = PRESETS["photoreal"]


def apply_preset(
    preset_id: str,
    overrides: dict[str, Any] | None = None,
    *,
    auto_tune: bool = False,
) -> dict[str, Any]:
    """
    Merge preset + overrides.

    auto_tune=False (default): respect explicit filter_speckle / thresholds.
    auto_tune=True: lightly map detail/simplify_strength if provided.
    """
    base = PRESETS.get(preset_id) or PRESETS[DEFAULT_PRESET_ID]
    params = deepcopy(base["params"])
    if overrides:
        # Ignore None values so UI can pass partials
        for k, v in overrides.items():
            if v is not None:
                params[k] = v

    if auto_tune and ("detail" in params or "simplify_strength" in params):
        detail = float(params.get("detail", 0.85))
        strength = float(params.get("simplify_strength", 0.2))
        # Only nudge — do not destroy preset intent
        base_speckle = int(params.get("filter_speckle", 4))
        params["filter_speckle"] = max(
            1, min(20, int(round(base_speckle + (1 - detail) * 4 + strength * 3)))
        )
        params["length_threshold"] = max(
            2.0,
            float(params.get("length_threshold", 3.5))
            + (1 - detail) * 1.5
            + strength * 1.0,
        )

    params["max_process_size"] = int(
        params.get("max_process_size", DEFAULT_MAX_PROCESS_SIZE)
    )
    return params


def preset_choices() -> list[tuple[str, str]]:
    """Stable ordered list of (id, label) for UI — unique ids only."""
    order = [
        "laser_pro",
        "logo",
        "illustration",
        "photo",
        "photoreal",
        "bw_compound",
    ]
    return [(k, PRESETS[k]["label"]) for k in order if k in PRESETS]
