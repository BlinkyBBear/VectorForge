"""
Potrace-based outline engine (v1.0.2).

Silhouette tiers (Soft / Normal / Aggressive):
  A OUTER/PRIMARY — borders, main silhouettes
  B MAJOR ELEMENTS — text blocks, secondary animals, icons (kept in Soft+Normal)
  C INTERNAL/JUNK — fur lines, speckles (dropped in silhouette)

Fabrication hardening: closed paths, micro-gap weld, near-duplicate stroke cull.
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
SilhouetteStrength = Literal["soft", "normal", "aggressive"]


@dataclass
class PathStats:
    path_count: int
    node_estimate: int


@dataclass
class _Cand:
    area: float
    sign: int
    d: str
    nodes: int
    cx: float
    cy: float
    bw: float
    bh: float


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
    xs = [float(sp.x)]
    ys = [float(sp.y)]
    for seg in curve:
        if isinstance(seg, CornerSegment) or seg.is_corner:
            c = seg.c
            end = seg.end_point
            parts.append(f"L{c.x:.3f},{c.y:.3f}")
            parts.append(f"L{end.x:.3f},{end.y:.3f}")
            nodes += 2
            xs.extend([float(c.x), float(end.x)])
            ys.extend([float(c.y), float(end.y)])
        else:
            c1, c2, end = seg.c1, seg.c2, seg.end_point
            parts.append(
                f"C{c1.x:.3f},{c1.y:.3f} {c2.x:.3f},{c2.y:.3f} {end.x:.3f},{end.y:.3f}"
            )
            nodes += 3
            xs.append(float(end.x))
            ys.append(float(end.y))
    # Always close for laser/CNC cut geometry
    parts.append("Z")
    return " ".join(parts), nodes


def _curve_bbox(curve) -> tuple[float, float, float, float]:
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
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def _path_bbox_area(curve) -> float:
    x0, y0, x1, y1 = _curve_bbox(curve)
    return max(0.0, (x1 - x0) * (y1 - y0))


def _ensure_closed_d(d: str) -> str:
    s = (d or "").strip()
    if not s:
        return s
    if not s.rstrip().endswith(("Z", "z")):
        s = s + " Z"
    return s


def _dedupe_near_parallel(
    cands: list[_Cand], *, area_tol: float = 0.12, center_tol_frac: float = 0.03
) -> list[_Cand]:
    """
    Drop near-duplicate paths (double parallel strokes of the same edge).
    Keep the one with fewer nodes when area+centroid match.
    """
    if len(cands) < 2:
        return cands
    # sort largest first so we prefer primary outlines
    ordered = sorted(cands, key=lambda c: c.area, reverse=True)
    kept: list[_Cand] = []
    for c in ordered:
        dup = False
        for k in kept:
            if k.area <= 0:
                continue
            ar = abs(c.area - k.area) / max(k.area, 1.0)
            if ar > area_tol:
                continue
            # center distance relative to average bbox size
            scale = max(k.bw, k.bh, c.bw, c.bh, 1.0)
            dist = ((c.cx - k.cx) ** 2 + (c.cy - k.cy) ** 2) ** 0.5
            if dist <= scale * center_tol_frac and ar <= area_tol:
                # same-ish stroke — keep fewer nodes
                if c.nodes < k.nodes:
                    kept[kept.index(k)] = c
                dup = True
                break
        if not dup:
            kept.append(c)
    return kept


def _silhouette_floors(
    *,
    img_area: float,
    largest: float,
    second: float,
    min_path_area: float,
    strength: str,
) -> tuple[float, float, float]:
    """
    Returns (junk_floor, major_floor, hole_floor).

    Tier B (MAJOR) uses absolute image-area floor + fraction of *second*
    largest path so a huge diamond border does not erase text/icons.

    Aggressive reintroduces strong largest-relative cut (old ~5-path behaviour).
    """
    s = (strength or "normal").lower()
    mpa = max(1.0, float(min_path_area))
    # Prefer second-largest so a huge border does not dominate floors
    ref = max(second, 1.0)
    if s == "aggressive":
        # Old over-filter: dog + diamond (+few) only
        junk = max(mpa * 2, img_area * 0.0008, largest * 0.008)
        major = max(mpa * 8, img_area * 0.006, largest * 0.04)
        hole = max(mpa, img_area * 0.0008, largest * 0.004)
    elif s == "soft":
        junk = max(mpa * 0.4, img_area * 0.0001)
        major = max(mpa * 2, img_area * 0.0004, ref * 0.008)
        hole = max(mpa * 0.3, img_area * 0.00012, ref * 0.004)
    else:
        # Normal — keep text blocks, secondary animals, icons
        # floor ≈ max(min_area*4, 0.15% of image, 1% of second-largest)
        junk = max(mpa, img_area * 0.0002)  # C INTERNAL / speckles
        major = max(mpa * 4, img_area * 0.0015, ref * 0.01)  # B MAJOR
        hole = max(mpa * 0.8, img_area * 0.0003, ref * 0.006)
    return junk, major, hole


def _filter_silhouette(
    candidates: list[_Cand],
    *,
    img_area: float,
    min_path_area: float,
    strength: str,
) -> list[_Cand]:
    if not candidates:
        return []
    positives = [c for c in candidates if c.sign >= 0]
    holes = [c for c in candidates if c.sign < 0]
    areas = sorted((c.area for c in positives), reverse=True)
    largest = areas[0] if areas else 1.0
    second = areas[1] if len(areas) > 1 else largest

    junk_f, major_f, hole_f = _silhouette_floors(
        img_area=img_area,
        largest=largest,
        second=second,
        min_path_area=min_path_area,
        strength=strength,
    )

    s = (strength or "normal").lower()
    kept: list[_Cand] = []

    # Keep MAJOR (and OUTER which is always >= major) ink paths
    for c in positives:
        if c.area < junk_f:
            continue  # C INTERNAL/JUNK
        if c.area >= major_f:
            kept.append(c)
            continue
        # Soft: also keep mid-tier above junk
        if s == "soft" and c.area >= junk_f * 2:
            kept.append(c)

    # Letter counters / meaningful holes
    for c in holes:
        if c.area >= hole_f:
            kept.append(c)

    # Safety: never return fewer than 2 ink paths if available (border + content)
    ink_kept = [c for c in kept if c.sign >= 0]
    if len(ink_kept) < 2 and len(positives) >= 2:
        top = sorted(positives, key=lambda c: c.area, reverse=True)[: max(2, min(6, len(positives)))]
        for c in top:
            if c not in kept and c.area >= junk_f:
                kept.append(c)

    return kept


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
    outer_and_counters_only: bool = True,
    silhouette: bool = False,
    silhouette_strength: str = "normal",
    min_path_area: float = 40.0,
) -> tuple[str, PathStats]:
    """
    silhouette=True: tiered filter Soft/Normal/Aggressive.
    Always emits closed paths (Z) for cut geometry.
    """
    if isinstance(binary_bw, Image.Image):
        gray = np.array(binary_bw.convert("L"), dtype=np.uint8)
    else:
        gray = np.asarray(binary_bw)
        if gray.ndim == 3:
            gray = gray[:, :, 0]
        gray = gray.astype(np.uint8)

    h, w = gray.shape[:2]
    _, pure = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    gray = pure

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
    raw: list[_Cand] = []

    for curve in traced:
        area = abs(float(getattr(curve._path, "area", 0)))
        sign = int(getattr(curve._path, "sign", 1) or 1)
        bbox_area = _path_bbox_area(curve)
        x0, y0, x1, y1 = _curve_bbox(curve)

        if filter_border and (
            area > img_area * 0.92 or bbox_area > img_area * 0.98
        ):
            continue

        d, nodes = _curve_to_d(curve)
        if not d:
            continue
        d = _ensure_closed_d(d)
        cx = (x0 + x1) * 0.5
        cy = (y0 + y1) * 0.5
        raw.append(
            _Cand(
                area=area,
                sign=sign,
                d=d,
                nodes=nodes,
                cx=cx,
                cy=cy,
                bw=max(0.0, x1 - x0),
                bh=max(0.0, y1 - y0),
            )
        )

    if not raw:
        svg = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
            f"</svg>\n"
        )
        return svg, PathStats(0, 0)

    if silhouette:
        kept = _filter_silhouette(
            raw,
            img_area=img_area,
            min_path_area=min_path_area,
            strength=silhouette_strength,
        )
    elif outer_and_counters_only:
        kept = [c for c in raw if c.area >= min_path_area]
    else:
        kept = list(raw)

    # Cull double parallel strokes (laser failure mode)
    kept = _dedupe_near_parallel(kept)

    path_elems: list[str] = []
    total_nodes = 0
    path_count = 0
    # Stable order: large → small (outer first helps Fusion sketch)
    for c in sorted(kept, key=lambda x: x.area, reverse=True):
        total_nodes += c.nodes
        path_count += 1
        if style == "outline":
            path_elems.append(
                f'<path d="{c.d}" fill="none" stroke="#000000" '
                f'stroke-width="{stroke_width}" stroke-linejoin="round" '
                f'stroke-linecap="round"/>'
            )
        else:
            path_elems.append(
                f'<path d="{c.d}" fill="#000000" stroke="none" fill-rule="evenodd"/>'
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
    strength = str(params.get("silhouette_strength", "normal")).lower()
    if strength not in ("soft", "normal", "aggressive"):
        strength = "normal"
    return {
        "turdsize": int(params.get("turdsize", turd)),
        "alphamax": float(params.get("alphamax", alphamax)),
        "opticurve": bool(params.get("opticurve", True)),
        "opttolerance": float(params.get("opttolerance", opttol)),
        "turnpolicy": str(params.get("turnpolicy", "minority")),
        "stroke_width": float(params.get("stroke_width", 1.0)),
        "blacklevel": float(params.get("blacklevel", 0.5)),
        "outer_and_counters_only": bool(params.get("outer_and_counters_only", True)),
        "silhouette": bool(params.get("silhouette", False)),
        "silhouette_strength": strength,
        "min_path_area": float(params.get("min_path_area", 40.0)),
    }
