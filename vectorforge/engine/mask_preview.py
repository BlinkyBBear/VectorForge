"""Binary mask preview only (no Potrace / vtracer). Offline."""

from __future__ import annotations

from typing import Any

from PIL import Image

from .image_ops import downsample_image
from .memory import clamp_process_size
from .preprocess import preprocess_binary_for_potrace


def preview_binary_mask(
    img: Image.Image,
    overrides: dict[str, Any] | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Run raster prep only → binary mask image (RGB black/white) + meta.

    Same preprocess as Outline / B&W / Centerline vectorize, without tracing.
    """
    o = dict(overrides or {})
    max_side = clamp_process_size(o.get("max_process_size", 3600))
    work, plan = downsample_image(img, max_side)

    raw_sf = o.get("scale_factor", None)
    try:
        raw_sf_f = float(raw_sf) if raw_sf is not None else 0.0
    except (TypeError, ValueError):
        raw_sf_f = 0.0
    auto_scale = bool(o.get("auto_scale", raw_sf_f < 1.01))
    hp = o.get("highpass_radius", None)

    preview_img, _binary, pre_meta = preprocess_binary_for_potrace(
        work,
        denoise=float(o.get("denoise", 0.40)),
        contrast=float(o.get("contrast", 0.25)),
        edge_strength=float(o.get("edge_strength", 0.25)),
        threshold_method=str(o.get("threshold_method", "otsu")),
        blacklevel=float(o.get("blacklevel", 0.5)),
        invert=bool(o.get("invert", False)),
        logo_text=bool(o.get("logo_text", True)),
        highpass_radius=float(hp) if hp is not None else None,
        scale_factor=raw_sf_f if raw_sf_f >= 1.01 else None,
        auto_scale=auto_scale,
    )
    meta = {
        **pre_meta,
        "process_label": getattr(plan, "label", f"{work.width}×{work.height}"),
        "working_size": (work.width, work.height),
    }
    # Ensure RGB for UI
    if preview_img.mode != "RGB":
        preview_img = preview_img.convert("RGB")
    return preview_img, meta
