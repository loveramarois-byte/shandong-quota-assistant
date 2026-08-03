from __future__ import annotations

import queue
from types import SimpleNamespace
import unittest
from unittest import mock

from app.main import QuotaApp, ai_connection_state, centered_content_padding, clean_structured_validation, initial_window_bounds
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

        self.assertEqual((width, height), (1360, 860))
        self.assertEqual((left, top), (600, 290))
        self.assertEqual((min_width, min_height), (1120, 680))

    def test_initial_window_stays_inside_a_small_desktop(self):
        width, height, left, top, min_width, min_height = initial_window_bounds(1366, 768, 1.0)

        self.assertLessEqual(width + (left * 2), 1366)
        self.assertLessEqual(height + (top * 2), 768)
        self.assertGreaterEqual(width, min_width)
        self.assertGreaterEqual(height, min_height)

    def test_low_reported_dpi_does_not_shrink_the_workspace(self):
        width, height, _left, _top, min_width, min_height = initial_window_bounds(1536, 864, 0.4)

        self.assertGreaterEqual(width, 2800)
        self.assertGreaterEqual(height, 1700)
        self.assertEqual((min_width, min_height), (2800, 1700))

    def test_conversation_width_is_centered_on_wide_windows(self):
        self.assertEqual(centered_content_padding(1360, 204, 960), 98)
        self.assertEqual(centered_content_padding(1920, 204, 960), 378)
        self.assertEqual(centered_content_padding(980, 204, 960), 18)
        self.assertEqual(centered_content_padding(2040, 204, 960, window_scaling=1.5), 98)

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


class EventPollingTests(unittest.TestCase):
    def test_event_burst_is_split_across_fast_follow_up_ticks(self):
        received: list[dict] = []
        scheduled: list[tuple[int, object]] = []
        events: queue.Queue[tuple[str, object]] = queue.Queue()
        for index in range(4):
            events.put(("library_stats", {"index": index}))
        probe = SimpleNamespace(
            _closing=False,
            MAX_EVENTS_PER_TICK=QuotaApp.MAX_EVENTS_PER_TICK,
            events=events,
            sidebar=SimpleNamespace(set_library_stats=received.append),
            after=lambda delay, callback: scheduled.append((delay, callback)) or "poll-job",
            _poll_events=lambda: None,
            _poll_job=None,
        )

        QuotaApp._poll_events(probe)

        self.assertEqual(received, [{"index": 0}, {"index": 1}, {"index": 2}])
        self.assertEqual(scheduled[-1][0], 16)
        QuotaApp._poll_events(probe)
        self.assertEqual(received[-1], {"index": 3})
        self.assertEqual(scheduled[-1][0], 120)

    def test_resize_probe_without_built_widgets_stays_safe(self):
        probe = _LayoutProbe((1280, 820))
        event = SimpleNamespace(widget=probe, width=1120, height=820)

        QuotaApp._schedule_layout_update(probe, event)

        self.assertEqual(len(probe.scheduled), 1)


class AiPrimaryPresentationTests(unittest.TestCase):
    def test_connected_provider_is_the_primary_header_state(self):
        connected, subtitle, action = ai_connection_state({
            "ai_enabled": True,
            "ai_provider": "deepseek",
            "ai_model": "deepseek-chat",
        })

        self.assertTrue(connected)
        self.assertIn("DeepSeek", subtitle)
        self.assertEqual(action, "AI 已连接")

    def test_offline_fallback_prompts_for_ai_connection(self):
        connected, subtitle, action = ai_connection_state({"ai_enabled": False})

        self.assertFalse(connected)
        self.assertIn("本地资料", subtitle)
        self.assertEqual(action, "连接 AI")

    def test_structured_validation_hides_only_legacy_uncited_noise(self):
        cleaned = clean_structured_validation({
            "warnings": ["AI 部分关键结论未标注本地候选编号，属于模型推断，不可直接作为套项依据。", "保留的业务提醒"],
            "uncited_lines": ["已形成方案"],
        })

        self.assertEqual(cleaned["warnings"], ["保留的业务提醒"])
        self.assertEqual(cleaned["uncited_lines"], [])


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


