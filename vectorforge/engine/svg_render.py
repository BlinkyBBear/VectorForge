"""
Rasterize SVG path data for live on-canvas preview (no Cairo required).

Supports the subset we emit: M/L/C/Z paths with fill or stroke.
"""

from __future__ import annotations

import re

from PIL import Image, ImageDraw


def parse_path_elements(svg: str) -> list[dict]:
    out = []
    for m in re.finditer(r"<path\b([^>]*)/?>", svg, flags=re.I):
        attrs = m.group(1)
        dm = re.search(r'\bd="([^"]+)"', attrs)
        if not dm:
            continue
        fill_m = re.search(r'\bfill="([^"]+)"', attrs)
        stroke_m = re.search(r'\bstroke="([^"]+)"', attrs)
        sw_m = re.search(r'\bstroke-width="([^"]+)"', attrs)
        fill = fill_m.group(1) if fill_m else "none"
        stroke = stroke_m.group(1) if stroke_m else "none"
        sw = float(sw_m.group(1)) if sw_m else 1.0
        out.append({"d": dm.group(1), "fill": fill, "stroke": stroke, "sw": sw})
    return out


def path_d_to_points(d: str, samples: int = 10) -> list[tuple[float, float]]:
    tokens = re.findall(
        r"([MLCZmlcz])|([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)",
        d,
    )
    items: list[str | float] = []
    for t in tokens:
        if t[0]:
            items.append(t[0])
        else:
            items.append(float(t[1]))

    pts: list[tuple[float, float]] = []
    i = 0
    cx = cy = sx = sy = 0.0

    def take_num() -> float:
        nonlocal i
        while i < len(items) and not isinstance(items[i], (int, float)):
            i += 1
        if i >= len(items):
            return 0.0
        v = float(items[i])  # type: ignore[arg-type]
        i += 1
        return v

    while i < len(items):
        if not isinstance(items[i], str):
            i += 1
            continue
        cmd = str(items[i])
        i += 1
        if cmd in ("M", "m"):
            x, y = take_num(), take_num()
            if cmd == "m":
                cx, cy = cx + x, cy + y
            else:
                cx, cy = x, y
            sx, sy = cx, cy
            pts.append((cx, cy))
            while i < len(items) and isinstance(items[i], (int, float)):
                x, y = take_num(), take_num()
                if cmd == "m":
                    cx, cy = cx + x, cy + y
                else:
                    cx, cy = x, y
                pts.append((cx, cy))
                cmd = "l" if cmd == "m" else "L"
        elif cmd in ("L", "l"):
            while i < len(items) and isinstance(items[i], (int, float)):
                x, y = take_num(), take_num()
                if cmd == "l":
                    cx, cy = cx + x, cy + y
                else:
                    cx, cy = x, y
                pts.append((cx, cy))
        elif cmd in ("C", "c"):
            while i < len(items) and isinstance(items[i], (int, float)):
                vals = [take_num() for _ in range(6)]
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
                x0, y0 = cx, cy
                for s in range(1, samples + 1):
                    t = s / samples
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
                    pts.append((x, y))
                cx, cy = end
        elif cmd in ("Z", "z"):
            pts.append((sx, sy))
            cx, cy = sx, sy
    return pts


def render_svg_preview(
    svg: str,
    *,
    max_side: int = 900,
    bg: tuple[int, int, int] = (245, 245, 247),
) -> Image.Image:
    """Rasterize SVG paths into a PIL image for UI preview."""
    w = h = 512
    m = re.search(r'viewBox="0\s+0\s+([\d.]+)\s+([\d.]+)"', svg)
    if m:
        w, h = max(1, int(float(m.group(1)))), max(1, int(float(m.group(2))))
    else:
        wm = re.search(r'width="([\d.]+)"', svg)
        hm = re.search(r'height="([\d.]+)"', svg)
        if wm and hm:
            w, h = int(float(wm.group(1))), int(float(hm.group(1)))

    scale = min(1.0, max_side / max(w, h))
    dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
    img = Image.new("RGB", (dw, dh), bg)
    draw = ImageDraw.Draw(img)

    for p in parse_path_elements(svg):
        pts = path_d_to_points(p["d"])
        if len(pts) < 2:
            continue
        scaled = [(x * scale, y * scale) for x, y in pts]
        fill = p["fill"]
        stroke = p["stroke"]
        if fill and fill.lower() not in ("none", "transparent"):
            try:
                draw.polygon(scaled, fill=fill)
            except Exception:
                pass
        if stroke and stroke.lower() not in ("none", "transparent"):
            sw = max(1, int(round(p["sw"] * scale)))
            try:
                draw.line(scaled, fill=stroke, width=sw, joint="curve")
            except TypeError:
                draw.line(scaled, fill=stroke, width=sw)
    return img
