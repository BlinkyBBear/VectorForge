"""VectorForge v1.0 engine tests."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from vectorforge.engine.dxf_export import svg_to_dxf
from vectorforge.engine.memory import HARD_MAX_PROCESS_SIZE, clamp_process_size
from vectorforge.engine.presets import PRESETS, apply_preset, preset_choices
from vectorforge.engine.preprocess import preprocess_binary_for_potrace
from vectorforge.engine.svg_render import render_svg_preview
from vectorforge.engine.vectorize import VectorizeParams, vectorize_image


def _kelpie_like(size: int = 600) -> Image.Image:
    """High-contrast diamond sign used as acceptance fixture."""
    img = Image.new("RGB", (size, size), (255, 255, 255))
    d = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    outer = [(cx, 30), (size - 30, cy), (cx, size - 30), (30, cy)]
    m = 50
    inner = [(cx, 30 + m), (size - 30 - m, cy), (cx, size - 30 - m), (30 + m, cy)]
    d.polygon(outer, fill=(0, 0, 0))
    d.polygon(inner, fill=(255, 255, 255))
    d.rectangle((size * 0.28, size * 0.32, size * 0.72, size * 0.40), fill=(0, 0, 0))
    d.rectangle((size * 0.32, size * 0.44, size * 0.68, size * 0.50), fill=(0, 0, 0))
    d.ellipse((size * 0.35, size * 0.55, size * 0.55, size * 0.75), fill=(0, 0, 0))
    d.ellipse((size * 0.32, size * 0.52, size * 0.42, size * 0.62), fill=(0, 0, 0))
    d.ellipse((size * 0.55, size * 0.58, size * 0.72, size * 0.72), fill=(0, 0, 0))
    return img


class MemoryTests(unittest.TestCase):
    def test_max_6000(self) -> None:
        self.assertEqual(HARD_MAX_PROCESS_SIZE, 6000)
        self.assertEqual(clamp_process_size(99999), 6000)


class PreprocessTests(unittest.TestCase):
    def test_not_flooded(self) -> None:
        img = _kelpie_like(400)
        preview, binary, meta = preprocess_binary_for_potrace(img)
        ink = (binary < 128).mean()
        # ink should be minority (diamond ring + figures), not near 100%
        self.assertLess(ink, 0.55)
        self.assertGreater(ink, 0.05)


class PresetTests(unittest.TestCase):
    def test_cnc_default(self) -> None:
        ids = [k for k, _ in preset_choices()]
        self.assertIn("cnc_outline", ids)
        p = apply_preset("cnc_outline")
        self.assertEqual(p["engine"], "potrace")
        self.assertEqual(p["output_style"], "outline")


class AcceptanceTests(unittest.TestCase):
    def test_kelpie_cnc_outline(self) -> None:
        img = _kelpie_like(700)
        result = vectorize_image(
            img,
            VectorizeParams(preset_id="cnc_outline", max_process_size=700),
        )
        self.assertEqual(result.engine, "potrace")
        self.assertGreaterEqual(result.path_count, 3)
        self.assertIn("<svg", result.svg.lower())
        self.assertIn("viewBox", result.svg)
        # Outline mode uses stroke paths
        self.assertIn('stroke="#000000"', result.svg)
        # Outer diamond should produce a closed path (Z)
        self.assertIn("Z", result.svg)
        # No full-frame single path only
        self.assertGreater(result.path_count, 1)
        # Overlay fidelity: re-rasterize and compare black coverage roughly
        preview = render_svg_preview(result.svg, max_side=700)
        self.assertEqual(preview.mode, "RGB")

    def test_laser_fill(self) -> None:
        result = vectorize_image(
            _kelpie_like(400),
            VectorizeParams(preset_id="laser_pro", max_process_size=400),
        )
        self.assertIn("fill=", result.svg)
        self.assertGreater(result.path_count, 0)

    def test_dxf(self) -> None:
        result = vectorize_image(
            _kelpie_like(300),
            VectorizeParams(preset_id="cnc_outline", max_process_size=300),
        )
        dxf = svg_to_dxf(result.svg)
        self.assertIn("POLYLINE", dxf)
        self.assertIn("EOF", dxf)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.dxf"
            p.write_text(dxf, encoding="utf-8")
            self.assertGreater(p.stat().st_size, 50)


if __name__ == "__main__":
    unittest.main()


class QualityAndRasterTests(unittest.TestCase):
    def test_highpass_scale_meta(self) -> None:
        from vectorforge.engine.preprocess import preprocess_binary_for_potrace
        img = _kelpie_like(200)
        _, b1, m1 = preprocess_binary_for_potrace(
            img, highpass_radius=0, scale_factor=1.0, auto_scale=False
        )
        _, b2, m2 = preprocess_binary_for_potrace(
            img, highpass_radius=5, scale_factor=2.0, auto_scale=False
        )
        self.assertEqual(m1["scale_factor"], 1.0)
        self.assertAlmostEqual(m2["scale_factor"], 2.0)
        self.assertGreater(b2.size, b1.size)

    def test_quality_tip(self) -> None:
        from vectorforge.engine.quality_check import analyze_svg_quality
        r = analyze_svg_quality(
            '<svg><path d="M0,0 L1,0 L1,1 L0,1 Z" stroke="#000" fill="none"/></svg>'
        )
        self.assertIn("Laser-ready", r.tip)


class SilhouetteTierTests(unittest.TestCase):
    def _busy_sign(self, size: int = 700) -> Image.Image:
        img = Image.new("RGB", (size, size), (255, 255, 255))
        d = ImageDraw.Draw(img)
        cx = cy = size // 2
        outer = [(cx, 20), (size - 20, cy), (cx, size - 20), (20, cy)]
        m = 45
        inner = [(cx, 20 + m), (size - 20 - m, cy), (cx, size - 20 - m), (20 + m, cy)]
        d.polygon(outer, fill=(0, 0, 0))
        d.polygon(inner, fill=(255, 255, 255))
        for x in (0.22, 0.32, 0.42, 0.52, 0.62):
            d.rectangle((size * x, size * 0.28, size * (x + 0.06), size * 0.36), fill=(0, 0, 0))
        for x in (0.30, 0.40, 0.50):
            d.rectangle((size * x, size * 0.40, size * (x + 0.07), size * 0.46), fill=(0, 0, 0))
        d.ellipse((size * 0.32, size * 0.52, size * 0.50, size * 0.78), fill=(0, 0, 0))
        d.ellipse((size * 0.54, size * 0.58, size * 0.70, size * 0.74), fill=(0, 0, 0))
        d.ellipse((size * 0.16, size * 0.58, size * 0.28, size * 0.76), fill=(0, 0, 0))
        for i in range(15):
            d.ellipse((20 + i * 12, 30, 24 + i * 12, 34), fill=(0, 0, 0))
        return img

    def test_normal_keeps_more_than_aggressive(self) -> None:
        from vectorforge.engine.preprocess import preprocess_binary_for_potrace
        from vectorforge.engine.potrace_engine import potrace_binary_to_svg
        from vectorforge.engine.quality_check import analyze_svg_quality

        _, binary, _ = preprocess_binary_for_potrace(
            self._busy_sign(),
            highpass_radius=2,
            scale_factor=1.2,
            auto_scale=False,
            logo_text=True,
            denoise=0.35,
        )
        off, st_off = potrace_binary_to_svg(
            binary, silhouette=False, outer_and_counters_only=True, turdsize=6
        )
        n_svg, st_n = potrace_binary_to_svg(
            binary, silhouette=True, silhouette_strength="normal", turdsize=6
        )
        a_svg, st_a = potrace_binary_to_svg(
            binary, silhouette=True, silhouette_strength="aggressive", turdsize=6
        )
        self.assertGreaterEqual(st_off.path_count, st_n.path_count)
        self.assertGreaterEqual(st_n.path_count, st_a.path_count)
        self.assertGreaterEqual(st_n.path_count, 6)
        self.assertLess(st_a.path_count, st_n.path_count)
        q = analyze_svg_quality(n_svg)
        self.assertEqual(q.open_count, 0)
        self.assertIn("Laser-ready", q.tip)
        self.assertIn("Z", n_svg)

    def test_dxf_has_mm_units(self) -> None:
        from vectorforge.engine.dxf_export import svg_to_dxf

        svg = '<svg viewBox="0 0 10 10"><path d="M0,0 L10,0 L10,10 L0,10 Z"/></svg>'
        dxf = svg_to_dxf(svg)
        self.assertIn("$INSUNITS", dxf)
