"""Lightweight tests for VectorForge engine (no GUI)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from vectorforge.engine.bg_remove import auto_remove_background, wand_at
from vectorforge.engine.memory import clamp_process_size, plan_processing_size, HARD_MAX_PROCESS_SIZE
from vectorforge.engine.vectorize import VectorizeParams, vectorize_image


def _logo(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    for x in range(size // 4, 3 * size // 4):
        for y in range(size // 4, 3 * size // 4):
            # ring-ish
            cx, cy = size // 2, size // 2
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if 40**2 < d2 < 70**2:
                img.putpixel((x, y), (10, 10, 12, 255))
    return img


class MemoryTests(unittest.TestCase):
    def test_clamp(self) -> None:
        self.assertEqual(clamp_process_size(9999), HARD_MAX_PROCESS_SIZE)
        self.assertGreaterEqual(clamp_process_size(100), 256)

    def test_plan_downsample(self) -> None:
        plan = plan_processing_size(6000, 4000, 1400)
        self.assertTrue(plan.downsampled)
        self.assertLessEqual(max(plan.process_width, plan.process_height), 1400)


class BgTests(unittest.TestCase):
    def test_flood_fill_corners(self) -> None:
        img = _logo(128)
        out = auto_remove_background(img, prefer_ai=False, tolerance=40)
        self.assertEqual(out.mode, "RGBA")
        self.assertEqual(out.getpixel((2, 2))[3], 0)

    def test_wand_erase(self) -> None:
        img = Image.new("RGBA", (40, 40), (255, 255, 255, 255))
        out = wand_at(img, 0, 0, erase=True, tolerance=30)
        self.assertEqual(out.getpixel((0, 0))[3], 0)


class VectorizeTests(unittest.TestCase):
    def test_logo_svg(self) -> None:
        img = _logo(200)
        result = vectorize_image(
            img,
            VectorizeParams(preset_id="logo", max_process_size=400),
        )
        self.assertIn("<svg", result.svg.lower())
        self.assertGreater(result.path_count, 0)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.svg"
            p.write_text(result.svg, encoding="utf-8")
            self.assertGreater(p.stat().st_size, 50)


if __name__ == "__main__":
    unittest.main()
