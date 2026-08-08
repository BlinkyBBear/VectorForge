"""
v1.0 preprocessing — mkbitmap-inspired pipeline for geometric fidelity.

Official Potrace quality comes from mkbitmap order:
  greyscale → highpass → light blur → INTERPOLATED scale-up → threshold → potrace

We previously thresholded first then nearest-upscaled binary (wrong order).
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from PIL import Image


def flatten_rgba(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    rgba = img.convert("RGBA")
    base = Image.new("RGBA", rgba.size, (*bg, 255))
    return Image.alpha_composite(base, rgba).convert("RGB")


def to_gray_u8(img: Image.Image) -> np.ndarray:
    rgb = np.array(flatten_rgba(img), dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def highpass(gray: np.ndarray, radius: float = 4.0) -> np.ndarray:
    """
    mkbitmap-style highpass: subtract local mean so lines/text stay while
    uneven backgrounds flatten. radius ~ filter scale in pixels.
    """
    r = max(1.0, float(radius))
    k = int(r * 2) | 1
    blur = cv2.GaussianBlur(gray, (k, k), r)
    # highpass residual mapped back to 0..255 mid-grey
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
    """Interpolate greyscale UP before threshold (mkbitmap core idea)."""
    f = float(factor)
    if f <= 1.01:
        return gray
    h, w = gray.shape[:2]
    nw, nh = int(round(w * f)), int(round(h * f))
    # cubic preserves more edge energy than linear for logos
    return cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_CUBIC)


def threshold_for_outline(
    gray: np.ndarray,
    *,
    method: str = "otsu",
    blacklevel: float = 0.5,
    invert: bool = False,
) -> np.ndarray:
    """Return binary uint8: 0 = ink, 255 = background."""
    g = gray
    method = (method or "otsu").lower()
    if method == "adaptive":
        ink_white = cv2.adaptiveThreshold(
            g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 8
        )
    elif method == "fixed":
        thr = int(np.clip(blacklevel, 0.02, 0.98) * 255)
        _, ink_white = cv2.threshold(g, thr, 255, cv2.THRESH_BINARY_INV)
    else:
        _, ink_white = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    if invert:
        ink_white = cv2.bitwise_not(ink_white)

    return cv2.bitwise_not(ink_white)  # 0=ink, 255=bg


def light_morphology(binary_bw: np.ndarray, denoise: float) -> np.ndarray:
    s = float(np.clip(denoise, 0.0, 1.0))
    if s < 0.15:
        return binary_bw
    ink = cv2.bitwise_not(binary_bw)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, k, iterations=1)
    if s >= 0.7:
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, k, iterations=1)
    return cv2.bitwise_not(ink)


def preprocess_binary_for_potrace(
    img: Image.Image,
    *,
    denoise: float = 0.35,
    contrast: float = 0.28,
    edge_strength: float = 0.30,
    threshold_method: str = "otsu",
    blacklevel: float = 0.5,
    invert: bool = False,
    scale_factor: float | None = None,
) -> tuple[Image.Image, np.ndarray]:
    """
    mkbitmap order:
      gray → denoise → highpass(edge) → contrast → scale UP → threshold → morph

    Returns (preview RGB, binary 0=ink for Potrace Bitmap).
    """
    gray = to_gray_u8(img)
    gray = denoise_gray(gray, denoise)

    # Highpass strength follows edge_strength (0 = skip)
    if edge_strength > 0.08:
        radius = 2.0 + edge_strength * 6.0  # ~2–8 px
        gray = highpass(gray, radius=radius)

    gray = enhance_contrast(gray, contrast)

    # Scale greyscale BEFORE threshold (critical for small logos)
    h, w = gray.shape[:2]
    side = max(h, w)
    if scale_factor is None:
        # aim for ~1600px side after scale, clamp 1–4×
        target = 1600.0
        scale_factor = float(np.clip(target / max(side, 1), 1.0, 4.0))
    gray = scale_greyscale(gray, scale_factor)

    binary = threshold_for_outline(
        gray,
        method=threshold_method,
        blacklevel=blacklevel,
        invert=invert,
    )
    binary = light_morphology(binary, denoise)

    # Auto-invert if ink dominates (typical wrong polarity)
    ink_frac = float(np.mean(binary < 128))
    if ink_frac > 0.55 and not invert:
        binary = cv2.bitwise_not(binary)

    preview = Image.fromarray(cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB), "RGB")
    return preview, binary


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
        f"edge={float(params.get('edge_strength', 0)):.2f} "
        f"denoise={float(params.get('denoise', 0)):.2f} "
        f"contrast={float(params.get('contrast', 0)):.2f}"
    )
