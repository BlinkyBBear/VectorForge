"""
Edge-aware preprocessing for v0.5 vector quality.

Runs *before* vtracer. All ops are iterative/OpenCV/numpy — no recursion.
"""

from __future__ import annotations

from typing import Any, Literal

import cv2
import numpy as np
from PIL import Image

PreprocessMode = Literal[
    "laser_bw",
    "logo",
    "illustration",
    "photo",
    "photoreal",
    "bw_compound",
    "color",
    "none",
]


def preprocess_for_vectorize(
    img: Image.Image,
    *,
    mode: str = "logo",
    invert: bool = False,
    edge_strength: float = 0.55,
    denoise: float = 0.35,
    contrast: float = 0.55,
    threshold_bias: float = 0.5,
    compound_levels: int = 6,
) -> Image.Image:
    """
    Return an RGB (or gray-as-RGB) image ready for vtracer.

    Parameters 0–1 control intensity of each stage.
    """
    rgba = img.convert("RGBA")
    # Flatten transparency onto pure white (laser/CAD friendly background)
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(bg, rgba)
    bgr = cv2.cvtColor(np.array(flat.convert("RGB")), cv2.COLOR_RGB2BGR)

    mode = (mode or "logo").lower()
    if mode in ("laser", "laser_bw", "laser_pro", "binary"):
        out = _prep_laser_bw(
            bgr,
            invert=invert,
            edge_strength=edge_strength,
            denoise=denoise,
            contrast=contrast,
            threshold_bias=threshold_bias,
        )
    elif mode in ("bw_compound", "compound", "engrave"):
        out = _prep_bw_compound(
            bgr,
            levels=compound_levels,
            invert=invert,
            denoise=denoise,
            contrast=contrast,
            edge_strength=edge_strength,
        )
    elif mode in ("photoreal", "photorealistic", "max", "photo_max"):
        out = _prep_photo(
            bgr,
            denoise=max(0.05, denoise * 0.4),
            contrast=contrast,
            edge_strength=edge_strength * 0.7,
            strong_edges=False,
        )
    elif mode in ("photo", "high_detail_photo"):
        out = _prep_photo(
            bgr,
            denoise=denoise * 0.6,
            contrast=contrast,
            edge_strength=edge_strength * 0.85,
            strong_edges=False,
        )
    elif mode in ("illustration", "illustration_colour", "illustration_color"):
        out = _prep_illustration(
            bgr,
            denoise=denoise,
            contrast=contrast,
            edge_strength=edge_strength,
        )
    elif mode in ("none", "raw"):
        out = bgr
    else:
        # logo / line art / default colour logo
        out = _prep_logo(
            bgr,
            invert=invert,
            denoise=denoise,
            contrast=contrast,
            edge_strength=edge_strength,
        )

    rgb = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb, "RGB")


def _to_gray(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def _clahe_gray(gray: np.ndarray, clip: float, grid: int = 8) -> np.ndarray:
    clip = float(np.clip(clip, 0.5, 8.0))
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(grid, grid))
    return clahe.apply(gray)


def _bilateral(bgr: np.ndarray, strength: float) -> np.ndarray:
    s = float(np.clip(strength, 0.0, 1.0))
    if s < 0.05:
        return bgr
    d = int(3 + round(s * 6))  # 3–9
    sigma = 15 + s * 60
    return cv2.bilateralFilter(bgr, d, sigma, sigma)


def _unsharp(bgr: np.ndarray, amount: float) -> np.ndarray:
    a = float(np.clip(amount, 0.0, 1.5))
    if a < 0.05:
        return bgr
    blur = cv2.GaussianBlur(bgr, (0, 0), sigmaX=1.0 + a)
    # weighted: original * (1+a) - blur * a
    return cv2.addWeighted(bgr, 1.0 + a, blur, -a, 0)


def _morph_clean(mask: np.ndarray, open_k: int = 2, close_k: int = 3) -> np.ndarray:
    """Remove speckles and close thin gaps — iterative morphology only."""
    out = mask
    if open_k > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
        out = cv2.morphologyEx(out, cv2.MORPH_OPEN, k, iterations=1)
    if close_k > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, k, iterations=1)
    return out


