from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from components.button import blend_hex
from components.result import CandidateSection
from themes.tokens import DARK, LIGHT, Typography
from utils.formatting import candidate_row_tsv
from utils.svg import _fallback_icon, _render_svg_cached, svg_image
from utils.motion import motion_enabled
from utils.windows_theme import hex_to_colorref


class DesignSystemTests(unittest.TestCase):
    @staticmethod
    def _contrast_ratio(foreground: str, background: str) -> float:
        def luminance(color: str) -> float:
            channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            channels = [
                value / 12.92 if value <= 0.04045 else math.pow((value + 0.055) / 1.055, 2.4)
                for value in channels
            ]
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (lighter + 0.05) / (darker + 0.05)

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

    def test_motion_preference_probe_has_a_stable_boolean_contract(self):
        self.assertIsInstance(motion_enabled(), bool)

    def test_normal_text_tokens_meet_wcag_aa(self):
        self.assertGreaterEqual(self._contrast_ratio(LIGHT.colors.text_muted, LIGHT.colors.background), 4.5)
        self.assertGreaterEqual(self._contrast_ratio(DARK.colors.on_accent, DARK.colors.accent_fill), 4.5)

    def test_typography_tokens_never_drop_below_eleven_pixels(self):
        self.assertGreaterEqual(min(vars(Typography()).values()), 11)

    def test_candidate_copy_has_six_spreadsheet_columns(self):
        value = candidate_row_tsv(
            {
                "code": "010101001001",
                "title": "平整场地",
                "unit": "m2",
                "edition": "2025",
                "discipline": "building",
            }
        )
        self.assertEqual(value, "010101001001\t平整场地\tm²\t2025\t建筑\t")
        self.assertEqual(len(value.split("\t")), 6)

    def test_legacy_header_uses_one_grid_layout_manager(self):
        source = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
        header_source = source.split("    def _build_header", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("self.controls.grid(", header_source)
        self.assertNotIn("self.controls.place(", header_source)


if __name__ == "__main__":
    unittest.main()
