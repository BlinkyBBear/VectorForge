"""
High-quality vectorization via vtracer.

Supports:
- Pure B&W laser paths
- Full colour compound vectors
- Photorealistic high-node output
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
    max_process_size: int = 1800
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


def _prepare_image(
    img: Image.Image,
    *,
    force_mono: bool,
    threshold: int = 128,
) -> Image.Image:
    """Prepare image for tracing."""
    rgba = img.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(bg, rgba)

    if not force_mono:
        return flat.convert("RGB")

    # Pure B&W pipeline for laser / logo
    gray = flat.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.8)
    gray = gray.filter(ImageFilter.SHARPEN)

    thr = max(30, min(220, int(threshold)))
    bw = gray.point(lambda p: 0 if p < thr else 255, mode="L")

    # Light clean-up of single-pixel noise
    bw = bw.filter(ImageFilter.MaxFilter(3))
    bw = bw.filter(ImageFilter.MinFilter(3))
    return bw.convert("RGB")


def _clean_svg_mono(svg: str) -> str:
    svg = re.sub(r'fill="#[0-9a-fA-F]{3,8}"', 'fill="#000000"', svg)
    svg = re.sub(r"fill='#[0-9a-fA-F]{3,8}'", "fill='#000000'", svg)
    svg = re.sub(r'fill="rgb\([^)]+\)"', 'fill="#000000"', svg)
    svg = re.sub(r'stroke="#[0-9a-fA-F]{3,8}"', 'stroke="none"', svg)
    return svg


def vectorize_image(
    img: Image.Image,
    params: VectorizeParams | None = None,
    on_progress: ProgressCb | None = None,
) -> VectorResult:
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

    force_mono = bool(vt.get("force_mono", False) or vt.get("colormode") == "binary")
    threshold = int(vt.get("threshold", 128))

    report(f"Preparing image @ {plan.label}", 0.12)
    prepared = _prepare_image(work, force_mono=force_mono, threshold=threshold)

    report("Running vtracer", 0.35)

    with tempfile.TemporaryDirectory(prefix="vectorforge_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "input.png"
        dst = tmp_path / "output.svg"
        prepared.save(src, format="PNG")

        common = dict(
            colormode="binary" if force_mono else str(vt.get("colormode", "color")),
            hierarchical=str(vt.get("hierarchical", "stacked")),
            mode=str(vt.get("mode", "spline")),
            filter_speckle=int(vt.get("filter_speckle", 4)),
            color_precision=int(vt.get("color_precision", 8)),
            corner_threshold=int(vt.get("corner_threshold", 50)),
            length_threshold=float(vt.get("length_threshold", 3.5)),
            path_precision=int(vt.get("path_precision", 3)),
        )

        try:
            vtracer.convert_image_to_svg_py(
                str(src),
                str(dst),
                layer_difference=int(vt.get("layer_difference", 12)),
                max_iterations=int(vt.get("max_iterations", 12)),
                splice_threshold=int(vt.get("splice_threshold", 40)),
                **common,
            )
        except TypeError:
            vtracer.convert_image_to_svg_py(str(src), str(dst), **common)

        report("Reading SVG", 0.9)
        svg = dst.read_text(encoding="utf-8")

    meta = (
        f"<!-- VectorForge | preset={params.preset_id} "
        f"| {plan.label} | mono={force_mono} -->\n"
    )
    if svg.lstrip().startswith("<?xml"):
        parts = svg.split("\n", 1)
        svg = parts[0] + "\n" + meta + (parts[1] if len(parts) == 2 else "")
    else:
        svg = meta + svg

    if force_mono:
        svg = _clean_svg_mono(svg)

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