def _prep_laser_bw(
    bgr: np.ndarray,
    *,
    invert: bool,
    edge_strength: float,
    denoise: float,
    contrast: float,
    threshold_bias: float,
) -> np.ndarray:
    """
    Tight solid black fills for laser cutting.
    Adaptive threshold + edge boost + morphology cleanup.
    """
    gray = _to_gray(bgr)
    # light denoise without blurring edges hard
    if denoise > 0.05:
        k = 3 if denoise < 0.5 else 5
        gray = cv2.medianBlur(gray, k)

    gray = _clahe_gray(gray, clip=1.0 + contrast * 3.0, grid=8)

    # Edge-aware boost: Canny edges reinforce dark structure
    if edge_strength > 0.05:
        lo = int(40 + (1 - edge_strength) * 40)
        hi = int(100 + (1 - edge_strength) * 80)
        edges = cv2.Canny(gray, lo, hi)
        # dilate thin edges slightly so they survive threshold
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        edges = cv2.dilate(edges, k, iterations=1)
        # darken edge pixels
        gray = gray.copy()
        gray[edges > 0] = np.minimum(gray[edges > 0], 40)

    # Adaptive threshold — bias shifts block size / C
    bias = float(np.clip(threshold_bias, 0.0, 1.0))
    block = int(11 + round(bias * 20)) | 1  # odd 11–31
    C = int(round(2 + (0.5 - bias) * 8))  # ~-2..6
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block,
        C,
    )

    # Also blend Otsu for large solid regions (max of both keeps more black ink)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Prefer black (0) where either method says black for solid logos
    ink = np.minimum(binary, otsu)

    # Morphology: open small noise, close gaps in strokes
    open_k = 2 if denoise > 0.3 else 1
    close_k = 2 + int(round(edge_strength * 2))
    ink = _morph_clean(ink, open_k=open_k, close_k=close_k)

    if invert:
        ink = cv2.bitwise_not(ink)

    return cv2.cvtColor(ink, cv2.COLOR_GRAY2BGR)


def _prep_logo(
    bgr: np.ndarray,
    *,
    invert: bool,
    denoise: float,
    contrast: float,
    edge_strength: float,
) -> np.ndarray:
    """High-contrast colour logos / line art with sharp edges."""
    out = _bilateral(bgr, denoise * 0.7)
    # LAB CLAHE on L only — preserves hue
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = _clahe_gray(l, clip=1.2 + contrast * 2.5, grid=8)
    lab = cv2.merge([l, a, b])
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    out = _unsharp(out, edge_strength * 0.9)
    if invert:
        out = cv2.bitwise_not(out)
    return out


def _prep_illustration(
    bgr: np.ndarray,
    *,
    denoise: float,
    contrast: float,
    edge_strength: float,
) -> np.ndarray:
    out = _bilateral(bgr, denoise)
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = _clahe_gray(l, clip=1.0 + contrast * 2.0, grid=8)
    lab = cv2.merge([l, a, b])
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    out = _unsharp(out, edge_strength * 0.6)
    # light median to stabilize flat colour regions
    if denoise > 0.2:
        out = cv2.medianBlur(out, 3)
    return out


def _prep_photo(
    bgr: np.ndarray,
    *,
    denoise: float,
    contrast: float,
    edge_strength: float,
    strong_edges: bool,
) -> np.ndarray:
    out = _bilateral(bgr, denoise)
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = _clahe_gray(l, clip=1.0 + contrast * 1.8, grid=8)
    if strong_edges and edge_strength > 0.1:
        edges = cv2.Canny(l, 50, 140)
        l = l.copy()
        l[edges > 0] = np.clip(l[edges > 0].astype(np.int16) - int(20 * edge_strength), 0, 255).astype(
            np.uint8
        )
    lab = cv2.merge([l, a, b])
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    out = _unsharp(out, edge_strength * 0.5)
    return out


def _prep_bw_compound(
    bgr: np.ndarray,
    *,
    levels: int,
    invert: bool,
    denoise: float,
    contrast: float,
    edge_strength: float,
) -> np.ndarray:
    """
    Multi-level grayscale bands for engraving (B&W compound vectors).
    Each band becomes a distinct gray that vtracer can separate into layers.
    """
    gray = _to_gray(bgr)
    if denoise > 0.05:
        gray = cv2.medianBlur(gray, 3 if denoise < 0.5 else 5)
    gray = _clahe_gray(gray, clip=1.0 + contrast * 2.5, grid=8)
    if edge_strength > 0.1:
        gray = _unsharp(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), edge_strength * 0.5)
        gray = _to_gray(gray)

    n = int(np.clip(levels, 2, 16))
    # quantize to n levels
    step = 256 // n
    q = (gray // step) * step + step // 2
    q = np.clip(q, 0, 255).astype(np.uint8)
    if invert:
        q = 255 - q
    return cv2.cvtColor(q, cv2.COLOR_GRAY2BGR)


def preprocess_mode_for_preset(preset_id: str) -> str:
    mapping = {
        "laser_pro": "laser_bw",
        "laser": "laser_bw",
        "logo": "logo",
        "illustration": "illustration",
        "photo": "photo",
        "photoreal": "photoreal",
        "bw_compound": "bw_compound",
    }
    return mapping.get(preset_id, "logo")


def describe_preprocess(params: dict[str, Any]) -> str:
    return (
        f"pre={params.get('preprocess_mode', '?')} "
        f"edge={params.get('edge_strength', 0):.2f} "
        f"denoise={params.get('denoise', 0):.2f} "
        f"contrast={params.get('contrast', 0):.2f}"
    )
