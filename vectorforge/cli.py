"""
Headless CLI for VectorForge v0.5.

Examples:
  python -m vectorforge.cli input.png -o out.svg --preset logo
  python -m vectorforge.cli input.jpg -o out.svg --preset photoreal --bg
  python -m vectorforge.cli cut.png -o cut.svg --preset laser_pro --max-side 3200
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vectorforge import __version__
from vectorforge.engine.bg_remove import auto_remove_background, rembg_status
from vectorforge.engine.image_ops import load_image
from vectorforge.engine.presets import PRESETS, DEFAULT_PRESET_ID, preset_choices
from vectorforge.engine.vectorize import VectorizeParams, save_svg, vectorize_image


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="vectorforge",
        description=f"VectorForge v{__version__} — offline raster → laser-ready SVG",
    )
    p.add_argument("input", type=Path, help="Input image path")
    p.add_argument("-o", "--output", type=Path, required=True, help="Output .svg path")
    p.add_argument(
        "--preset",
        choices=[k for k, _ in preset_choices()] + ["laser", "max"],
        default=DEFAULT_PRESET_ID,
        help="Quality preset",
    )
    p.add_argument("--max-side", type=int, default=None)
    p.add_argument("--bg", action="store_true", help="Background removal first")
    p.add_argument("--bg-strength", type=float, default=0.55)
    p.add_argument("--no-ai-bg", action="store_true")
    p.add_argument("--bw", action="store_true", help="Force pure B&W laser mode")
    p.add_argument("--color", action="store_true", help="Force colour compound mode")
    p.add_argument("--edge", type=float, default=None, help="Edge strength 0-1")
    p.add_argument("--denoise", type=float, default=None)
    p.add_argument("--contrast", type=float, default=None)
    p.add_argument("--filter-speckle", type=int, default=None)
    p.add_argument("--invert", action="store_true")
    args = p.parse_args(argv)

    print(f"VectorForge v{__version__}")
    print(f"rembg: {rembg_status()}")
    print(f"Loading {args.input}…")
    img = load_image(args.input)
    print(f"Source {img.width}×{img.height}")

    if args.bg:
        print(f"Background removal (strength={args.bg_strength})…")
        img = auto_remove_background(
            img, prefer_ai=not args.no_ai_bg, strength=args.bg_strength
        )

    overrides: dict = {}
    if args.max_side is not None:
        overrides["max_process_size"] = args.max_side
    if args.bw:
        overrides["force_binary"] = True
        overrides["colormode"] = "binary"
        overrides["preprocess_mode"] = "laser_bw"
    if args.color:
        overrides["force_color"] = True
        overrides["colormode"] = "color"
    if args.edge is not None:
        overrides["edge_strength"] = args.edge
    if args.denoise is not None:
        overrides["denoise"] = args.denoise
    if args.contrast is not None:
        overrides["contrast"] = args.contrast
    if args.filter_speckle is not None:
        overrides["filter_speckle"] = args.filter_speckle
    if args.invert:
        overrides["invert"] = True

    def prog(stage: str, frac: float) -> None:
        print(f"  [{frac:5.1%}] {stage}")

    max_side = args.max_side or PRESETS[args.preset]["params"]["max_process_size"]
    print(f"Vectorizing (preset={args.preset})…")
    result = vectorize_image(
        img,
        VectorizeParams(
            preset_id=args.preset,
            max_process_size=max_side,
            overrides=overrides,
        ),
        on_progress=prog,
    )
    save_svg(result, args.output)
    print(
        f"Wrote {args.output} | paths={result.path_count} "
        f"nodes~{result.node_estimate} | {result.process_label} | {result.duration_ms}ms"
    )
    print(f"  {result.preprocess_note}")
    if result.warning:
        print(f"Note: {result.warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
