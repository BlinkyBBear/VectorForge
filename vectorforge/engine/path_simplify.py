"""
Post-trace path simplify (Inkscape Path → Simplify style).

Works on exported SVG path data from Potrace/centerline.
- Closed paths stay closed (Z preserved; endpoints welded).
- Letter counters are separate paths — each simplified independently.
- Iterative RDP only (no recursion depth risk).
Offline, no heavy deps.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable


_PATH_TAG = re.compile(r'(<path\b[^>]*\bd=")([^"]+)(")', re.I)
_TOKEN = re.compile(
    r"([MLCZmlcz])|([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
)


@dataclass
class SimplifyStats:
    paths: int
    nodes_before: int
    nodes_after: int
    strength: float
    auto: bool


def _point_line_dist(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    denom = math.hypot(dx, dy)
    if denom < 1e-12:
        return math.hypot(px - ax, py - ay)
    return abs(dy * px - dx * py + bx * ay - by * ax) / denom


def _rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    """Iterative Ramer–Douglas–Peucker for open polylines."""
    if len(points) < 3 or epsilon <= 0:
        return points
    stack = [(0, len(points) - 1)]
    keep = {0, len(points) - 1}
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        ax, ay = points[start]
        bx, by = points[end]
        max_d = -1.0
        max_i = start
        for i in range(start + 1, end):
            d = _point_line_dist(points[i], points[start], points[end])
            if d > max_d:
                max_d = d
                max_i = i
        if max_d > epsilon:
            keep.add(max_i)
            stack.append((start, max_i))
            stack.append((max_i, end))
    return [points[i] for i in sorted(keep)]


def _rdp_closed(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    """
    Closed-ring RDP: drop duplicate close point, split ring at two anchors,
    RDP each arc, re-close. Never collapses to a single point pair.
    """
    if len(points) < 4 or epsilon <= 0:
        return points
    pts = list(points)
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 0.05:
        pts = pts[:-1]
    n = len(pts)
    if n < 3:
        return points
    # Anchor A: leftmost then bottom-most
    a = min(range(n), key=lambda i: (pts[i][0], pts[i][1]))
    # Anchor B: farthest from A (rough diameter)
    b = max(range(n), key=lambda i: math.hypot(pts[i][0] - pts[a][0], pts[i][1] - pts[a][1]))
    if a == b:
        return points

    def arc(i0: int, i1: int) -> list[tuple[float, float]]:
        out = [pts[i0]]
        i = (i0 + 1) % n
        guard = 0
        while i != i1 and guard < n + 2:
            out.append(pts[i])
            i = (i + 1) % n
            guard += 1
        out.append(pts[i1])
        return out

    arc1 = _rdp(arc(a, b), epsilon)
    arc2 = _rdp(arc(b, a), epsilon)
    # merge, drop duplicate junction
    merged = arc1[:-1] + arc2[:-1]
    if len(merged) < 3:
        # too aggressive — lighten
        return _rdp_closed(points, epsilon * 0.4) if epsilon > 0.05 else points
    # re-close
    merged.append(merged[0])
    return merged


def _simplify_poly(
    points: list[tuple[float, float]], epsilon: float, *, closed: bool
) -> list[tuple[float, float]]:
    if epsilon <= 0 or len(points) < 3:
        return points
    if closed:
        return _rdp_closed(points, epsilon)
    return _rdp(points, epsilon)


def _cubic(
    p0: tuple[float, float],
    c1: tuple[float, float],
    c2: tuple[float, float],
    p1: tuple[float, float],
    steps: int,
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for s in range(1, steps + 1):
        t = s / steps
        u = 1.0 - t
        x = (
            u**3 * p0[0]
            + 3 * u**2 * t * c1[0]
            + 3 * u * t**2 * c2[0]
            + t**3 * p1[0]
        )
        y = (
            u**3 * p0[1]
            + 3 * u**2 * t * c1[1]
            + 3 * u * t**2 * c2[1]
            + t**3 * p1[1]
        )
        out.append((x, y))
    return out


def _parse_d_to_polylines(d: str) -> tuple[list[list[tuple[float, float]]], bool]:
    """Parse M/L/C/Z path into polylines. Returns (polys, was_closed_any)."""
    tokens: list[str | float] = []
    for m in _TOKEN.finditer(d or ""):
        if m.group(1):
            tokens.append(m.group(1))
        else:
            tokens.append(float(m.group(2)))

    polys: list[list[tuple[float, float]]] = []
    i = 0
    cx = cy = 0.0
    current: list[tuple[float, float]] = []
    any_closed = False

    def take(n: int) -> list[float]:
        nonlocal i
        vals: list[float] = []
        for _ in range(n):
            while i < len(tokens) and not isinstance(tokens[i], (int, float)):
                i += 1
            if i >= len(tokens):
                break
            vals.append(float(tokens[i]))  # type: ignore[arg-type]
            i += 1
        return vals

    while i < len(tokens):
        if not isinstance(tokens[i], str):
            i += 1
            continue
        cmd = str(tokens[i])
        i += 1
        if cmd in ("M", "m"):
            if len(current) >= 2:
                polys.append(current)
            vals = take(2)
            if len(vals) < 2:
                break
            if cmd == "m":
                cx, cy = cx + vals[0], cy + vals[1]
            else:
                cx, cy = vals[0], vals[1]
            current = [(cx, cy)]
            while i < len(tokens) and isinstance(tokens[i], (int, float)):
                vals = take(2)
                if len(vals) < 2:
                    break
                if cmd == "m":
                    cx, cy = cx + vals[0], cy + vals[1]
                else:
                    cx, cy = vals[0], vals[1]
                current.append((cx, cy))
                cmd = "l" if cmd == "m" else "L"
        elif cmd in ("L", "l"):
            while i < len(tokens) and isinstance(tokens[i], (int, float)):
                vals = take(2)
                if len(vals) < 2:
                    break
                if cmd == "l":
                    cx, cy = cx + vals[0], cy + vals[1]
                else:
                    cx, cy = vals[0], vals[1]
                current.append((cx, cy))
        elif cmd in ("C", "c"):
            while i < len(tokens) and isinstance(tokens[i], (int, float)):
                vals = take(6)
                if len(vals) < 6:
                    break
                if cmd == "c":
                    c1 = (cx + vals[0], cy + vals[1])
                    c2 = (cx + vals[2], cy + vals[3])
                    end = (cx + vals[4], cy + vals[5])
                else:
                    c1 = (vals[0], vals[1])
                    c2 = (vals[2], vals[3])
                    end = (vals[4], vals[5])
                # densify for RDP
                span = math.hypot(end[0] - cx, end[1] - cy)
                steps = max(4, min(24, int(span / 2.0) + 4))
                current.extend(_cubic((cx, cy), c1, c2, end, steps))
                cx, cy = end
        elif cmd in ("Z", "z"):
            if current:
                if current[0] != current[-1]:
                    current.append(current[0])
                polys.append(current)
                current = []
                any_closed = True
        else:
            pass

    if len(current) >= 2:
        # open subpath
        polys.append(current)
    # Detect closed without Z (first≈last)
    closed_flag = any_closed
    for poly in polys:
        if len(poly) >= 3:
            if math.hypot(poly[0][0] - poly[-1][0], poly[0][1] - poly[-1][1]) < 0.05:
                closed_flag = True
    return polys, closed_flag


def _poly_to_d(poly: list[tuple[float, float]], *, closed: bool) -> str:
    if len(poly) < 2:
        return ""
    # Drop duplicate closing point if present; re-add via Z
    pts = list(poly)
    if (
        closed
        and len(pts) >= 2
        and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 0.05
    ):
        pts = pts[:-1]
    if len(pts) < 2:
        return ""
    parts = [f"M{pts[0][0]:.3f},{pts[0][1]:.3f}"]
    for x, y in pts[1:]:
        parts.append(f"L{x:.3f},{y:.3f}")
    if closed:
        # weld: ensure last near first then Z
        parts.append("Z")
    return " ".join(parts)


def _count_nodes_in_d(d: str) -> int:
    return len(re.findall(r"[MLCQSTmlcqst]", d or ""))


def strength_to_epsilon(strength: float, *, path_scale: float = 1.0) -> float:
    """
    Map 0–1 UI strength to RDP epsilon in path units.
    0 = off; 0.3 mild; 1.0 aggressive but still shape-preserving for CNC logos.
    """
    s = max(0.0, min(1.0, float(strength)))
    if s < 0.005:
        return 0.0
    # ~0.25px at s=0.1 … ~4px at s=1.0 (scaled)
    return (0.15 + s * s * 3.8 + s * 1.2) * max(0.5, path_scale)


def simplify_path_d(d: str, strength: float, *, path_scale: float = 1.0) -> str:
    """Simplify one path d string. Preserves closed vs open."""
    eps = strength_to_epsilon(strength, path_scale=path_scale)
    if eps <= 0:
        return d
    polys, closed = _parse_d_to_polylines(d)
    if not polys:
        return d
    out_parts: list[str] = []
    for poly in polys:
        if len(poly) < 3:
            out_parts.append(_poly_to_d(poly, closed=False))
            continue
        # Detect this subpath closed
        sub_closed = closed and (
            math.hypot(poly[0][0] - poly[-1][0], poly[0][1] - poly[-1][1]) < 0.5
            or "Z" in d
            or "z" in d
        )
        # If original path was closed overall and single poly, force closed
        if closed and len(polys) == 1:
            sub_closed = True
        simplified = _simplify_poly(poly, eps, closed=sub_closed)
        min_pts = 4 if sub_closed else 2
        # Progressive fallback if over-simplified
        e2 = eps
        while len(simplified) < min_pts and e2 > 0.02 and len(poly) >= min_pts:
            e2 *= 0.45
            simplified = _simplify_poly(poly, e2, closed=sub_closed)
        if len(simplified) < min_pts:
            simplified = poly  # refuse to destroy geometry
        if sub_closed and len(simplified) >= 2:
            if math.hypot(simplified[0][0] - simplified[-1][0], simplified[0][1] - simplified[-1][1]) > 0.01:
                simplified = list(simplified) + [simplified[0]]
        dd = _poly_to_d(simplified, closed=sub_closed)
        if dd:
            out_parts.append(dd)
    if not out_parts:
        return d
    # Join multi-subpath
    if len(out_parts) == 1:
        return out_parts[0]
    # Multiple M segments in one path
    return " ".join(out_parts)


def simplify_svg_paths(
    svg: str,
    strength: float,
    *,
    auto_if_dense: bool = True,
    dense_nodes_per_path: float = 90.0,
    auto_strength: float = 0.18,
) -> tuple[str, SimplifyStats]:
    """
    Apply extra simplify to all path d= attributes in SVG.
    If strength≈0 and auto_if_dense, apply light auto when node density high.
    """
    s = max(0.0, min(1.0, float(strength)))
    auto = False
    paths = list(_PATH_TAG.finditer(svg or ""))
    if not paths:
        return svg, SimplifyStats(0, 0, 0, 0.0, False)

    nodes_before = sum(_count_nodes_in_d(m.group(2)) for m in paths)
    npp = nodes_before / max(1, len(paths))
    if s < 0.005 and auto_if_dense and npp >= dense_nodes_per_path:
        s = float(auto_strength)
        auto = True
    if s < 0.005:
        return svg, SimplifyStats(len(paths), nodes_before, nodes_before, 0.0, False)

    # path scale from viewBox for epsilon
    path_scale = 1.0
    m = re.search(r'viewBox="0\s+0\s+([\d.]+)\s+([\d.]+)"', svg or "")
    if m:
        side = max(float(m.group(1)), float(m.group(2)))
        # normalize so 1000px image ~ scale 1
        path_scale = max(0.5, side / 1000.0)

    def repl(match: re.Match[str]) -> str:
        pre, d, post = match.group(1), match.group(2), match.group(3)
        nd = simplify_path_d(d, s, path_scale=path_scale)
        return f"{pre}{nd}{post}"

    new_svg = _PATH_TAG.sub(repl, svg)
    paths_after = list(_PATH_TAG.finditer(new_svg))
    nodes_after = sum(_count_nodes_in_d(m.group(2)) for m in paths_after)
    return new_svg, SimplifyStats(
        paths=len(paths_after),
        nodes_before=nodes_before,
        nodes_after=nodes_after,
        strength=s,
        auto=auto,
    )
