"""
High-quality vectorization pipeline (v0.5).

preprocess (edge-aware) → vtracer → SVG sanitize for CAD/laser tools.
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
from .preprocess import preprocess_for_vectorize, describe_preprocess
from .presets import apply_preset, DEFAULT_PRESET_ID

ProgressCb = Callable[[str, float], None]


@dataclass
class VectorizeParams:
    preset_id: str = DEFAULT_PRESET_ID
    max_process_size: int = 2800
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
    preprocess_note: str = ""


def _count_svg_stats(svg: str) -> tuple[int, int]:
    paths = len(re.findall(r"<path\b", svg, flags=re.I))
    nodes = len(re.findall(r"[MLCQSTmlcqst]", svg))
    return paths, nodes


def _sanitize_svg_for_cad(svg: str, *, width: int, height: int) -> str:
    """
    Ensure SVG is friendly to xTool Studio, Fusion 360, LightBurn, Inkscape.
    - valid viewBox
    - no script
    - fill-rule nonzero where helpful
    """
    # Strip any accidental scripts
    svg = re.sub(r"<script[\s\S]*?</script>", "", svg, flags=re.I)
    # Ensure xmlns
    if "xmlns=" not in svg[:400]:
        svg = svg.replace(
            "<svg",
            '<svg xmlns="http://www.w3.org/2000/svg"',
            1,
        )
    # Ensure viewBox if missing
    if "viewBox" not in svg[:500]:
        svg = re.sub(
            r"<svg([^>]*)>",
            rf'<svg\1 viewBox="0 0 {width} {height}">',
            svg,
            count=1,
        )
    # Prefer nonzero fill-rule on paths that lack it (cleaner holes in CAD)
    def _path_fill_rule(m: re.Match[str]) -> str:
        tag = m.group(0)
        if "fill-rule" in tag or "fill=" not in tag:
            return tag
        return tag[:-1] + ' fill-rule="nonzero">'

    svg = re.sub(r"<path\b[^>]*>", _path_fill_rule, svg)
    return svg


def vectorize_image(
    img: Image.Image,
    params: VectorizeParams | None = None,
    on_progress: ProgressCb | None = None,
) -> VectorResult:
    """Full v0.5 pipeline: downsample → preprocess → vtracer → sanitize."""
    import vtracer

    params = params or VectorizeParams()
    t0 = time.perf_counter()
    report = on_progress or (lambda _s, _p: None)

    report("Planning resolution", 0.04)
    max_side = clamp_process_size(
        params.overrides.get("max_process_size", params.max_process_size)
    )
    work, plan = downsample_image(img, max_side)
    vt = apply_preset(params.preset_id, params.overrides, auto_tune=False)
    vt["max_process_size"] = max_side

    # Colour mode override from UI
    if vt.get("force_binary"):
        vt["colormode"] = "binary"
        vt["preprocess_mode"] = "laser_bw"
    elif vt.get("force_color"):
        if vt.get("colormode") == "binary":
            vt["colormode"] = "color"

    report("Edge-aware preprocess", 0.15)
    pre_mode = str(vt.get("preprocess_mode", "logo"))
    prepared = preprocess_for_vectorize(
        work,
        mode=pre_mode,
        invert=bool(vt.get("invert", False)),
        edge_strength=float(vt.get("edge_strength", 0.55)),
        denoise=float(vt.get("denoise", 0.35)),
        contrast=float(vt.get("contrast", 0.55)),
        threshold_bias=float(vt.get("threshold_bias", 0.5)),
        compound_levels=int(vt.get("compound_levels", 6)),
    )
    pre_note = describe_preprocess(vt)

    report(f"Vectorizing @ {plan.label}", 0.35)

    with tempfile.TemporaryDirectory(prefix="vectorforge_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "input.png"
        dst = tmp_path / "output.svg"
        prepared.save(src, format="PNG", optimize=False)

        report("Running vtracer", 0.5)
        kwargs = dict(
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
        try:
            vtracer.convert_image_to_svg_py(str(src), str(dst), **kwargs)
        except TypeError:
            # Older bindings without some kwargs
            slim = {
                k: kwargs[k]
                for k in (
                    "colormode",
                    "hierarchical",
                    "mode",
                    "filter_speckle",
                    "color_precision",
                    "corner_threshold",
                    "length_threshold",
                    "path_precision",
                )
            }
            vtracer.convert_image_to_svg_py(str(src), str(dst), **slim)

        report("Sanitizing SVG", 0.9)
        svg = dst.read_text(encoding="utf-8")

    svg = _sanitize_svg_for_cad(svg, width=prepared.width, height=prepared.height)

    meta = (
        f"<!-- VectorForge {__import__('vectorforge').__version__} "
        f"| preset={params.preset_id} | {pre_note} "
        f"| working={plan.label} | max_side={max_side} -->\n"
    )
    if svg.lstrip().startswith("<?xml"):
        parts = svg.split("\n", 1)
        svg = parts[0] + "\n" + meta + (parts[1] if len(parts) > 1 else "")
    else:
        svg = meta + svg

    paths, nodes = _count_svg_stats(svg)
    ms = int((time.perf_counter() - t0) * 1000)
    report("Done", 1.0)

    return VectorResult(
        svg=svg,
        width=prepared.width,
        height=prepared.height,
        path_count=paths,
        node_estimate=nodes,
        duration_ms=ms,
        process_label=plan.label,
        params=vt,
        warning=plan.warning,
        preprocess_note=pre_note,
    )


def save_svg(result: VectorResult, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(result.svg, encoding="utf-8")
    return p
