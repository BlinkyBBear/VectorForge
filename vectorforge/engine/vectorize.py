"""
VectorForge v1.0 pipeline.

CNC / Logo / B&W → preprocess → Potrace
Colour / Photo    → preprocess → vtracer
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from vectorforge import __version__

from .image_ops import downsample_image
from .memory import clamp_process_size
from .potrace_engine import potrace_binary_to_svg, potrace_params_from_ui
from .preprocess import (
    describe_preprocess,
    preprocess_binary_for_potrace,
    preprocess_bw_compound,
    preprocess_color_for_vtracer,
)
from .presets import DEFAULT_PRESET_ID, apply_preset

ProgressCb = Callable[[str, float], None]


@dataclass
class VectorizeParams:
    preset_id: str = DEFAULT_PRESET_ID
    max_process_size: int = 3600
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
    preview_png: Image.Image | None = None
    engine: str = "potrace"


def _count_svg_stats(svg: str) -> tuple[int, int]:
    paths = len(re.findall(r"<path\b", svg, flags=re.I))
    nodes = len(re.findall(r"[MLCQSTmlcqst]", svg))
    return paths, nodes


def _sanitize_svg(svg: str, *, width: int, height: int) -> str:
    svg = re.sub(r"<script[\s\S]*?</script>", "", svg, flags=re.I)
    if "xmlns=" not in svg[:500]:
        svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    if "viewBox" not in svg[:600]:
        svg = re.sub(
            r"<svg([^>]*)>",
            rf'<svg\1 viewBox="0 0 {width} {height}">',
            svg,
            count=1,
        )
    return svg


def _vtracer_svg(img: Image.Image, vt: dict[str, Any], report: ProgressCb) -> str:
    import vtracer

    report("Running vtracer", 0.55)
    with tempfile.TemporaryDirectory(prefix="vf_") as tmp:
        src = Path(tmp) / "in.png"
        dst = Path(tmp) / "out.svg"
        img.save(src, format="PNG")
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
        return dst.read_text(encoding="utf-8")


def vectorize_image(
    img: Image.Image,
    params: VectorizeParams | None = None,
    on_progress: ProgressCb | None = None,
) -> VectorResult:
    params = params or VectorizeParams()
    t0 = time.perf_counter()
    report = on_progress or (lambda _s, _p: None)

    report("Planning resolution", 0.04)
    max_side = clamp_process_size(
        params.overrides.get("max_process_size", params.max_process_size)
    )
    work, plan = downsample_image(img, max_side)
    vt = apply_preset(params.preset_id, params.overrides)
    vt["max_process_size"] = max_side
    engine = str(vt.get("engine", "potrace")).lower()

    preview_img: Image.Image | None = None
    svg: str

    if engine == "potrace":
        report("Preprocess (outline)", 0.15)
        preview_img, binary = preprocess_binary_for_potrace(
            work,
            denoise=float(vt.get("denoise", 0.35)),
            contrast=float(vt.get("contrast", 0.28)),
            edge_strength=float(vt.get("edge_strength", 0.30)),
            threshold_method=str(vt.get("threshold_method", "otsu")),
            blacklevel=float(vt.get("blacklevel", 0.5)),
            invert=bool(vt.get("invert", False)),
        )
        report("Potrace", 0.5)
        pkwargs = potrace_params_from_ui(vt)
        style = str(vt.get("output_style", "outline"))
        if style not in ("outline", "fill"):
            style = "outline"
        svg, stats = potrace_binary_to_svg(
            binary,
            style=style,  # type: ignore[arg-type]
            **pkwargs,
        )
        path_count, node_estimate = stats.path_count, stats.node_estimate
    else:
        report("Preprocess (colour)", 0.15)
        if vt.get("preprocess_mode") == "bw_compound" or params.preset_id == "bw_compound":
            prepared = preprocess_bw_compound(
                work,
                levels=int(vt.get("compound_levels", 6)),
                denoise=float(vt.get("denoise", 0.3)),
                contrast=float(vt.get("contrast", 0.5)),
            )
        else:
            prepared = preprocess_color_for_vtracer(
                work,
                denoise=float(vt.get("denoise", 0.3)),
                contrast=float(vt.get("contrast", 0.45)),
                edge_strength=float(vt.get("edge_strength", 0.4)),
            )
        preview_img = prepared
        svg = _vtracer_svg(prepared, vt, report)
        path_count, node_estimate = _count_svg_stats(svg)

    report("Sanitize SVG", 0.9)
    w = work.width
    h = work.height
    m = re.search(r'viewBox="0\s+0\s+([\d.]+)\s+([\d.]+)"', svg)
    if m:
        w, h = int(float(m.group(1))), int(float(m.group(2)))
    svg = _sanitize_svg(svg, width=w, height=h)

    meta = (
        f"<!-- VectorForge {__version__} | preset={params.preset_id} "
        f"| {describe_preprocess(vt)} | working={plan.label} -->\n"
    )
    if svg.lstrip().startswith("<?xml"):
        parts = svg.split("\n", 1)
        svg = parts[0] + "\n" + meta + (parts[1] if len(parts) > 1 else "")
    else:
        svg = meta + svg

    ms = int((time.perf_counter() - t0) * 1000)
    report("Done", 1.0)

    return VectorResult(
        svg=svg,
        width=w,
        height=h,
        path_count=path_count,
        node_estimate=node_estimate,
        duration_ms=ms,
        process_label=plan.label,
        params=vt,
        warning=plan.warning,
        preprocess_note=describe_preprocess(vt),
        preview_png=preview_img,
        engine=engine,
    )


def save_svg(result: VectorResult, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(result.svg, encoding="utf-8")
    return p
