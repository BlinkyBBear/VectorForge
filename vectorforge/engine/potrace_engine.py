"""
Potrace-based outline engine (v1.0 primary for CNC / logo / B&W).

Uses pure-Python `potracer` (offline, no system binary required).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

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

    h, w = gray.shape[:2]
    bm = Bitmap(gray, blacklevel=0.5)
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
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
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
    }
