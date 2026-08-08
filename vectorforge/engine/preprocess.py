"""
v1.0 preprocessing — geometric fidelity first.

For CNC Outline / Logo / Laser B&W:
  - Clean JPEG noise
  - Optional local contrast (gentle CLAHE)
  - Single Otsu OR fixed blacklevel threshold (NOT dual min-merge that floods)
  - Light morphology only when requested
  - Preserve thin strokes and holes

Never force solid black across large regions.
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
    # Gentle CLAHE — high clip floods midtones and destroys logos
    clip = 0.8 + a * 1.8  # 0.8–2.6 (v0.5 used up to ~4 and crushed detail)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    return clahe.apply(gray)


def unsharp(gray: np.ndarray, amount: float) -> np.ndarray:
    a = float(np.clip(amount, 0.0, 1.0))
    if a < 0.05:
        return gray
    blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=0.8 + a * 0.6)
    return cv2.addWeighted(gray, 1.0 + a * 0.8, blur, -a * 0.8, 0)


def threshold_for_outline(
    gray: np.ndarray,
    *,
    method: str = "otsu",
    blacklevel: float = 0.5,
    invert: bool = False,
) -> np.ndarray:
    """
    Return binary uint8 image: 0 = ink (black), 255 = background (white).
    method: otsu | fixed | adaptive
    """
    g = gray
    method = (method or "otsu").lower()
    if method == "adaptive":
        # Adaptive for uneven lighting only — block size moderate
        bin_inv = cv2.adaptiveThreshold(
            g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 8
        )
        # bin_inv: ink=255
        ink_white = bin_inv
    elif method == "fixed":
        thr = int(np.clip(blacklevel, 0.02, 0.98) * 255)
        _, ink_white = cv2.threshold(g, thr, 255, cv2.THRESH_BINARY_INV)
    else:
        # Otsu — best default for high-contrast logos/signs
        _, ink_white = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    if invert:
        ink_white = cv2.bitwise_not(ink_white)

    # Convert to black-ink-on-white (0 ink, 255 bg)
    return cv2.bitwise_not(ink_white)


def light_morphology(binary_bw: np.ndarray, denoise: float) -> np.ndarray:
    """
    binary_bw: 0=ink, 255=bg.
    Only remove tiny speckles; do not close large gaps (destroys letter holes).
    """
    s = float(np.clip(denoise, 0.0, 1.0))
    if s < 0.15:
        return binary_bw
    # work in ink=255 space
    ink = cv2.bitwise_not(binary_bw)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    if s >= 0.15:
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, k, iterations=1)
    if s >= 0.65:
        # very light close only
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, k, iterations=1)
    return cv2.bitwise_not(ink)


def preprocess_binary_for_potrace(
    img: Image.Image,
    *,
    denoise: float = 0.25,
    contrast: float = 0.35,
    edge_strength: float = 0.35,
    threshold_method: str = "otsu",
    blacklevel: float = 0.5,
    invert: bool = False,
) -> tuple[Image.Image, np.ndarray]:
    """
    Returns (preview RGB black-on-white, gray uint8 for Bitmap).
    Gray is L-mode style: dark = ink.
    """
    gray = to_gray_u8(img)
    gray = denoise_gray(gray, denoise)
    gray = enhance_contrast(gray, contrast)
    gray = unsharp(gray, edge_strength * 0.5)

    binary = threshold_for_outline(
        gray,
        method=threshold_method,
        blacklevel=blacklevel,
        invert=invert,
    )
    binary = light_morphology(binary, denoise)

    # Ensure ink is minority for typical logos (if not, auto-invert)
    ink_frac = float(np.mean(binary < 128))
    if ink_frac > 0.55 and not invert:
        binary = cv2.bitwise_not(binary)
        ink_frac = 1.0 - ink_frac

    preview = Image.fromarray(cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB), "RGB")
    return preview, binary


def preprocess_color_for_vtracer(
    img: Image.Image,
    *,
    denoise: float = 0.3,
    contrast: float = 0.45,
    edge_strength: float = 0.4,
) -> Image.Image:
    """Colour path — mild cleanup only; preserve chroma."""
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
