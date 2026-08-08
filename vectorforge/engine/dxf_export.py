"""
Minimal DXF (R12-ish) exporter from SVG path data for CNC / CAD import.

Produces LWPOLYLINE-like LINE and bulk POLYLINE approximations of cubic beziers.
Fully offline, no external deps.
"""

from __future__ import annotations

import math
import re
from pathlib import Path


def _parse_path_d(d: str) -> list[list[tuple[float, float]]]:
    """Parse simple SVG path (M/L/C/Z from our exporter) → list of closed polylines."""
    tokens = re.findall(
        r"([MLCZmlcz])|([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)",
        d,
    )
    cmds: list[str | float] = []
    for t in tokens:
        if t[0]:
            cmds.append(t[0])
        else:
            cmds.append(float(t[1]))

    polylines: list[list[tuple[float, float]]] = []
    i = 0
    cx = cy = 0.0
    current: list[tuple[float, float]] = []

    def take(n: int) -> list[float]:
        nonlocal i
        vals = []
        for _ in range(n):
            while i < len(cmds) and not isinstance(cmds[i], (int, float)):
                i += 1
            if i >= len(cmds):
                break
            vals.append(float(cmds[i]))  # type: ignore[arg-type]
            i += 1
        return vals

    while i < len(cmds):
        if not isinstance(cmds[i], str):
            i += 1
            continue
        cmd = str(cmds[i])
        i += 1
        if cmd in ("M", "m"):
            if current and len(current) >= 2:
                polylines.append(current)
            vals = take(2)
            if len(vals) < 2:
                break
            if cmd == "m":
                cx, cy = cx + vals[0], cy + vals[1]
            else:
                cx, cy = vals[0], vals[1]
            current = [(cx, cy)]
            # implicit lineto pairs
            while i < len(cmds) and isinstance(cmds[i], (int, float)):
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
            while i < len(cmds) and isinstance(cmds[i], (int, float)):
                vals = take(2)
                if len(vals) < 2:
                    break
                if cmd == "l":
                    cx, cy = cx + vals[0], cy + vals[1]
                else:
                    cx, cy = vals[0], vals[1]
                current.append((cx, cy))
        elif cmd in ("C", "c"):
            while i < len(cmds) and isinstance(cmds[i], (int, float)):
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
                # sample cubic
                x0, y0 = cx, cy
                steps = 8
                for s in range(1, steps + 1):
                    t = s / steps
                    u = 1 - t
                    x = (
                        u**3 * x0
                        + 3 * u**2 * t * c1[0]
                        + 3 * u * t**2 * c2[0]
                        + t**3 * end[0]
                    )
                    y = (
                        u**3 * y0
                        + 3 * u**2 * t * c1[1]
                        + 3 * u * t**2 * c2[1]
                        + t**3 * end[1]
                    )
                    current.append((x, y))
                cx, cy = end
        elif cmd in ("Z", "z"):
            if current:
                if current[0] != current[-1]:
                    current.append(current[0])
                polylines.append(current)
                current = []
        else:
            # skip unknown
            pass

    if current and len(current) >= 2:
        polylines.append(current)
    return polylines


def svg_to_dxf(svg: str, *, flip_y: bool = True) -> str:
    """Convert our SVG paths to a simple ASCII DXF."""
    height = 1000.0
    m = re.search(r'viewBox="0\s+0\s+([\d.]+)\s+([\d.]+)"', svg)
    if m:
        height = float(m.group(2))
    paths = re.findall(r'<path\b[^>]*\bd="([^"]+)"', svg, flags=re.I)
    entities: list[str] = []

    def emit_polyline(pts: list[tuple[float, float]]) -> None:
        if len(pts) < 2:
            return
        # POLYLINE
        entities.append("0\nPOLYLINE\n8\n0\n66\n1\n70\n1\n")
        for x, y in pts:
            yy = (height - y) if flip_y else y
            entities.append(f"0\nVERTEX\n8\n0\n10\n{x:.4f}\n20\n{yy:.4f}\n")
        entities.append("0\nSEQEND\n")

    for d in paths:
        for poly in _parse_path_d(d):
            emit_polyline(poly)

    dxf = (
        "0\nSECTION\n2\nHEADER\n"
        "0\nENDSEC\n"
        "0\nSECTION\n2\nTABLES\n0\nENDSEC\n"
        "0\nSECTION\n2\nBLOCKS\n0\nENDSEC\n"
        "0\nSECTION\n2\nENTITIES\n"
        + "".join(entities)
        + "0\nENDSEC\n0\nEOF\n"
    )
    return dxf


def save_dxf(svg: str, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(svg_to_dxf(svg), encoding="utf-8")
    return p
