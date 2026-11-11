"""Automated offline verification tests for KaleidoscopeV2."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from kaleidoscope.config import load_settings
from kaleidoscope.crop_engine import PRESET_VIEW_NAMES, slice_turnaround
from kaleidoscope.prompts import build_prompt


def _draw_synthetic_sheet(path: Path, width: int = 1920, height: int = 1080, add_shadows: bool = True, disjoint_heads: bool = False) -> None:
    """Render a synthetic 5-view 16:9 turnaround sheet for offline slicer testing."""
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    col_w = width // 5
    colors = [(40, 40, 180), (180, 50, 40), (30, 150, 40), (160, 40, 160), (40, 150, 180)]

    for i, col in enumerate(colors):
        cx = i * col_w + col_w // 2
        hy = int(height * 0.28)
        cv2.circle(img, (cx, hy), 45, col, -1)
        gap = 30 if disjoint_heads else 8
        ty1 = hy + 45 + gap
        ty2 = ty1 + 220
        cv2.rectangle(img, (cx - 45, ty1), (cx + 45, ty2), col, -1)
        cv2.rectangle(img, (cx - 45, ty2), (cx - 13, ty2 + 210), col, -1)
        cv2.rectangle(img, (cx + 13, ty2), (cx + 45, ty2 + 210), col, -1)
        if add_shadows:
            # Neutral pale gray floor shadow under feet (BGR ~228, should be filtered out cleanly)
            cv2.ellipse(img, (cx, ty2 + 220), (65, 14), 0, 0, 360, (228, 228, 228), -1)

    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


class CropEngineAndConfigTests(unittest.TestCase):
    def test_auto_and_contour_slice_five_square_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "sheet.png"
            _draw_synthetic_sheet(sheet, add_shadows=True, disjoint_heads=True)

            out_dir = root / "views"
            views = slice_turnaround(sheet, out_dir, prefix="hero", preset="character", target_size=512, mode="auto")
            self.assertEqual(len(views), 5)

            for idx, v_path in enumerate(views):
                self.assertTrue(v_path.exists())
                self.assertEqual(v_path.name, f"{PRESET_VIEW_NAMES['character'][idx]}_hero.png")
                im = np.asarray(Image.open(v_path).convert("RGB"))
                self.assertEqual(im.shape, (512, 512, 3))
                # Corners must stay pure white (#FFFFFF)
                self.assertTrue(np.all(im[0, 0] == 255))
                non_white = int(np.sum(np.any(np.abs(im.astype(np.int32) - 255) > 20, axis=2)))
                self.assertGreater(non_white, 500)

    def test_projection_fallback_slice_weapon_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = root / "weapon_sheet.png"
            _draw_synthetic_sheet(sheet, add_shadows=False)
            out_dir = root / "weapon_views"

            views = slice_turnaround(sheet, out_dir, preset="weapon", target_size=256, mode="projection")
            self.assertEqual(len(views), 5)
            expected = [f"{name}.png" for name in PRESET_VIEW_NAMES["weapon"]]
            self.assertEqual([p.name for p in views], expected)

    def test_prompt_builder_respects_custom_and_ref(self) -> None:
        wrapped = build_prompt("cyberpunk hammer", preset="weapon", has_reference_image=True)
        self.assertIn("cyberpunk hammer", wrapped)
        self.assertIn("#FFFFFF", wrapped)
        self.assertIn("attached reference image", wrapped)

        custom = "My exact 5-view turnaround sheet prompt on white background"
        self.assertEqual(build_prompt(custom, preset="character"), custom)

    def test_load_settings_defaults_without_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup = os.environ.copy()
            try:
                for key in list(os.environ.keys()):
                    if key.startswith("KALEIDOSCOPE_") or key == "FLOW_PROJECT_URL":
                        os.environ.pop(key, None)
                cfg = load_settings(base_dir=tmp)
                self.assertEqual(cfg.flow_url, "https://flow.google.com/")
                self.assertEqual(cfg.profile_dir, Path(tmp).resolve() / "browser_profile")
                self.assertTrue(cfg.headless)
            finally:
                os.environ.clear()
                os.environ.update(backup)


if __name__ == "__main__":
    unittest.main()
