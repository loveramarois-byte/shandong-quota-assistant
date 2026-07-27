from __future__ import annotations

import json
import unittest
from pathlib import Path

from components.result import CandidateSection
from themes.tokens import DARK, LIGHT
from utils.svg import _render_svg_cached, svg_image


class DesignSystemTests(unittest.TestCase):
    def test_light_and_dark_tokens_are_complete(self):
        for theme in (LIGHT, DARK):
            self.assertTrue(theme.colors.background)
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


if __name__ == "__main__":
    unittest.main()
