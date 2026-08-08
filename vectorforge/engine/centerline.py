"""
Centerline / Skeleton vectorization (Inkscape Trace Bitmap → Centerline style).

Pipeline:
  B&W binary (ink=0) → invert to ink=255 → Zhang-Suen thinning →
  spur prune → chain extract → RDP simplify → open stroke SVG paths

Offline, pure NumPy/OpenCV — no opencv-contrib required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np
from PIL import Image


@dataclass
class PathStats:
    path_count: int
    node_estimate: int


# ---------------------------------------------------------------------------
# Zhang–Suen thinning (iterative, non-recursive)
# ---------------------------------------------------------------------------

def _neighbours(img: np.ndarray, y: int, x: int) -> list[int]:
    # P2..P9 clockwise from north
    return [
        int(img[y - 1, x]),
        int(img[y - 1, x + 1]),
        int(img[y, x + 1]),
        int(img[y + 1, x + 1]),
        int(img[y + 1, x]),
        int(img[y + 1, x - 1]),
        int(img[y, x - 1]),
        int(img[y - 1, x - 1]),
    ]


def zhang_suen_thin(binary_ink255: np.ndarray, *, max_iter: int = 200) -> np.ndarray:
    """
    binary_ink255: uint8, ink=255, bg=0.
    Returns skeleton with ink=255.
    """
    img = (binary_ink255 > 0).astype(np.uint8)
    # pad to avoid border checks
    img = np.pad(img, 1, mode="constant")
    changed = True
    it = 0
    while changed and it < max_iter:
        it += 1
        changed = False
        for step in (0, 1):
            to_remove: list[tuple[int, int]] = []
            ys, xs = np.where(img == 1)
            for y, x in zip(ys.tolist(), xs.tolist()):
                if y == 0 or x == 0 or y == img.shape[0] - 1 or x == img.shape[1] - 1:
                    continue
                p2, p3, p4, p5, p6, p7, p8, p9 = _neighbours(img, y, x)
                b = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
                if b < 2 or b > 6:
                    continue
                a = 0
                seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
                for i in range(8):
                    if seq[i] == 0 and seq[i + 1] == 1:
                        a += 1
                if a != 1:
                    continue
                if step == 0:
                    if p2 * p4 * p6 != 0:
                        continue
                    if p4 * p6 * p8 != 0:
                        continue
                else:
                    if p2 * p4 * p8 != 0:
                        continue
                    if p2 * p6 * p8 != 0:
                        continue
                to_remove.append((y, x))
            if to_remove:
                changed = True
                for y, x in to_remove:
                    img[y, x] = 0
    return (img[1:-1, 1:-1] * 255).astype(np.uint8)


def morphological_skeleton(binary_ink255: np.ndarray) -> np.ndarray:
    """
    Fast OpenCV morphological skeleton (hit-or-miss style via erode+open).
    Used as fallback / speed path for large images; still offline.
    """
    img = (binary_ink255 > 0).astype(np.uint8) * 255
    skel = np.zeros_like(img)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    guard = 0
    while True:
        guard += 1
        if guard > 5000:
            break
        eroded = cv2.erode(img, element)
        opened = cv2.morphologyEx(eroded, cv2.MORPH_OPEN, element)
        temp = cv2.subtract(eroded, opened)
        skel = cv2.bitwise_or(skel, temp)
        img = eroded.copy()
        if cv2.countNonZero(img) == 0:
            break
    return skel


def thin_ink_mask(
    binary_bw: np.ndarray,
    *,
    method: str = "auto",
) -> np.ndarray:
    """
    binary_bw: 0=ink, 255=bg (VectorForge convention).
    Returns skeleton 0=ink, 255=bg for preview, plus ink255 skeleton internal.
    """
    ink = np.where(binary_bw < 128, 255, 0).astype(np.uint8)
    # Light close so thin strokes don't break before thinning
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, k, iterations=1)

    h, w = ink.shape[:2]
    n_ink = int(np.count_nonzero(ink))
    # Zhang-Suen is O(pixels*iters); use morph skeleton on large dense masks
    use_zs = method == "zhang_suen" or (
        method == "auto" and n_ink < 120_000 and max(h, w) <= 2200
    )
    if use_zs:
        sk = zhang_suen_thin(ink)
    else:
        sk = morphological_skeleton(ink)
        # single-pixel clean-up: hit-miss residual blobs
        sk = cv2.morphologyEx(sk, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        # re-thin with one ZS pass if small enough after morph
        if n_ink < 250_000:
            sk = zhang_suen_thin(sk)

    # Ensure 1px: any leftover thick pixels
    return sk


def prune_spurs(skel_ink255: np.ndarray, min_branch_len: int = 8) -> np.ndarray:
    """
    Iteratively remove endpoint chains shorter than min_branch_len.
    skel: ink=255.
    """
    min_branch_len = max(1, int(min_branch_len))
    img = (skel_ink255 > 0).astype(np.uint8)
    h, w = img.shape

    def degree(y: int, x: int) -> int:
        y0, y1 = max(0, y - 1), min(h, y + 2)
        x0, x1 = max(0, x - 1), min(w, x + 2)
        return int(img[y0:y1, x0:x1].sum() - img[y, x])

    def neighbours(y: int, x: int) -> list[tuple[int, int]]:
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and img[ny, nx]:
                    out.append((ny, nx))
        return out

    changed = True
    guard = 0
    while changed and guard < 50:
        guard += 1
        changed = False
        endpoints = [
            (y, x)
            for y, x in zip(*np.where(img == 1))
            if degree(y, x) == 1
        ]
        for ey, ex in endpoints:
            if not img[ey, ex]:
                continue
            chain = [(ey, ex)]
            cy, cx = ey, ex
            prev = None
            while True:
                nbs = [n for n in neighbours(cy, cx) if n != prev]
                if len(nbs) != 1:
                    break
                prev = (cy, cx)
                cy, cx = nbs[0]
                chain.append((cy, cx))
                if degree(cy, cx) != 2:
                    break
                if len(chain) > min_branch_len + 2:
                    break
            # If we ended at junction or stop and chain is short → spur
            end_deg = degree(chain[-1][0], chain[-1][1]) if chain else 0
            if len(chain) < min_branch_len and end_deg != 1:
                for y, x in chain[:-1]:  # keep junction pixel
                    img[y, x] = 0
                changed = True
            elif len(chain) < min_branch_len and end_deg == 1 and len(chain) > 1:
                # isolated short segment (two endpoints)
                for y, x in chain:
                    img[y, x] = 0
                changed = True
    return (img * 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Chain extraction + simplify
# ---------------------------------------------------------------------------

def _rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    """Iterative Ramer–Douglas–Peucker."""
    if len(points) < 3 or epsilon <= 0:
        return points
    stack = [(0, len(points) - 1)]
    keep = {0, len(points) - 1}
    pts = points
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        ax, ay = pts[start]
        bx, by = pts[end]
        dx, dy = bx - ax, by - ay
        denom = (dx * dx + dy * dy) ** 0.5 or 1.0
        max_d = -1.0
        max_i = start
        for i in range(start + 1, end):
            px, py = pts[i]
            # perpendicular distance
            d = abs(dy * px - dx * py + bx * ay - by * ax) / denom
            if d > max_d:
                max_d = d
                max_i = i
        if max_d > epsilon:
            keep.add(max_i)
            stack.append((start, max_i))
            stack.append((max_i, end))
    return [pts[i] for i in sorted(keep)]


def extract_chains(
    skel_ink255: np.ndarray,
    *,
    min_points: int = 3,
) -> list[list[tuple[int, int]]]:
    img = (skel_ink255 > 0).astype(np.uint8)
    h, w = img.shape
    visited = np.zeros_like(img, dtype=np.uint8)

    def nbs(y: int, x: int) -> list[tuple[int, int]]:
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and img[ny, nx]:
                    out.append((ny, nx))
        return out

    def deg(y: int, x: int) -> int:
        return len(nbs(y, x))

    chains: list[list[tuple[int, int]]] = []
    # Start from endpoints first, then leftover loops
    coords = list(zip(*np.where(img == 1)))
    endpoints = [(y, x) for y, x in coords if deg(y, x) == 1]
    junctions = {(y, x) for y, x in coords if deg(y, x) >= 3}
    starts = endpoints + [c for c in coords if c not in endpoints]

    for sy, sx in starts:
        if visited[sy, sx]:
            continue
        # Walk
        chain = [(sy, sx)]
        visited[sy, sx] = 1
        cy, cx = sy, sx
        prev = None
        while True:
            options = [n for n in nbs(cy, cx) if n != prev and not visited[n[0], n[1]]]
            # allow one step into already-visited junction to close branch cleanly
            if not options:
                jopts = [
                    n
                    for n in nbs(cy, cx)
                    if n != prev and n in junctions
                ]
                if jopts and (jopts[0][0], jopts[0][1]) != (sy, sx):
                    chain.append(jopts[0])
                break
            # prefer continuing straight-ish: pick first unvisited
            ny, nx = options[0]
            if len(options) > 1 and prev is not None:
                # choose neighbor maximizing collinearity
                pdx, pdy = cy - prev[0], cx - prev[1]
                best = None
                best_s = -1e9
                for oy, ox in options:
                    dx, dy = oy - cy, ox - cx
                    score = dx * pdx + dy * pdy
                    if score > best_s:
                        best_s = score
                        best = (oy, ox)
                ny, nx = best  # type: ignore[misc]
            chain.append((ny, nx))
            visited[ny, nx] = 1
            prev = (cy, cx)
            cy, cx = ny, nx
            if (cy, cx) in junctions and len(chain) > 1:
                # stop at junction so other branches start separately
                # but mark junction unvisited for other chains? keep visited
                break
            if deg(cy, cx) == 1 and len(chain) > 1:
                break
        if len(chain) >= min_points:
            chains.append(chain)

    return chains



def merge_short_chains(
    chains: list[list[tuple[int, int]]],
    *,
    max_gap: float = 2.5,
) -> list[list[tuple[int, int]]]:
    """Greedily join chains whose endpoints nearly touch (rebuild longer strokes)."""
    if len(chains) < 2:
        return chains
    used = [False] * len(chains)
    out: list[list[tuple[int, int]]] = []

    def ends(ch):
        return ch[0], ch[-1]

    def dist(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    for i, ch in enumerate(chains):
        if used[i]:
            continue
        used[i] = True
        cur = list(ch)
        extended = True
        while extended:
            extended = False
            head, tail = cur[0], cur[-1]
            best = None
            best_j = -1
            best_mode = ""
            for j, other in enumerate(chains):
                if used[j]:
                    continue
                o0, o1 = other[0], other[-1]
                candidates = [
                    (dist(tail, o0), "tail-o0", other),
                    (dist(tail, o1), "tail-o1", list(reversed(other))),
                    (dist(head, o1), "head-o1", other),
                    (dist(head, o0), "head-o0", list(reversed(other))),
                ]
                for d, mode, seq in candidates:
                    if d <= max_gap and (best is None or d < best):
                        best = d
                        best_j = j
                        best_mode = mode
                        best_seq = seq
            if best_j >= 0:
                used[best_j] = True
                if best_mode.startswith("tail"):
                    cur = cur + best_seq[1:]
                else:
                    cur = best_seq[:-1] + cur
                extended = True
        out.append(cur)
    return out


def chains_to_svg(
    chains: list[list[tuple[int, int]]],
    *,
    width: int,
    height: int,
    stroke_width: float = 1.0,
    simplify: float = 1.2,
) -> tuple[str, PathStats]:
    path_elems: list[str] = []
    total_nodes = 0
    for ch in chains:
        # pixel centers
        pts = [(float(x) + 0.5, float(y) + 0.5) for y, x in ch]
        pts = _rdp(pts, simplify)
        if len(pts) < 2:
            continue
        d_parts = [f"M{pts[0][0]:.2f},{pts[0][1]:.2f}"]
        for x, y in pts[1:]:
            d_parts.append(f"L{x:.2f},{y:.2f}")
        d = " ".join(d_parts)
        # open path — no Z (centerline)
        total_nodes += len(pts)
        path_elems.append(
            f'<path d="{d}" fill="none" stroke="#000000" '
            f'stroke-width="{stroke_width}" stroke-linecap="round" '
            f'stroke-linejoin="round"/>'
        )
    body = "\n  ".join(path_elems)
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f"  {body}\n"
        f"</svg>\n"
    )
    return svg, PathStats(path_count=len(path_elems), node_estimate=total_nodes)


def centerline_binary_to_svg(
    binary_bw: np.ndarray | Image.Image,
    *,
    min_branch_len: int = 12,
    spur_prune: float = 0.65,
    simplify: float = 1.2,
    stroke_width: float = 1.0,
    thin_method: str = "auto",
) -> tuple[str, PathStats, Image.Image]:
    """
    Full centerline pass.
    binary_bw: 0=ink, 255=bg.
    spur_prune 0–1 scales min_branch_len.
    Returns (svg, stats, skeleton_preview_rgb).
    """
    if isinstance(binary_bw, Image.Image):
        gray = np.array(binary_bw.convert("L"), dtype=np.uint8)
    else:
        gray = np.asarray(binary_bw)
        if gray.ndim == 3:
            gray = gray[:, :, 0]
        gray = gray.astype(np.uint8)

    h, w = gray.shape[:2]
    sk = thin_ink_mask(gray, method=thin_method)
    mbl = int(round(float(min_branch_len) * (0.35 + 0.9 * float(np.clip(spur_prune, 0, 1)))))
    mbl = max(2, mbl)
    sk = prune_spurs(sk, min_branch_len=mbl)
    chains = extract_chains(sk, min_points=3)
    # drop very short chains (pixel count)
    min_len = max(4, mbl // 2)
    chains = [c for c in chains if len(c) >= min_len]
    # reconnect fragments that meet at endpoints (cleaner single strokes)
    chains = merge_short_chains(chains, max_gap=3.0)
    chains = [c for c in chains if len(c) >= min_len]
    svg, stats = chains_to_svg(
        chains,
        width=w,
        height=h,
        stroke_width=stroke_width,
        simplify=max(0.6, float(simplify)),
    )
    # Preview: skeleton black on white
    preview = np.full((h, w, 3), 255, dtype=np.uint8)
    preview[sk > 0] = (0, 0, 0)
    preview_img = Image.fromarray(preview, "RGB")
    return svg, stats, preview_img
