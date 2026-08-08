"""
v1.0 preprocessing — mkbitmap-inspired + logo/text morphology.

Pipeline for CNC / logo outlines:
  greyscale → denoise → highpass → contrast → scale UP → threshold
  → mild close (keep letter strokes continuous) → despeckle → Potrace

Yellow logo on black (or black on yellow) forced to pure binary with no grey fringe.
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
    r = max(1.0, float(radius))
    k = int(r * 2) | 1
    blur = cv2.GaussianBlur(gray, (k, k), r)
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
    f = float(factor)
    if f <= 1.01:
        return gray
    h, w = gray.shape[:2]
    nw, nh = int(round(w * f)), int(round(h * f))
    return cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_CUBIC)


def threshold_hard(
    gray: np.ndarray,
    *,
    method: str = "otsu",
    blacklevel: float = 0.5,
    invert: bool = False,
) -> np.ndarray:
    """
    Pure binary: 0 = ink, 255 = background.
    Forces no grey fringe (important for yellow signs / black text).
    """
    method = (method or "otsu").lower()
    if method == "adaptive":
        ink_white = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 6
        )
    elif method == "fixed":
        thr = int(np.clip(blacklevel, 0.02, 0.98) * 255)
        _, ink_white = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY_INV)
    else:
        # Otsu then snap any residual midtones
        _, ink_white = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

    if invert:
        ink_white = cv2.bitwise_not(ink_white)

    # Hard snap — kill grey fringe completely
    _, pure = cv2.threshold(ink_white, 127, 255, cv2.THRESH_BINARY)
    # Convert to 0=ink, 255=bg
    return cv2.bitwise_not(pure)


def logo_text_morphology(binary_bw: np.ndarray, denoise: float) -> np.ndarray:
    """
    binary_bw: 0=ink, 255=bg.

    - Mild CLOSE so letter strokes (E bars, P bowl) stay continuous
    - OPEN to kill speckles outside letters
    - Stronger despeckle inside large black regions via connected-component size filter
    """
    s = float(np.clip(denoise, 0.0, 1.0))
    # work in ink=255 space
    ink = cv2.bitwise_not(binary_bw)

    # Mild close — reconnect broken letter strokes (1–2 px gaps)
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, k_close, iterations=1)

    # Open — remove external speckles
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, k_open, iterations=1)

    # Connected-component despeckle: drop tiny black islands
    # Keep components above a size floor (stronger when denoise high)
    min_area = int(8 + s * 40)  # ~8–48 px
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    cleaned = np.zeros_like(ink)
    for i in range(1, n_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= min_area:
            cleaned[labels == i] = 255
    ink = cleaned

    # One more light close after despeckle so letters stay solid
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, k_close, iterations=1)

    return cv2.bitwise_not(ink)  # back to 0=ink


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
    logo_text: bool = True,
) -> tuple[Image.Image, np.ndarray]:
    """
    Returns (binary preview RGB for UI, binary array 0=ink for Potrace).
    """
    gray = to_gray_u8(img)
    gray = denoise_gray(gray, denoise)

    if edge_strength > 0.08:
        radius = 2.0 + edge_strength * 5.0
        gray = highpass(gray, radius=radius)

    gray = enhance_contrast(gray, contrast)

    h, w = gray.shape[:2]
    side = max(h, w)
    if scale_factor is None:
        target = 1800.0  # a bit more resolution for text
        scale_factor = float(np.clip(target / max(side, 1), 1.0, 4.0))
    gray = scale_greyscale(gray, scale_factor)

    binary = threshold_hard(
        gray,
        method=threshold_method,
        blacklevel=blacklevel,
        invert=invert,
    )

    if logo_text:
        binary = logo_text_morphology(binary, denoise)
    else:
        # light open only
        if denoise > 0.15:
            ink = cv2.bitwise_not(binary)
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
            ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, k, iterations=1)
            binary = cv2.bitwise_not(ink)

    # Auto-invert if ink dominates
    ink_frac = float(np.mean(binary < 128))
    if ink_frac > 0.55 and not invert:
        binary = cv2.bitwise_not(binary)

    # Final hard snap — zero grey
    _, binary = cv2.threshold(binary, 127, 255, cv2.THRESH_BINARY)

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
