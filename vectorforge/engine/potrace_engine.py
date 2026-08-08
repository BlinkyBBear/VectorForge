"""
Potrace-based outline engine (v1.0 primary for CNC / logo / B&W).

Uses pure-Python `potracer` (offline, no system binary required).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import cv2
import numpy as np
from PIL import Image

from potrace import (
    Bitmap,
    CornerSegment,
    POTRACE_TURNPOLICY_MINORITY,
    POTRACE_TURNPOLICY_MAJORITY,
    POTRACE_TURNPOLICY_BLACK,
    POTRACE_TURNPOLICY_WHITE,
)

OutputStyle = Literal["outline", "fill"]


@dataclass
class PathStats:
    path_count: int
    node_estimate: int


def _turnpolicy(name: str) -> int:
    n = (name or "minority").lower()
    return {
        "minority": POTRACE_TURNPOLICY_MINORITY,
        "majority": POTRACE_TURNPOLICY_MAJORITY,
        "black": POTRACE_TURNPOLICY_BLACK,
        "white": POTRACE_TURNPOLICY_WHITE,
    }.get(n, POTRACE_TURNPOLICY_MINORITY)


def _curve_to_d(curve) -> tuple[str, int]:
    sp = curve.start_point
    if sp is None:
        return "", 0
    parts = [f"M{sp.x:.3f},{sp.y:.3f}"]
    nodes = 1
    for seg in curve:
        if isinstance(seg, CornerSegment) or seg.is_corner:
            c = seg.c
            end = seg.end_point
            parts.append(f"L{c.x:.3f},{c.y:.3f}")
            parts.append(f"L{end.x:.3f},{end.y:.3f}")
            nodes += 2
        else:
            c1, c2, end = seg.c1, seg.c2, seg.end_point
            parts.append(
                f"C{c1.x:.3f},{c1.y:.3f} {c2.x:.3f},{c2.y:.3f} {end.x:.3f},{end.y:.3f}"
            )
            nodes += 3
    parts.append("Z")
    return " ".join(parts), nodes


def _path_bbox_area(curve) -> float:
    xs: list[float] = []
    ys: list[float] = []
    if curve.start_point is not None:
        xs.append(float(curve.start_point.x))
        ys.append(float(curve.start_point.y))
    for seg in curve:
        if seg.is_corner:
            xs.extend([float(seg.c.x), float(seg.end_point.x)])
            ys.extend([float(seg.c.y), float(seg.end_point.y)])
        else:
            xs.append(float(seg.end_point.x))
            ys.append(float(seg.end_point.y))
    if not xs:
        return 0.0
    return max(0.0, (max(xs) - min(xs)) * (max(ys) - min(ys)))


def _ensure_min_resolution(gray: np.ndarray, min_side: int = 1400) -> tuple[np.ndarray, float]:
    """
    Upscale small bitmaps with nearest-neighbour so Potrace has enough pixels.
    Returns (scaled_gray, scale_factor). scale_factor is used to note original size.
    """
    h, w = gray.shape[:2]
    side = max(h, w)
    if side >= min_side:
        return gray, 1.0
    scale = min_side / float(side)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    # nearest keeps binary edges crisp
    scaled = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_NEAREST)
    return scaled, scale


def potrace_binary_to_svg(
    binary_bw: np.ndarray | Image.Image,
    *,
    style: OutputStyle = "outline",
    turdsize: int = 2,
    alphamax: float = 1.0,
    opticurve: bool = True,
    opttolerance: float = 0.2,
    turnpolicy: str = "minority",
    stroke_width: float = 1.0,
    filter_border: bool = True,
    blacklevel: float = 0.5,
    min_trace_side: int = 1400,
) -> tuple[str, PathStats]:
    """
    binary_bw: grayscale where dark (near 0) is ink to vectorize.
    style outline → stroke only (CNC cut paths)
    style fill → filled black with evenodd (laser engrave / solid logos)
    """
    if isinstance(binary_bw, Image.Image):
        gray = np.array(binary_bw.convert("L"), dtype=np.uint8)
    else:
        gray = np.asarray(binary_bw)
        if gray.ndim == 3:
            gray = gray[:, :, 0]
        gray = gray.astype(np.uint8)

    orig_h, orig_w = gray.shape[:2]

    # Force pure binary (no residual grays that create double contours)
    _, pure = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    gray = pure

    # Upscale small logos — critical for clean Potrace geometry
    gray, scale = _ensure_min_resolution(gray, min_side=min_trace_side)
    h, w = gray.shape[:2]

    bl = float(np.clip(blacklevel, 0.02, 0.98))
    bm = Bitmap(gray, blacklevel=bl)
    traced = bm.trace(
        turdsize=int(max(0, turdsize)),
        turnpolicy=_turnpolicy(turnpolicy),
        alphamax=float(alphamax),
        opticurve=bool(opticurve),
        opttolerance=float(opttolerance),
    )

    img_area = float(w * h)
    path_elems: list[str] = []
    total_nodes = 0
    path_count = 0

    # Scale path coords back to original image size if we upscaled
    inv = 1.0 / scale if scale != 1.0 else 1.0

    for curve in traced:
        area = abs(getattr(curve._path, "area", 0))
        bbox_area = _path_bbox_area(curve)
        if filter_border and (
            area > img_area * 0.92 or bbox_area > img_area * 0.98
        ):
            continue

        d, nodes = _curve_to_d(curve)
        if not d:
            continue

        # Rescale coordinates to original pixel space
        if inv != 1.0:
            # simple numeric scale of all floats in the path
            import re as _re

            def _scale_num(m: _re.Match[str]) -> str:
                return f"{float(m.group(0)) * inv:.3f}"

            d = _re.sub(r"-?\d+\.\d+|-?\d+", _scale_num, d)

        total_nodes += nodes
        path_count += 1
        if style == "outline":
            path_elems.append(
                f'<path d="{d}" fill="none" stroke="#000000" '
                f'stroke-width="{stroke_width}" stroke-linejoin="round" '
                f'stroke-linecap="round"/>'
            )
        else:
            path_elems.append(
                f'<path d="{d}" fill="#000000" stroke="none" fill-rule="evenodd"/>'
            )

    body = "\n  ".join(path_elems)
    # Emit SVG at original dimensions
    out_w, out_h = orig_w, orig_h
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{out_w}" height="{out_h}" viewBox="0 0 {out_w} {out_h}">\n'
        f"  {body}\n"
        f"</svg>\n"
    )
    return svg, PathStats(path_count=path_count, node_estimate=total_nodes)


def potrace_params_from_ui(params: dict[str, Any]) -> dict[str, Any]:
    detail = float(params.get("detail", 0.85))
    simplify = float(params.get("simplify_strength", 0.2))
    turd = int(params.get("turdsize", max(0, round(1 + (1 - detail) * 8 + simplify * 6))))
    opttol = float(
        params.get(
            "opttolerance",
            max(0.05, 0.12 + (1 - detail) * 0.35 + simplify * 0.25),
        )
    )
    alphamax = float(params.get("alphamax", 0.9 + detail * 0.1))
    return {
        "turdsize": int(params.get("turdsize", turd)),
        "alphamax": float(params.get("alphamax", alphamax)),
        "opticurve": bool(params.get("opticurve", True)),
        "opttolerance": float(params.get("opttolerance", opttol)),
        "turnpolicy": str(params.get("turnpolicy", "minority")),
        "stroke_width": float(params.get("stroke_width", 1.0)),
        "blacklevel": float(params.get("blacklevel", 0.5)),
    }
