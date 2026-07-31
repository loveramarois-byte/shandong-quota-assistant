from __future__ import annotations

import json
import unittest
from pathlib import Path

from components.button import blend_hex
from components.result import CandidateSection
from themes.tokens import DARK, LIGHT
from utils.svg import _fallback_icon, _render_svg_cached, svg_image
from utils.windows_theme import hex_to_colorref


class DesignSystemTests(unittest.TestCase):
    def test_light_and_dark_tokens_are_complete(self):
        for theme in (LIGHT, DARK):
            self.assertTrue(theme.colors.background)
            self.assertTrue(theme.colors.accent_fill)
            self.assertTrue(theme.colors.on_accent)
            self.assertGreater(theme.control_height, 30)
            self.assertLess(theme.transition_fast, theme.transition_normal)

    def test_lottie_asset_has_timing(self):
        path = Path(__file__).parents[1] / "assets" / "animations" / "analysis-pulse.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreater(data["fr"], 0)
        self.assertGreater(data["op"], data["ip"])

    def test_results_use_progressive_rendering(self):
        self.assertLessEqual(CandidateSection.INITIAL_ROWS, 3)
        self.assertGreaterEqual(CandidateSection.ROW_BATCH, CandidateSection.INITIAL_ROWS)

    def test_svg_rendering_is_cached(self):
        path = Path(__file__).parents[1] / "assets" / "icons" / "copy.svg"
        _render_svg_cached.cache_clear()
        svg_image(path, (16, 16), color="#555A55")
        before = _render_svg_cached.cache_info()
        svg_image(path, (16, 16), color="#555A55")
        after = _render_svg_cached.cache_info()
        self.assertEqual(after.hits, before.hits + 1)

    def test_remove_icon_has_a_native_fallback(self):
        path = Path(__file__).parents[1] / "assets" / "icons" / "x.svg"
        image = _fallback_icon(path, (16, 16), "#555A55")

        self.assertIsNotNone(image.getbbox())
        self.assertGreater(image.getpixel((16, 16))[3], 0)

    def test_interaction_color_blending_is_bounded(self):
        self.assertEqual(blend_hex("#000000", "#FFFFFF", 0.5), "#808080")
        self.assertEqual(blend_hex("#112233", "#FFFFFF", -2), "#112233")
        self.assertEqual(blend_hex("#112233", "#FFFFFF", 4), "#FFFFFF")

    def test_windows_caption_color_uses_colorref_order(self):
        self.assertEqual(hex_to_colorref("#112233"), 0x332211)
        with self.assertRaises(ValueError):
            hex_to_colorref("#123")


if __name__ == "__main__":
    unittest.main()
