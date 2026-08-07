"""
Headless CLI for VectorForge (no GUI required).

Examples:
  python -m vectorforge.cli input.png -o out.svg --preset logo
  python -m vectorforge.cli input.jpg -o out.svg --preset photo --bg
  python -m vectorforge.cli input.png -o out.svg --preset laser --max-side 1200
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vectorforge.engine.bg_remove import auto_remove_background, rembg_status
from vectorforge.engine.image_ops import load_image
from vectorforge.engine.presets import PRESETS, DEFAULT_PRESET_ID
from vectorforge.engine.vectorize import VectorizeParams, save_svg, vectorize_image


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="vectorforge",
        description="Offline raster → laser-ready SVG (vtracer + optional rembg)",
    )
    p.add_argument("input", type=Path, help="Input image path")
    p.add_argument("-o", "--output", type=Path, required=True, help="Output .svg path")
    p.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        default=DEFAULT_PRESET_ID,
        help="Quality preset",
    )
    p.add_argument(
        "--max-side",
        type=int,
        default=None,
        help="Max longest side for processing (default from preset)",
    )
    p.add_argument(
        "--bg",
        action="store_true",
        help="Run offline background removal before vectorize",
    )
    p.add_argument(
        "--no-ai-bg",
        action="store_true",
        help="Use flood-fill BG removal instead of rembg",
    )
    args = p.parse_args(argv)

    print(f"rembg: {rembg_status()}")
    print(f"Loading {args.input}…")
    img = load_image(args.input)
    print(f"Source {img.width}×{img.height}")

    if args.bg:
        print("Background removal…")
        img = auto_remove_background(img, prefer_ai=not args.no_ai_bg)
        print("Subject isolated")

    max_side = args.max_side
    overrides = {}
    if max_side is not None:
        overrides["max_process_size"] = max_side

    def prog(stage: str, frac: float) -> None:
        print(f"  [{frac:5.1%}] {stage}")

    print(f"Vectorizing (preset={args.preset})…")
    result = vectorize_image(
        img,
        VectorizeParams(
            preset_id=args.preset,
            max_process_size=max_side
            or PRESETS[args.preset]["params"]["max_process_size"],
            overrides=overrides,
        ),
        on_progress=prog,
    )
    save_svg(result, args.output)
    print(
        f"Wrote {args.output} | paths={result.path_count} "
        f"nodes~{result.node_estimate} | {result.process_label} | {result.duration_ms}ms"
    )
    if result.warning:
        print(f"Note: {result.warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