class SidebarSessionRefreshTests(unittest.TestCase):
    class _Row:
        def __init__(self, session_id: str, *, title: str = "", updated_at: float = 0.0):
            self.session_id = session_id
            self.title = title
            self.updated_at = updated_at
            self.updated: list[tuple[str, float]] = []
            self.active: list[bool] = []
            self.grid_calls: list[dict] = []
            self.destroyed = False

        def update_session(self, *, title, updated_at):
            self.updated.append((title, updated_at))
            self.title = title
            self.updated_at = updated_at

        def matches_session(self, *, title, updated_at):
            return (title, updated_at) == (self.title, self.updated_at)

        def set_active(self, value):
            self.active.append(value)

        def grid(self, **kwargs):
            self.grid_calls.append(kwargs)

        def destroy(self):
            self.destroyed = True

    class _EmptyLabel:
        def __init__(self):
            self.removed = 0
            self.gridded: list[dict] = []

        def grid_remove(self):
            self.removed += 1

        def grid(self, **kwargs):
            self.gridded.append(kwargs)

    def _probe(self, rows):
        actions: list[bool] = []
        return SimpleNamespace(
            _session_rows=rows,
            _active_session_id=None,
            _set_session_actions_visible=actions.append,
            _session_actions=actions,
            empty_label=self._EmptyLabel(),
            session_list=object(),
            tokens=object(),
            _select=lambda _session_id: None,
        )

    def test_same_order_reuses_rows_and_only_updates_active_state(self):
        first = self._Row("first", title="防水工程", updated_at=10.0)
        second = self._Row("second", title="屋面工程", updated_at=20.0)
        probe = self._probe([first, second])
        sessions = [
            {"id": "first", "title": "防水工程", "updated_at": 10.0},
            {"id": "second", "title": "屋面工程", "updated_at": 20.0},
        ]

        Sidebar.refresh_sessions(probe, sessions, "second")

        self.assertEqual(probe._session_rows, [first, second])
        self.assertFalse(first.destroyed)
        self.assertFalse(second.destroyed)
        self.assertEqual(first.grid_calls, [])
        self.assertEqual(second.grid_calls, [])
        self.assertEqual(first.updated, [])
        self.assertEqual(second.updated, [])
        self.assertEqual(first.active, [False])
        self.assertEqual(second.active, [True])
        self.assertEqual(probe._session_actions, [True])

    def test_changed_order_reuses_rows_and_only_creates_or_destroys_differences(self):
        first = self._Row("first", title="防水工程", updated_at=10.0)
        second = self._Row("second", title="屋面工程", updated_at=20.0)
        removed = self._Row("removed")
        probe = self._probe([first, second, removed])
        created: list[SidebarSessionRefreshTests._Row] = []

        def create_row(_master, *, session_id, **_kwargs):
            row = self._Row(session_id)
            created.append(row)
            return row

        sessions = [
            {"id": "second", "title": "屋面工程（更新）", "updated_at": 30.0},
            {"id": "new", "title": "保温工程", "updated_at": 40.0},
            {"id": "first", "title": "防水工程", "updated_at": 10.0},
        ]
        with mock.patch("components.sidebar.SessionRow", side_effect=create_row):
            Sidebar.refresh_sessions(probe, sessions, "new")

        self.assertEqual(probe._session_rows, [second, created[0], first])
        self.assertFalse(first.destroyed)
        self.assertFalse(second.destroyed)
        self.assertTrue(removed.destroyed)
        self.assertEqual(len(created), 1)
        self.assertEqual(second.updated, [("屋面工程（更新）", 30.0)])
        self.assertEqual(second.grid_calls, [{"row": 0, "column": 0, "sticky": "ew", "pady": (0, 2)}])
        self.assertEqual(first.grid_calls, [{"row": 2, "column": 0, "sticky": "ew", "pady": (0, 2)}])
        self.assertEqual(created[0].grid_calls, [{"row": 1, "column": 0, "sticky": "ew", "pady": (0, 2)}])


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
