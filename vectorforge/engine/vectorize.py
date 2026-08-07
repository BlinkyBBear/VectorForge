"""
High-quality vectorization via vtracer (visioncortex).

Memory-safe: caller must pass an already-downsampled image.
Tuned defaults produce tight, laser-ready black fills for signs & logos.
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps, ImageFilter

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


def _prepare_for_laser(img: Image.Image, force_mono: bool, threshold: int = 140) -> Image.Image:
    """
    Convert to high-contrast mono when requested.
    This is the single biggest quality win for laser signs.
    """
    rgba = img.convert("RGBA")
    if not force_mono:
        # Still flatten transparency onto pure white
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, rgba).convert("RGB")

    # High-contrast mono pipeline
    # 1. Flatten on white
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(bg, rgba).convert("L")

    # 2. Mild sharpen + contrast boost so thin lines stay solid
    flat = ImageOps.autocontrast(flat, cutoff=1)
    flat = flat.filter(ImageFilter.SHARPEN)

    # 3. Hard threshold → pure black / white
    thr = max(40, min(220, int(threshold)))
    bw = flat.point(lambda p: 0 if p < thr else 255, mode="L")
    return bw.convert("RGB")


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

    force_mono = bool(vt.get("force_mono", vt.get("colormode") == "binary"))
    threshold = int(vt.get("threshold", 140))

    report(f"Preparing image @ {plan.label}", 0.15)
    prepared = _prepare_for_laser(work, force_mono=force_mono, threshold=threshold)

    report(f"Vectorizing @ {plan.label}", 0.3)

    with tempfile.TemporaryDirectory(prefix="vectorforge_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "input.png"
        dst = tmp_path / "output.svg"
        prepared.save(src, format="PNG")

        report("Running vtracer (tight paths)", 0.45)

        common = dict(
            colormode=str(vt.get("colormode", "binary")),
            hierarchical=str(vt.get("hierarchical", "stacked")),
            mode=str(vt.get("mode", "spline")),
            filter_speckle=int(vt.get("filter_speckle", 10)),
            color_precision=int(vt.get("color_precision", 6)),
            corner_threshold=int(vt.get("corner_threshold", 70)),
            length_threshold=float(vt.get("length_threshold", 5.0)),
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
            # Older vtracer API
            vtracer.convert_image_to_svg_py(
                str(src),
                str(dst),
                **common,
            )

        report("Reading SVG", 0.9)
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

    # Force pure black fills for laser presets (removes any residual colour)
    if force_mono:
        svg = re.sub(r'fill="#[0-9a-fA-F]{3,8}"', 'fill="#000000"', svg)
        svg = re.sub(r"fill='#[0-9a-fA-F]{3,8}'", "fill='#000000'", svg)
        svg = re.sub(r'fill="rgb\([^"]+\)"', 'fill="#000000"', svg)

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
