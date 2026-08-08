"""VectorForge v1.0 presets — CNC outline quality first."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .memory import DEFAULT_MAX_PROCESS_SIZE, MAX_QUALITY_PROCESS_SIZE

DEFAULT_PRESET_ID = "cnc_outline"

PRESETS: dict[str, dict[str, Any]] = {
    "cnc_outline": {
        "label": "CNC Outline",
        "description": "Pure closed outlines for plasma/router/laser cut-outs. Potrace, stroke-only.",
        "params": {
            "engine": "potrace",
            "output_style": "outline",
            "color_mode": "outline",
            "threshold_method": "otsu",
            "blacklevel": 0.5,
            "denoise": 0.22,
            "contrast": 0.30,
            "edge_strength": 0.35,
            "turdsize": 2,
            "alphamax": 1.0,
            "opttolerance": 0.2,
            "opticurve": True,
            "turnpolicy": "minority",
            "stroke_width": 1.0,
            "max_process_size": 3600,
            "invert": False,
            "detail": 0.9,
            "simplify_strength": 0.15,
        },
    },
    "laser_pro": {
        "label": "Laser Pro",
        "description": "Tight solid black fills (evenodd holes) via Potrace.",
        "params": {
            "engine": "potrace",
            "output_style": "fill",
            "color_mode": "bw",
            "threshold_method": "otsu",
            "blacklevel": 0.5,
            "denoise": 0.28,
            "contrast": 0.35,
            "edge_strength": 0.4,
            "turdsize": 3,
            "alphamax": 1.0,
            "opttolerance": 0.22,
            "opticurve": True,
            "turnpolicy": "minority",
            "max_process_size": 3200,
            "invert": False,
            "detail": 0.85,
            "simplify_strength": 0.2,
        },
    },
    "logo": {
        "label": "Logo / Line Art",
        "description": "High-fidelity solid logos and signs. Potrace, sharp corners.",
        "params": {
            "engine": "potrace",
            "output_style": "fill",
            "color_mode": "bw",
            "threshold_method": "otsu",
            "blacklevel": 0.48,
            "denoise": 0.18,
            "contrast": 0.28,
            "edge_strength": 0.45,
            "turdsize": 1,
            "alphamax": 0.95,
            "opttolerance": 0.15,
            "opticurve": True,
            "turnpolicy": "minority",
            "max_process_size": 4000,
            "invert": False,
            "detail": 0.95,
            "simplify_strength": 0.1,
        },
    },
    "colour": {
        "label": "Colour Compound",
        "description": "Multi-colour stacked layers (vtracer) for fills / vinyl / engraving colour.",
        "params": {
            "engine": "vtracer",
            "output_style": "fill",
            "color_mode": "color",
            "colormode": "color",
            "hierarchical": "stacked",
            "mode": "spline",
            "filter_speckle": 4,
            "color_precision": 6,
            "layer_difference": 14,
            "corner_threshold": 50,
            "length_threshold": 3.5,
            "max_iterations": 12,
            "splice_threshold": 40,
            "path_precision": 3,
            "denoise": 0.35,
            "contrast": 0.45,
            "edge_strength": 0.4,
            "max_process_size": 2800,
            "invert": False,
        },
    },
    "photo": {
        "label": "High Detail Photo",
        "description": "Photographic detail with colour layers (vtracer).",
        "params": {
            "engine": "vtracer",
            "output_style": "fill",
            "color_mode": "color",
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
            "denoise": 0.28,
            "contrast": 0.5,
            "edge_strength": 0.4,
            "max_process_size": 3600,
            "invert": False,
        },
    },
    "photoreal": {
        "label": "Photorealistic Max",
        "description": "Maximum colour fidelity — slow, high node count.",
        "params": {
            "engine": "vtracer",
            "output_style": "fill",
            "color_mode": "color",
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
            "denoise": 0.15,
            "contrast": 0.45,
            "edge_strength": 0.35,
            "max_process_size": MAX_QUALITY_PROCESS_SIZE,
            "invert": False,
        },
    },
}

# aliases
PRESETS["illustration"] = PRESETS["colour"]
PRESETS["laser"] = PRESETS["laser_pro"]
PRESETS["max"] = PRESETS["photoreal"]
PRESETS["bw_compound"] = {
    "label": "B&W Compound",
    "description": "Tonal gray layers for engraving depth.",
    "params": {
        **PRESETS["colour"]["params"],
        "preprocess_mode": "bw_compound",
        "compound_levels": 6,
        "engine": "vtracer",
    },
}


def apply_preset(preset_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = PRESETS.get(preset_id) or PRESETS[DEFAULT_PRESET_ID]
    params = deepcopy(base["params"])
    if overrides:
        for k, v in overrides.items():
            if v is not None:
                params[k] = v
    # Colour mode toggle overrides
    cm = str(params.get("color_mode", "")).lower()
    if cm in ("outline", "outline-only", "cnc"):
        params["engine"] = "potrace"
        params["output_style"] = "outline"
    elif cm in ("bw", "binary", "pure_bw", "blackwhite"):
        params["engine"] = "potrace"
        params["output_style"] = params.get("output_style") or "fill"
    elif cm in ("color", "colour", "compound"):
        params["engine"] = "vtracer"
        params["colormode"] = "color"

    params["max_process_size"] = int(
        params.get("max_process_size", DEFAULT_MAX_PROCESS_SIZE)
    )
    return params


def preset_choices() -> list[tuple[str, str]]:
    order = [
        "cnc_outline",
        "laser_pro",
        "logo",
        "colour",
        "photo",
        "photoreal",
    ]
    return [(k, PRESETS[k]["label"]) for k in order if k in PRESETS]
