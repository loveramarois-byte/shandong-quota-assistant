from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

from app.main import QuotaApp, initial_window_bounds
from components.sidebar import Sidebar


class _LayoutProbe:
    def __init__(self, size: tuple[int, int]):
        self._closing = False
        self._last_layout_size = size
        self._resize_job = None
        self.cancelled: list[str] = []
        self.scheduled: list[tuple[int, object]] = []

    def after_cancel(self, job: str) -> None:
        self.cancelled.append(job)

    def after(self, delay: int, callback) -> str:
        self.scheduled.append((delay, callback))
        return "layout-job"

    def _apply_responsive_layout(self) -> None:
        pass


class LayoutRefreshTests(unittest.TestCase):
    def test_initial_window_uses_physical_size_at_150_percent_dpi(self):
        width, height, left, top, min_width, min_height = initial_window_bounds(2560, 1440, 1.5)

        self.assertEqual((width, height), (907, 573))
        self.assertEqual((left, top), (600, 290))
        self.assertEqual((min_width, min_height), (653, 453))

    def test_initial_window_stays_inside_a_small_desktop(self):
        width, height, left, top, min_width, min_height = initial_window_bounds(1366, 768, 1.0)

        self.assertLessEqual(width + (left * 2), 1366)
        self.assertLessEqual(height + (top * 2), 768)
        self.assertGreaterEqual(width, min_width)
        self.assertGreaterEqual(height, min_height)

    def test_window_move_with_same_size_does_not_schedule_layout_refresh(self):
        probe = _LayoutProbe((1280, 820))
        event = SimpleNamespace(widget=probe, width=1280, height=820)

        QuotaApp._schedule_layout_update(probe, event)

        self.assertEqual(probe.scheduled, [])
        self.assertEqual(probe.cancelled, [])

    def test_resize_schedules_one_layout_refresh(self):
        probe = _LayoutProbe((1280, 820))
        event = SimpleNamespace(widget=probe, width=1100, height=820)

        QuotaApp._schedule_layout_update(probe, event)

        self.assertEqual(probe._last_layout_size, (1100, 820))
        self.assertEqual(len(probe.scheduled), 1)


class SidebarStateTests(unittest.TestCase):
    def test_rejected_session_switch_does_not_move_highlight(self):
        row = SimpleNamespace(session_id="old", calls=[], set_active=lambda active: row.calls.append(active))
        probe = SimpleNamespace(
            _active_session_id="old",
            _session_rows=[row],
            on_select_session=lambda _session_id: False,
        )

        Sidebar._select(probe, "new")

        self.assertEqual(probe._active_session_id, "old")
        self.assertEqual(row.calls, [])

    def test_busy_sidebar_disables_new_rename_and_delete(self):
        class _Button:
            def __init__(self):
                self.enabled = None

            def set_enabled(self, value):
                self.enabled = value

        probe = SimpleNamespace(new_button=_Button(), rename_button=_Button(), delete_button=_Button())

        Sidebar.set_busy(probe, True)

        self.assertFalse(probe.new_button.enabled)
        self.assertFalse(probe.rename_button.enabled)
        self.assertFalse(probe.delete_button.enabled)


class SessionPersistenceUiTests(unittest.TestCase):
    def test_save_failure_is_reported_without_refreshing_history(self):
        messages = []
        probe = SimpleNamespace(
            session={"id": "session-a"},
            _active_turn_id="turn-a",
            _closing=False,
            _set_status=lambda text, tone="neutral": messages.append(("status", text, tone)),
            _show_toast=lambda text, kind="info": messages.append(("toast", text, kind)),
            _refresh_session_list=lambda: messages.append(("refresh",)),
        )

        with mock.patch("app.main.session_store.save_session", side_effect=OSError(28, "disk full")), mock.patch("app.main.log_exception"):
            saved = QuotaApp._save_current_session(probe)

        self.assertFalse(saved)
        self.assertNotIn(("refresh",), messages)
        self.assertTrue(any(item[0] == "toast" and "保存失败" in item[1] for item in messages))


if __name__ == "__main__":
    unittest.main()
