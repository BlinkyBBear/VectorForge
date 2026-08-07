"""VectorForge v0.5 engine tests (no GUI)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from vectorforge.engine.bg_remove import auto_remove_background, wand_at
from vectorforge.engine.memory import (
    HARD_MAX_PROCESS_SIZE,
    clamp_process_size,
    plan_processing_size,
)
from vectorforge.engine.preprocess import preprocess_for_vectorize
from vectorforge.engine.presets import PRESETS, apply_preset, preset_choices
from vectorforge.engine.vectorize import VectorizeParams, vectorize_image


def _logo(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    m = max(8, size // 8)
    d.ellipse((m, m, size - m - 1, size - m - 1), outline=(10, 10, 12, 255), width=max(2, size // 25))
    m2 = max(m + 10, size // 4)
    d.ellipse((m2, m2, size - m2 - 1, size - m2 - 1), fill=(10, 10, 12, 255))
    cx = size // 2
    half = max(3, size // 32)
    d.rectangle((cx - half, m, cx + half, size - m), fill=(10, 10, 12, 255))
    return img


def _photoish(size: int = 320) -> Image.Image:
    img = Image.new("RGB", (size, size), (220, 210, 200))
    d = ImageDraw.Draw(img)
    d.ellipse((60, 40, size - 60, size - 40), fill=(180, 120, 90))
    d.ellipse((100, 100, 140, 130), fill=(40, 30, 20))
    d.ellipse((size - 140, 100, size - 100, 130), fill=(40, 30, 20))
    d.arc((110, 140, size - 110, 220), 10, 170, fill=(80, 40, 30), width=4)
    return img


class MemoryTests(unittest.TestCase):
    def test_hard_max_6000(self) -> None:
        self.assertEqual(HARD_MAX_PROCESS_SIZE, 6000)
        self.assertEqual(clamp_process_size(99999), 6000)

    def test_plan(self) -> None:
        plan = plan_processing_size(8000, 6000, 4000)
        self.assertTrue(plan.downsampled)
        self.assertLessEqual(max(plan.process_width, plan.process_height), 4000)


class PreprocessTests(unittest.TestCase):
    def test_laser_bw_binary_like(self) -> None:
        out = preprocess_for_vectorize(_logo(), mode="laser_bw", edge_strength=0.7)
        self.assertEqual(out.mode, "RGB")
        colors = out.getcolors(maxcolors=50000)
        self.assertIsNotNone(colors)
        assert colors is not None
        self.assertLessEqual(len(colors), 64)

    def test_logo_keeps_colour(self) -> None:
        img = Image.new("RGB", (64, 64), (255, 0, 0))
        out = preprocess_for_vectorize(img, mode="logo")
        self.assertEqual(out.mode, "RGB")


class PresetTests(unittest.TestCase):
    def test_all_presets_exist(self) -> None:
        ids = [k for k, _ in preset_choices()]
        for need in (
            "laser_pro",
            "logo",
            "illustration",
            "photo",
            "photoreal",
            "bw_compound",
        ):
            self.assertIn(need, ids)
            self.assertIn("preprocess_mode", PRESETS[need]["params"])

    def test_apply_preset_keeps_speckle(self) -> None:
        p = apply_preset("photoreal")
        self.assertEqual(p["filter_speckle"], 1)


class BgTests(unittest.TestCase):
    def test_flood(self) -> None:
        out = auto_remove_background(_logo(128), prefer_ai=False, strength=0.6)
        self.assertEqual(out.getpixel((2, 2))[3], 0)

    def test_wand(self) -> None:
        img = Image.new("RGBA", (40, 40), (255, 255, 255, 255))
        out = wand_at(img, 0, 0, erase=True, tolerance=30)
        self.assertEqual(out.getpixel((0, 0))[3], 0)


class VectorizeTests(unittest.TestCase):
    def test_logo_laser(self) -> None:
        result = vectorize_image(
            _logo(200),
            VectorizeParams(preset_id="laser_pro", max_process_size=400),
        )
        self.assertIn("<svg", result.svg.lower())
        self.assertGreater(result.path_count, 0)
        self.assertIn("viewBox", result.svg)

    def test_logo_detail(self) -> None:
        result = vectorize_image(
            _logo(220),
            VectorizeParams(preset_id="logo", max_process_size=500),
        )
        self.assertGreater(result.path_count, 0)

    def test_photo_preset(self) -> None:
        result = vectorize_image(
            _photoish(240),
            VectorizeParams(preset_id="photo", max_process_size=400),
        )
        self.assertIn("<svg", result.svg.lower())
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.svg"
            p.write_text(result.svg, encoding="utf-8")
            self.assertGreater(p.stat().st_size, 80)


if __name__ == "__main__":
    unittest.main()
