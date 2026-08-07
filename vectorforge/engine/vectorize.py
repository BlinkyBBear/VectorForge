"""
High-quality vectorization via vtracer (visioncortex).

For laser presets we force a pure black-and-white image before tracing.
This is the only way to get the tight, solid fills needed for cutting.
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps, ImageFilter, ImageEnhance

from .image_ops import downsample_image
from .memory import clamp_process_size
from .presets import apply_preset, DEFAULT_PRESET_ID

ProgressCb = Callable[[str, float], None]


@dataclass
class VectorizeParams:
    preset_id: str = DEFAULT_PRESET_ID
    max_process_size: int = 1400
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorResult:
    svg: str
    width: int
    height: int
    path_count: int
    node_estimate: int
    duration_ms: int
    process_label: str
    params: dict[str, Any]
    warning: str | None = None


def _count_svg_stats(svg: str) -> tuple[int, int]:
    paths = len(re.findall(r"<path\b", svg, flags=re.I))
    nodes = len(re.findall(r"[MLCQSTmlcqst]", svg))
    return paths, nodes


def _prepare_for_laser(img: Image.Image, force_mono: bool, threshold: int = 128) -> Image.Image:
    """
    Aggressive pure black / white conversion.

    Goal: solid black subject on pure white background so vtracer
    produces clean filled paths instead of multi-colour fragments.
    """
    rgba = img.convert("RGBA")

    # Always flatten transparency onto pure white first
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat_rgba = Image.alpha_composite(bg, rgba)

    if not force_mono:
        return flat_rgba.convert("RGB")

    # --- Aggressive mono pipeline ---
    gray = flat_rgba.convert("L")

    # Boost contrast hard so the subject becomes pure black
    gray = ImageOps.autocontrast(gray, cutoff=2)
    gray = ImageEnhance.Contrast(gray).enhance(2.2)
    gray = gray.filter(ImageFilter.SHARPEN)

    # Hard threshold → pure black or pure white
    thr = max(30, min(220, int(threshold)))
    bw = gray.point(lambda p: 0 if p < thr else 255, mode="L")

    # Optional morphological clean-up (remove tiny speckles before tracing)
    # We do a simple 1-pixel dilate/erode using max/min filters
    bw = bw.filter(ImageFilter.MaxFilter(3))
    bw = bw.filter(ImageFilter.MinFilter(3))

    return bw.convert("RGB")


def _clean_svg_for_laser(svg: str) -> str:
    """Force every fill to pure black and remove tiny path noise if possible."""
    # Force black fills
    svg = re.sub(r'fill="#[0-9a-fA-F]{3,8}"', 'fill="#000000"', svg)
    svg = re.sub(r"fill='#[0-9a-fA-F]{3,8}'", "fill='#000000'", svg)
    svg = re.sub(r'fill="rgb\([^)]+\)"', 'fill="#000000"', svg)
    svg = re.sub(r'fill="hsl\([^)]+\)"', 'fill="#000000"', svg)

    # Remove stroke colours that are not black (keep structure simple)
    svg = re.sub(r'stroke="#[0-9a-fA-F]{3,8}"', 'stroke="none"', svg)
    svg = re.sub(r"stroke='#[0-9a-fA-F]{3,8}'", "stroke='none'", svg)

    return svg


def vectorize_image(
    img: Image.Image,
    params: VectorizeParams | None = None,
    on_progress: ProgressCb | None = None,
) -> VectorResult:
    """Convert a PIL image to tight, laser-ready SVG using vtracer."""
    import vtracer

    params = params or VectorizeParams()
    t0 = time.perf_counter()
    report = on_progress or (lambda _s, _p: None)

    report("Planning resolution", 0.05)
    max_side = clamp_process_size(
        params.overrides.get("max_process_size", params.max_process_size)
    )
    work, plan = downsample_image(img, max_side)
    vt = apply_preset(params.preset_id, params.overrides)
    vt["max_process_size"] = max_side

    # Force mono for any laser / logo style preset
    force_mono = bool(
        vt.get("force_mono", False)
        or vt.get("colormode") == "binary"
        or params.preset_id in ("laser", "logo")
    )
    threshold = int(vt.get("threshold", 128))

    report(f"Preparing pure black/white @ {plan.label}", 0.12)
    prepared = _prepare_for_laser(work, force_mono=force_mono, threshold=threshold)

    report("Running vtracer (binary / tight)", 0.35)

    with tempfile.TemporaryDirectory(prefix="vectorforge_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "input.png"
        dst = tmp_path / "output.svg"
        prepared.save(src, format="PNG")

        # Very aggressive settings when we want laser quality
        filter_speckle = int(vt.get("filter_speckle", 12))
        if force_mono:
            filter_speckle = max(filter_speckle, 10)

        common = dict(
            colormode="binary" if force_mono else str(vt.get("colormode", "color")),
            hierarchical="stacked",
            mode=str(vt.get("mode", "spline")),
            filter_speckle=filter_speckle,
            color_precision=int(vt.get("color_precision", 6)),
            corner_threshold=int(vt.get("corner_threshold", 80)),
            length_threshold=float(vt.get("length_threshold", 5.5)),
            path_precision=int(vt.get("path_precision", 2)),
        )

        try:
            vtracer.convert_image_to_svg_py(
                str(src),
                str(dst),
                layer_difference=int(vt.get("layer_difference", 16)),
                max_iterations=int(vt.get("max_iterations", 10)),
                splice_threshold=int(vt.get("splice_threshold", 45)),
                **common,
            )
        except TypeError:
            vtracer.convert_image_to_svg_py(
                str(src),
                str(dst),
                **common,
            )

        report("Cleaning SVG", 0.9)
        svg = dst.read_text(encoding="utf-8")

    # Inject metadata
    meta = (
        f"<!-- VectorForge | preset={params.preset_id} "
        f"| working={plan.label} | mono={force_mono} -->\n"
    )
    if svg.lstrip().startswith("<?xml"):
        parts = svg.split("\n", 1)
        svg = parts[0] + "\n" + meta + (parts[1] if len(parts) == 2 else "")
    else:
        svg = meta + svg

    if force_mono:
        svg = _clean_svg_for_laser(svg)

    paths, nodes = _count_svg_stats(svg)
    ms = int((time.perf_counter() - t0) * 1000)
    report("Done", 1.0)

    return VectorResult(
        svg=svg,
        width=work.width,
        height=work.height,
        path_count=paths,
        node_estimate=nodes,
        duration_ms=ms,
        process_label=plan.label,
        params=vt,
        warning=plan.warning,
    )


def save_svg(result: VectorResult, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(result.svg, encoding="utf-8")
    return p
