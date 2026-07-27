from __future__ import annotations

import unittest
from types import SimpleNamespace

from components.scrollable import (
    PointerScrollableFrame,
    normalized_wheel_pixels,
    pixel_scroll_fraction,
    view_can_scroll,
)


class WheelNormalizationTests(unittest.TestCase):
    def test_standard_windows_notches_have_stable_distance(self):
        self.assertEqual(normalized_wheel_pixels(120), -56)
        self.assertEqual(normalized_wheel_pixels(-240), 112)

    def test_high_resolution_wheel_keeps_fractional_input(self):
        self.assertEqual(normalized_wheel_pixels(30), -14)
        self.assertEqual(normalized_wheel_pixels("bad"), 0)

    def test_scrollable_uses_content_sized_pixel_increments(self):
        self.assertGreaterEqual(PointerScrollableFrame.WHEEL_STEP, 48)
        self.assertLessEqual(PointerScrollableFrame.WHEEL_STEP, 72)

    def test_pixel_delta_uses_canvas_fraction_instead_of_tk_units(self):
        self.assertAlmostEqual(pixel_scroll_fraction((0.25, 0.5), 56, 250), 0.306)
        self.assertAlmostEqual(pixel_scroll_fraction((0.25, 0.5), -56, 250), 0.194)

    def test_pixel_delta_stops_at_both_edges(self):
        self.assertIsNone(pixel_scroll_fraction((0.0, 0.25), -56, 250))
        self.assertIsNone(pixel_scroll_fraction((0.75, 1.0), 56, 250))
        self.assertIsNone(pixel_scroll_fraction((0.0, 1.0), 56, 250))

    def test_nested_scroll_can_handoff_at_an_edge(self):
        self.assertFalse(view_can_scroll((0.0, 0.4), -56))
        self.assertTrue(view_can_scroll((0.0, 0.4), 56))
        self.assertTrue(view_can_scroll((0.6, 1.0), -56))
        self.assertFalse(view_can_scroll((0.6, 1.0), 56))

    def test_wheel_events_are_coalesced_into_one_canvas_update(self):
        calls = []
        scheduled = []
        canvas = SimpleNamespace(
            xview=lambda: (0.0, 1.0),
            yview=lambda: (0.0, 0.25),
            winfo_width=lambda: 500,
            winfo_height=lambda: 250,
            xview_moveto=lambda fraction: calls.append(("x", fraction)),
            yview_moveto=lambda fraction: calls.append(("y", fraction)),
        )
        frame = SimpleNamespace(
            WHEEL_STEP=56,
            WHEEL_FLUSH_MS=8,
            _wheel_remainder=0.0,
            _pending_horizontal_pixels=0,
            _pending_vertical_pixels=0,
            _wheel_job=None,
            _parent_canvas=canvas,
        )
        frame._flush_wheel = lambda: PointerScrollableFrame._flush_wheel(frame)

        def after(delay, callback):
            scheduled.append((delay, callback))
            return "wheel-job"

        frame.after = after
        PointerScrollableFrame._queue_wheel(frame, -120, horizontal=False)
        PointerScrollableFrame._queue_wheel(frame, -120, horizontal=False)

        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 8)
        self.assertEqual(calls, [])
        scheduled[0][1]()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "y")
        self.assertAlmostEqual(calls[0][1], 0.112)
        self.assertIsNone(frame._wheel_job)


if __name__ == "__main__":
    unittest.main()
