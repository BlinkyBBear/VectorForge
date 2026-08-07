"""
Background removal + click refinement (offline) — v0.5.

- rembg (U2Net) with strength control (alpha threshold + erode/dilate)
- Iterative wand / brush (never recursive)
"""

from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np
from PIL import Image

_rembg_session = None
_rembg_error: str | None = None


def _get_rembg_remove():
    global _rembg_session, _rembg_error
    if _rembg_error:
        return None
    try:
        from rembg import new_session, remove

        if _rembg_session is None:
            _rembg_session = new_session("u2net")
        return lambda img: remove(img, session=_rembg_session)
    except Exception as e:  # noqa: BLE001
        _rembg_error = str(e)
        return None


def auto_remove_background(
    img: Image.Image,
    *,
    prefer_ai: bool = True,
    tolerance: int = 36,
    strength: float = 0.55,
) -> Image.Image:
    """
    Isolate subject on transparent background.

    strength 0–1:
      low  → keep more edge fringe (gentler cut)
      high → harder alpha cutoff + slight erode (tighter subject)
    """
    rgba = img.convert("RGBA")
    strength = float(np.clip(strength, 0.0, 1.0))

    if prefer_ai:
        rem = _get_rembg_remove()
        if rem is not None:
            try:
                out = rem(rgba)
                if isinstance(out, bytes):
                    from io import BytesIO

                    out = Image.open(BytesIO(out)).convert("RGBA")
                else:
                    out = out.convert("RGBA")
                return _apply_alpha_strength(out, strength)
            except Exception:
                pass

    return _apply_alpha_strength(
        _corner_flood_remove(rgba, tolerance=tolerance),
        strength,
    )


def _apply_alpha_strength(img: Image.Image, strength: float) -> Image.Image:
    """Harder strength → higher alpha cutoff + morphological erode on mask."""
    arr = np.array(img.convert("RGBA"), dtype=np.uint8)
    alpha = arr[:, :, 3].astype(np.float32)
    # threshold: low strength keeps soft edges; high strength clips harder
    cutoff = 20 + strength * 100  # 20–120
    mask = (alpha >= cutoff).astype(np.uint8) * 255

    # erode for high strength (tighter), dilate for low (keep fringe)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    if strength > 0.6:
        iters = int(round((strength - 0.6) * 5))  # 0–2
        if iters > 0:
            mask = cv2.erode(mask, k, iterations=iters)
    elif strength < 0.4:
        iters = int(round((0.4 - strength) * 5))
        if iters > 0:
            mask = cv2.dilate(mask, k, iterations=iters)

    # feather 1px for mid strength
    if 0.35 < strength < 0.75:
        mask = cv2.GaussianBlur(mask, (3, 3), 0)

    arr[:, :, 3] = mask
    # zero RGB where fully transparent (cleaner exports)
    arr[mask < 8, 0:3] = 0
    return Image.fromarray(arr, "RGBA")


