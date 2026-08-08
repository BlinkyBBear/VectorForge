"""CLI for VectorForge v1.0."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vectorforge import __version__
from vectorforge.engine.bg_remove import auto_remove_background, rembg_status
from vectorforge.engine.dxf_export import save_dxf
from vectorforge.engine.image_ops import load_image
from vectorforge.engine.presets import PRESETS, DEFAULT_PRESET_ID, preset_choices
from vectorforge.engine.vectorize import VectorizeParams, save_svg, vectorize_image


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="vectorforge",
        description=f"VectorForge v{__version__} — offline raster → CNC/laser SVG+DXF",
    )
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True, help="Output .svg path")
    p.add_argument("--dxf", type=Path, default=None, help="Optional DXF path")
    p.add_argument(
        "--preset",
        choices=[k for k, _ in preset_choices()]
        + ["laser", "max", "illustration", "bw_compound"],
        default=DEFAULT_PRESET_ID,
    )
    p.add_argument("--max-side", type=int, default=None)
    p.add_argument("--bg", action="store_true")
    p.add_argument("--bg-strength", type=float, default=0.55)
    p.add_argument("--no-ai-bg", action="store_true")
    p.add_argument(
        "--mode",
        choices=["outline", "bw", "color"],
        default=None,
        help="Force colour mode",
    )
    p.add_argument("--invert", action="store_true")
    p.add_argument("--edge", type=float, default=None)
    p.add_argument("--denoise", type=float, default=None)
    p.add_argument("--contrast", type=float, default=None)
    p.add_argument("--turdsize", type=int, default=None)
    p.add_argument("--opttolerance", type=float, default=None)
    args = p.parse_args(argv)

    print(f"VectorForge v{__version__}")
    print(f"rembg: {rembg_status()}")
    img = load_image(args.input)
    print(f"Source {img.width}×{img.height}")

    if args.bg:
        img = auto_remove_background(
            img, prefer_ai=not args.no_ai_bg, strength=args.bg_strength
        )
        print("BG removed")

    overrides: dict = {}
    if args.max_side is not None:
        overrides["max_process_size"] = args.max_side
    if args.mode:
        overrides["color_mode"] = args.mode
    if args.invert:
        overrides["invert"] = True
    if args.edge is not None:
        overrides["edge_strength"] = args.edge
    if args.denoise is not None:
        overrides["denoise"] = args.denoise
    if args.contrast is not None:
        overrides["contrast"] = args.contrast
    if args.turdsize is not None:
        overrides["turdsize"] = args.turdsize
    if args.opttolerance is not None:
        overrides["opttolerance"] = args.opttolerance

    def prog(stage: str, frac: float) -> None:
        print(f"  [{frac:5.1%}] {stage}")

    max_side = args.max_side or PRESETS[args.preset]["params"]["max_process_size"]
    result = vectorize_image(
        img,
        VectorizeParams(
            preset_id=args.preset, max_process_size=max_side, overrides=overrides
        ),
        on_progress=prog,
    )
    save_svg(result, args.output)
    print(
        f"SVG {args.output} | engine={result.engine} paths={result.path_count} "
        f"nodes~{result.node_estimate} | {result.process_label} | {result.duration_ms}ms"
    )
    print(f"  {result.preprocess_note}")
    if args.dxf:
        save_dxf(result.svg, args.dxf)
        print(f"DXF {args.dxf}")
    if result.warning:
        print(f"Note: {result.warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
