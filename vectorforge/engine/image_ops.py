"""Image load / EXIF orientation / downsample helpers."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from .memory import MAX_FILE_BYTES, plan_processing_size, clamp_process_size


def load_image(path: str | Path) -> Image.Image:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Image not found: {p}")
    size = p.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(
            f"Image exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB limit."
        )
    img = Image.open(p)
    img = ImageOps.exif_transpose(img)
    # Normalize to RGBA for consistent pipeline
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    elif img.mode == "RGB":
        img = img.convert("RGBA")
    return img


def downsample_image(
    img: Image.Image,
    max_process_size: int,
) -> tuple[Image.Image, object]:
    """Return (possibly downsampled image, SizePlan). Never upsamples."""
    max_side = clamp_process_size(max_process_size)
    plan = plan_processing_size(img.width, img.height, max_side)
    if not plan.downsampled:
        return img.copy(), plan
    out = img.resize(
        (plan.process_width, plan.process_height),
        Image.Resampling.LANCZOS,
    )
    return out, plan


def image_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def image_to_photoimage_bytes(img: Image.Image, max_display: int = 900) -> bytes:
    """PNG bytes for Qt/Tk preview, optionally display-downsampled."""
    w, h = img.size
    long = max(w, h)
    preview = img
    if long > max_display:
        scale = max_display / long
        preview = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.BILINEAR,
        )
    return image_to_png_bytes(preview)