def _corner_flood_remove(img: Image.Image, tolerance: int = 36) -> Image.Image:
    """Iterative BFS from corners — no recursion, hard pixel budget."""
    arr = np.array(img.convert("RGBA"), dtype=np.uint8)
    h, w = arr.shape[:2]
    max_pixels = w * h
    visited = np.zeros((h, w), dtype=np.uint8)
    queue = np.empty(max_pixels, dtype=np.int32)
    qh = 0
    qt = 0

    seeds = [
        (0, 0),
        (w - 1, 0),
        (0, h - 1),
        (w - 1, h - 1),
        (w // 2, 0),
        (w // 2, h - 1),
        (0, h // 2),
        (w - 1, h // 2),
    ]
    seed_colors = [arr[sy, sx, :3].astype(np.int32) for sx, sy in seeds]

    def try_enq(x: int, y: int) -> None:
        nonlocal qt
        if x < 0 or y < 0 or x >= w or y >= h:
            return
        if visited[y, x]:
            return
        visited[y, x] = 1
        queue[qt] = y * w + x
        qt += 1

    for sx, sy in seeds:
        try_enq(sx, sy)

    tol2 = int(tolerance) * int(tolerance)
    filled = 0
    while qh < qt and filled < max_pixels:
        pi = int(queue[qh])
        qh += 1
        y, x = divmod(pi, w)
        pix = arr[y, x, :3].astype(np.int32)
        match = False
        for sc in seed_colors:
            d = pix - sc
            if int(d[0]) ** 2 + int(d[1]) ** 2 + int(d[2]) ** 2 <= tol2:
                match = True
                break
        if not match:
            continue
        arr[y, x, 3] = 0
        filled += 1
        try_enq(x - 1, y)
        try_enq(x + 1, y)
        try_enq(x, y - 1)
        try_enq(x, y + 1)

    return Image.fromarray(arr, "RGBA")


def wand_at(
    img: Image.Image,
    x: float,
    y: float,
    *,
    erase: bool = True,
    tolerance: int = 32,
) -> Image.Image:
    """Iterative magic-wand erase/restore from a click."""
    arr = np.array(img.convert("RGBA"), dtype=np.uint8)
    h, w = arr.shape[:2]
    cx = int(max(0, min(w - 1, round(x))))
    cy = int(max(0, min(h - 1, round(y))))
    target = arr[cy, cx].astype(np.int32)
    sr, sg, sb = int(target[0]), int(target[1]), int(target[2])
    if not erase and int(target[3]) < 16:
        for rad in range(1, 12):
            found = False
            for dy in range(-rad, rad + 1):
                for dx in range(-rad, rad + 1):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and arr[ny, nx, 3] > 200:
                        sr, sg, sb = map(int, arr[ny, nx, :3])
                        found = True
                        break
                if found:
                    break
            if found:
                break

    visited = np.zeros((h, w), dtype=np.uint8)
    max_pixels = w * h
    queue = np.empty(max_pixels, dtype=np.int32)
    qh = 0
    qt = 0
    visited[cy, cx] = 1
    queue[qt] = cy * w + cx
    qt += 1
    tol2 = int(tolerance) * int(tolerance)
    filled = 0
    tr, tg, tb = int(target[0]), int(target[1]), int(target[2])

    while qh < qt and filled < max_pixels:
        pi = int(queue[qh])
        qh += 1
        py, px = divmod(pi, w)
        pix = arr[py, px]
        d0 = int(pix[0]) - tr
        d1 = int(pix[1]) - tg
        d2 = int(pix[2]) - tb
        dist2 = d0 * d0 + d1 * d1 + d2 * d2
        a = int(pix[3])
        if erase:
            if not (dist2 <= tol2 or a < 8):
                continue
            arr[py, px, 3] = 0
        else:
            if not (dist2 <= tol2 or a < 128):
                continue
            arr[py, px, 0] = sr
            arr[py, px, 1] = sg
            arr[py, px, 2] = sb
            arr[py, px, 3] = 255
        filled += 1
        for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx]:
                visited[ny, nx] = 1
                queue[qt] = ny * w + nx
                qt += 1

    return Image.fromarray(arr, "RGBA")


def brush_stroke(
    img: Image.Image,
    points: Iterable[tuple[float, float]],
    *,
    radius: int = 12,
    erase: bool = True,
) -> Image.Image:
    """Circular brush erase/restore along a stroke (iterative stamps)."""
    arr = np.array(img.convert("RGBA"), dtype=np.uint8)
    h, w = arr.shape[:2]
    r = max(1, min(64, int(radius)))
    r2 = r * r
    pts = list(points)
    if not pts:
        return img.convert("RGBA")

    sr, sg, sb = 128, 128, 128
    if not erase:
        sx, sy = int(round(pts[0][0])), int(round(pts[0][1]))
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                nx, ny = sx + dx, sy + dy
                if 0 <= nx < w and 0 <= ny < h and arr[ny, nx, 3] > 200:
                    sr, sg, sb = map(int, arr[ny, nx, :3])
                    break

    if len(pts) > 4000:
        step = max(1, len(pts) // 4000)
        pts = pts[::step]

    for x, y in pts:
        cx, cy = int(round(x)), int(round(y))
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy > r2:
                    continue
                nx, ny = cx + dx, cy + dy
                if nx < 0 or ny < 0 or nx >= w or ny >= h:
                    continue
                if erase:
                    arr[ny, nx, 3] = 0
                else:
                    if arr[ny, nx, 3] < 16:
                        arr[ny, nx, 0] = sr
                        arr[ny, nx, 1] = sg
                        arr[ny, nx, 2] = sb
                    arr[ny, nx, 3] = 255

    return Image.fromarray(arr, "RGBA")


def rembg_status() -> str:
    rem = _get_rembg_remove()
    if rem is None:
        return f"rembg unavailable ({_rembg_error or 'not installed'}) — using flood-fill"
    return "rembg (u2net) ready — offline after model cache"
