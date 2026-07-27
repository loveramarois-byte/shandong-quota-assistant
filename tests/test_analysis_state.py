from __future__ import annotations

import threading
import unittest

from controllers.analysis import AnalysisTaskRegistry, TaskPhase, TaskToken


class AnalysisTaskRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = AnalysisTaskRegistry()
        self.cancel = threading.Event()
        self.task = self.registry.start(
            session_id="session-a",
            turn_id="turn-a",
            request_id=7,
            revision=3,
            cancel_event=self.cancel,
        )

    def test_event_identity_requires_all_four_fields(self):
        self.assertIsNotNone(self.registry.accepts(TaskToken("session-a", "turn-a", 7, 3)))
        self.assertIsNone(self.registry.accepts(TaskToken("session-b", "turn-a", 7, 3)))
        self.assertIsNone(self.registry.accepts(TaskToken("session-a", "turn-b", 7, 3)))
        self.assertIsNone(self.registry.accepts(TaskToken("session-a", "turn-a", 7, 4)))

    def test_local_ready_and_ai_running_release_send_and_switch(self):
        self.registry.transition(7, TaskPhase.AI_RUNNING)
        capabilities = self.registry.capabilities("session-a")
        self.assertTrue(capabilities.send)
        self.assertTrue(capabilities.switch)
        self.assertTrue(capabilities.cancel)

    def test_searching_blocks_mutating_navigation(self):
        capabilities = self.registry.capabilities("session-a")
        self.assertFalse(capabilities.send)
        self.assertFalse(capabilities.switch)
        self.assertFalse(capabilities.delete)
        self.assertTrue(capabilities.cancel)

    def test_cancel_rejects_late_event_immediately(self):
        token = self.task.token
        cancelled = self.registry.cancel(7)
        self.assertIsNotNone(cancelled)
        self.assertTrue(self.cancel.is_set())
        self.assertEqual(cancelled.phase, TaskPhase.CANCELLING)
        self.assertIsNone(self.registry.accepts(token))
        self.assertTrue(self.registry.capabilities("session-a").send)

    def test_close_session_isolates_every_inflight_turn(self):
        other_cancel = threading.Event()
        self.registry.start(
            session_id="session-a",
            turn_id="turn-b",
            request_id=8,
            revision=4,
            cancel_event=other_cancel,
            phase=TaskPhase.AI_RUNNING,
        )
        closed = self.registry.close_session("session-a")
        self.assertEqual({task.token.request_id for task in closed}, {7, 8})
        self.assertTrue(self.cancel.is_set())
        self.assertTrue(other_cancel.is_set())
        self.assertIsNone(self.registry.get(7))
        self.assertIsNone(self.registry.get(8))


if __name__ == "__main__":
    unittest.main()
