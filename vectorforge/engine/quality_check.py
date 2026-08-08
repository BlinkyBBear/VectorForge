"""Lightweight post-vectorize SVG path health check (laser / CNC readiness)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QualityReport:
    path_count: int
    closed_count: int
    open_count: int
    node_estimate: int
    nodes_per_path: float
    tip: str
    ok: bool


_PATH_RE = re.compile(r"<path\b([^>]*)/?>", re.I)
_D_RE = re.compile(r'\bd="([^"]*)"', re.I)
_CMD_RE = re.compile(r"[MLCQSTmlcqst]")


def _path_looks_closed(d: str) -> bool:
    s = (d or "").strip()
    if not s:
        return False
    if "Z" in s or "z" in s:
        return True
    nums = re.findall(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", s)
    if len(nums) >= 4:
        try:
            x0, y0 = float(nums[0]), float(nums[1])
            x1, y1 = float(nums[-2]), float(nums[-1])
            if abs(x0 - x1) < 0.05 and abs(y0 - y1) < 0.05:
                return True
        except ValueError:
            pass
    return False


def analyze_svg_quality(svg: str) -> QualityReport:
    paths = list(_PATH_RE.finditer(svg or ""))
    path_count = len(paths)
    closed = open_n = nodes = 0
    for m in paths:
        dm = _D_RE.search(m.group(1))
        d = dm.group(1) if dm else ""
        nodes += len(_CMD_RE.findall(d))
        if _path_looks_closed(d):
            closed += 1
        else:
            open_n += 1

    npp = (nodes / path_count) if path_count else 0.0

    if path_count == 0:
        tip = "No paths produced — adjust Raster prep / Binary mask"
        ok = False
    elif open_n > 0 and open_n >= max(1, path_count // 4):
        tip = "Warning: some paths may be open — check in LightBurn/Fusion"
        ok = False
    elif path_count > 0 and npp > 120:
        tip = "Warning: high node density — try higher Curve optimize or Silhouette"
        ok = False
    elif closed == path_count and path_count > 0:
        tip = f"Laser-ready: {path_count} closed path{'s' if path_count != 1 else ''}"
        ok = True
    else:
        tip = f"OK: {path_count} paths ({closed} closed)"
        ok = open_n == 0

    return QualityReport(
        path_count=path_count,
        closed_count=closed,
        open_count=open_n,
        node_estimate=nodes,
        nodes_per_path=round(npp, 1),
        tip=tip,
        ok=ok,
    )
