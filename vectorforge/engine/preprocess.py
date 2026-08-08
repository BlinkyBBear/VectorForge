"""
v1.0+ preprocessing — mkbitmap-inspired + logo/text morphology.

Pipeline for CNC / logo outlines:
  greyscale → denoise → highpass(radius) → contrast → scale UP (cubic) → threshold
  → mild close (keep letter strokes continuous) → despeckle → Potrace

Highpass radius and scale factor are user-controllable (Advanced Raster prep).
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from PIL import Image

AUTO_SCALE_TARGET = 1700.0


def flatten_rgba(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    rgba = img.convert("RGBA")
    base = Image.new("RGBA", rgba.size, (*bg, 255))
    return Image.alpha_composite(base, rgba).convert("RGB")


def to_gray_u8(img: Image.Image) -> np.ndarray:
    rgb = np.array(flatten_rgba(img), dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def highpass(gray: np.ndarray, radius: float = 4.0) -> np.ndarray:
    """
    mkbitmap-style highpass. radius 0 = off.
    Larger radius keeps thicker features; smaller isolates fine lines.
    """
    r = float(radius)
    if r < 0.15:
        return gray
    r = max(0.5, r)
    k = int(r * 2) | 1
    if k < 3:
        k = 3
    blur = cv2.GaussianBlur(gray, (k, k), r)
    # classic: original - blur + mid; mild boost like previous 1.5/-0.5
    hp = cv2.addWeighted(gray, 1.5, blur, -0.5, 128)
    return np.clip(hp, 0, 255).astype(np.uint8)


def denoise_gray(gray: np.ndarray, strength: float) -> np.ndarray:
    s = float(np.clip(strength, 0.0, 1.0))
    if s < 0.05:
        return gray
    if s < 0.35:
        return cv2.medianBlur(gray, 3)
    if s < 0.7:
        return cv2.bilateralFilter(gray, 5, 40, 40)
    return cv2.bilateralFilter(gray, 7, 55, 55)


def enhance_contrast(gray: np.ndarray, amount: float) -> np.ndarray:
    a = float(np.clip(amount, 0.0, 1.0))
    if a < 0.05:
        return gray
    clip = 0.8 + a * 1.6
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    return clahe.apply(gray)


def scale_greyscale(gray: np.ndarray, factor: float) -> np.ndarray:
    """Cubic upscale of greyscale BEFORE threshold."""
    f = float(factor)
    if f <= 1.01:
        return gray
    f = min(f, 4.0)
    h, w = gray.shape[:2]
    nw, nh = int(round(w * f)), int(round(h * f))
    # safety cap
    max_side = 6000
    long = max(nw, nh)
    if long > max_side:
        s = max_side / long
        nw = max(1, int(round(nw * s)))
        nh = max(1, int(round(nh * s)))
    return cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_CUBIC)


def resolve_scale_factor(
    width: int,
    height: int,
    scale_factor: float | None,
    *,
    auto: bool = True,
) -> float:
    """Explicit >= 1.01 wins; else auto toward ~1700px long side (1–4)."""
    if scale_factor is not None and float(scale_factor) >= 1.01 and not auto:
        return float(np.clip(float(scale_factor), 1.0, 4.0))
    if scale_factor is not None and float(scale_factor) >= 1.01:
        return float(np.clip(float(scale_factor), 1.0, 4.0))
    side = max(width, height, 1)
    return float(np.clip(AUTO_SCALE_TARGET / side, 1.0, 4.0))


def threshold_hard(
    gray: np.ndarray,
    *,
    method: str = "otsu",
    blacklevel: float = 0.5,
    invert: bool = False,
) -> np.ndarray:
    """Pure binary: 0 = ink, 255 = background."""
    method = (method or "otsu").lower()
    if method == "adaptive":
        ink_white = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 6
        )
    elif method == "fixed":
        thr = int(np.clip(blacklevel, 0.02, 0.98) * 255)
        _, ink_white = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY_INV)
    else:
        _, ink_white = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

    if invert:
        ink_white = cv2.bitwise_not(ink_white)

    _, pure = cv2.threshold(ink_white, 127, 255, cv2.THRESH_BINARY)
    return cv2.bitwise_not(pure)


def logo_text_morphology(binary_bw: np.ndarray, denoise: float) -> np.ndarray:
    """binary_bw: 0=ink, 255=bg. Mild close + open + CC despeckle."""
    s = float(np.clip(denoise, 0.0, 1.0))
    ink = cv2.bitwise_not(binary_bw)

    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, k_close, iterations=1)

    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, k_open, iterations=1)

    min_area = int(8 + s * 40)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    cleaned = np.zeros_like(ink)
    for i in range(1, n_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            cleaned[labels == i] = 255
    ink = cleaned
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, k_close, iterations=1)
    return cv2.bitwise_not(ink)


def preprocess_binary_for_potrace(
    img: Image.Image,
    *,
    denoise: float = 0.40,
    contrast: float = 0.25,
    edge_strength: float = 0.25,
    threshold_method: str = "otsu",
    blacklevel: float = 0.5,
    invert: bool = False,
    scale_factor: float | None = None,
    highpass_radius: float | None = None,
    auto_scale: bool = True,
    logo_text: bool = True,
) -> tuple[Image.Image, np.ndarray, dict[str, Any]]:
    """
    Returns (binary preview RGB, binary 0=ink, meta with applied hp/scale).

    highpass_radius: px, 0 = off. If None, derived from edge_strength (legacy).
    scale_factor: 1–4 explicit; if None/0 and auto_scale, target ~1700px.
    """
    gray = to_gray_u8(img)
    gray = denoise_gray(gray, denoise)

    # Highpass radius (explicit Advanced control, or legacy edge_strength mapping)
    if highpass_radius is None:
        if edge_strength > 0.08:
            hp_r = 2.0 + float(edge_strength) * 5.0  # ~2–7
        else:
            hp_r = 0.0
    else:
        hp_r = float(np.clip(float(highpass_radius), 0.0, 12.0))

    if hp_r > 0.1:
        gray = highpass(gray, radius=hp_r)

    gray = enhance_contrast(gray, contrast)

    h, w = gray.shape[:2]
    if scale_factor is not None and float(scale_factor) >= 1.01:
        # Explicit Advanced scale factor
        sf = resolve_scale_factor(w, h, float(scale_factor), auto=False)
    elif auto_scale:
        # Simple mode / default: grow toward ~1700px
        sf = resolve_scale_factor(w, h, None, auto=True)
    else:
        # Explicit 1.0 (or missing) with auto_scale off
        sf = 1.0
    gray = scale_greyscale(gray, sf)

    binary = threshold_hard(
        gray,
        method=threshold_method,
        blacklevel=blacklevel,
        invert=invert,
    )

    if logo_text:
        binary = logo_text_morphology(binary, denoise)
    else:
        if denoise > 0.15:
            ink = cv2.bitwise_not(binary)
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
            ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, k, iterations=1)
            binary = cv2.bitwise_not(ink)

    ink_frac = float(np.mean(binary < 128))
    if ink_frac > 0.55 and not invert:
        binary = cv2.bitwise_not(binary)
        ink_frac = 1.0 - ink_frac

    _, binary = cv2.threshold(binary, 127, 255, cv2.THRESH_BINARY)

    preview = Image.fromarray(cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB), "RGB")
    meta = {
        "highpass_radius": round(hp_r, 2),
        "scale_factor": round(float(sf), 3),
        "binary_size": (int(binary.shape[1]), int(binary.shape[0])),
        "ink_fraction": round(ink_frac, 4),
    }
    return preview, binary, meta


def preprocess_color_for_vtracer(
    img: Image.Image,
    *,
    denoise: float = 0.3,
    contrast: float = 0.45,
    edge_strength: float = 0.4,
) -> Image.Image:
    rgb = np.array(flatten_rgba(img), dtype=np.uint8)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    s = float(np.clip(denoise, 0.0, 1.0))
    if s >= 0.1:
        d = 5 if s < 0.5 else 7
        bgr = cv2.bilateralFilter(bgr, d, 30 + s * 40, 30 + s * 40)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    if contrast > 0.05:
        clip = 0.8 + float(contrast) * 1.5
        l = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(l)
    if edge_strength > 0.05:
        blur = cv2.GaussianBlur(l, (0, 0), 1.0)
        l = cv2.addWeighted(l, 1.0 + edge_strength * 0.6, blur, -edge_strength * 0.6, 0)
    lab = cv2.merge([l, a, b])
    bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb, "RGB")


def preprocess_bw_compound(
    img: Image.Image,
    *,
    levels: int = 6,
    denoise: float = 0.3,
    contrast: float = 0.5,
) -> Image.Image:
    gray = to_gray_u8(img)
    gray = denoise_gray(gray, denoise)
    gray = enhance_contrast(gray, contrast)
    n = int(np.clip(levels, 2, 12))
    step = max(1, 256 // n)
    q = ((gray // step) * step + step // 2).astype(np.uint8)
    return Image.fromarray(cv2.cvtColor(q, cv2.COLOR_GRAY2RGB), "RGB")


def describe_preprocess(params: dict[str, Any]) -> str:
    eng = params.get("engine", "?")
    return (
        f"engine={eng} thr={params.get('threshold_method', '-')} "
        f"hp={float(params.get('highpass_radius', 0)):.1f} "
        f"scale={float(params.get('scale_factor', 1)):.2f} "
        f"denoise={float(params.get('denoise', 0)):.2f} "
        f"contrast={float(params.get('contrast', 0)):.2f}"
    )
