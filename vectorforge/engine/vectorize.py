"""
High-quality vectorization via vtracer (visioncortex).

Memory-safe: caller must pass an already-downsampled image.
All heavy work is iterative inside vtracer (Rust) — no Python recursion.
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .image_ops import downsample_image
from .memory import clamp_process_size
from .presets import apply_preset, DEFAULT_PRESET_ID

ProgressCb = Callable[[str, float], None]


@dataclass
class VectorizeParams:
    preset_id: str = DEFAULT_PRESET_ID
    max_process_size: int = 1800
    # Optional direct vtracer overrides
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
    # rough node estimate from path commands
    nodes = len(re.findall(r"[MLCQSTmlcqst]", svg))
    return paths, nodes


def vectorize_image(
    img: Image.Image,
    params: VectorizeParams | None = None,
    on_progress: ProgressCb | None = None,
) -> VectorResult:
    """
    Convert a PIL image to SVG using vtracer.
    Downsamples to max_process_size first (memory safety).
    """
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
    # ensure process size from plan is reflected
    vt["max_process_size"] = max_side

    report(f"Vectorizing @ {plan.label}", 0.2)

    # vtracer works from file paths
    with tempfile.TemporaryDirectory(prefix="vectorforge_") as tmp:
        tmp_path = Path(tmp)
        # Flatten transparency onto white for binary cut modes; keep alpha for color
        if vt.get("colormode") == "binary":
            bg = Image.new("RGBA", work.size, (255, 255, 255, 255))
            flat = Image.alpha_composite(bg, work.convert("RGBA")).convert("RGB")
        else:
            # Composite on white so transparent regions become background
            bg = Image.new("RGBA", work.size, (255, 255, 255, 255))
            flat = Image.alpha_composite(bg, work.convert("RGBA")).convert("RGB")

        src = tmp_path / "input.png"
        dst = tmp_path / "output.svg"
        flat.save(src, format="PNG")

        report("Running vtracer", 0.45)
        try:
            vtracer.convert_image_to_svg_py(
                str(src),
                str(dst),
                colormode=str(vt.get("colormode", "color")),
                hierarchical=str(vt.get("hierarchical", "stacked")),
                mode=str(vt.get("mode", "spline")),
                filter_speckle=int(vt.get("filter_speckle", 4)),
                color_precision=int(vt.get("color_precision", 6)),
                layer_difference=int(vt.get("layer_difference", 16)),
                corner_threshold=int(vt.get("corner_threshold", 60)),
                length_threshold=float(vt.get("length_threshold", 4.0)),
                max_iterations=int(vt.get("max_iterations", 10)),
                splice_threshold=int(vt.get("splice_threshold", 45)),
                path_precision=int(vt.get("path_precision", 3)),
            )
        except TypeError:
            # Older vtracer API variants
            vtracer.convert_image_to_svg_py(
                str(src),
                str(dst),
                colormode=str(vt.get("colormode", "color")),
                hierarchical=str(vt.get("hierarchical", "stacked")),
                mode=str(vt.get("mode", "spline")),
                filter_speckle=int(vt.get("filter_speckle", 4)),
                color_precision=int(vt.get("color_precision", 6)),
                corner_threshold=int(vt.get("corner_threshold", 60)),
                length_threshold=float(vt.get("length_threshold", 4.0)),
                path_precision=int(vt.get("path_precision", 3)),
            )

        report("Reading SVG", 0.9)
        svg = dst.read_text(encoding="utf-8")

    # Inject helpful metadata comment
    meta = (
        f"<!-- VectorForge desktop | preset={params.preset_id} "
        f"| working={plan.label} | max_side={max_side} -->\n"
    )
    if svg.lstrip().startswith("<?xml"):
        # after xml declaration
        parts = svg.split("\n", 1)
        if len(parts) == 2:
            svg = parts[0] + "\n" + meta + parts[1]
        else:
            svg = meta + svg
    else:
        svg = meta + svg

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
