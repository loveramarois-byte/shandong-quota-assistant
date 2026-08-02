from __future__ import annotations

import unittest

from components import settings_dialog


class SettingsDialogRequestTests(unittest.TestCase):
    def test_stale_model_result_from_previous_provider_is_rejected(self):
        accepts = getattr(settings_dialog, "is_current_connection_result", None)
        self.assertIsNotNone(accepts)
        if accepts is None:
            return
        self.assertFalse(
            accepts(
                action="models",
                request_id=4,
                provider="deepseek",
                current_provider="zhipu",
                model_request_id=4,
                probe_request_id=2,
            )
        )

    def test_only_latest_request_of_the_same_kind_is_accepted(self):
        accepts = getattr(settings_dialog, "is_current_connection_result", None)
        self.assertIsNotNone(accepts)
        if accepts is None:
            return
        self.assertFalse(
            accepts(
                action="probe",
                request_id=2,
                provider="deepseek",
                current_provider="deepseek",
                model_request_id=8,
                probe_request_id=3,
            )
        )
        self.assertTrue(
            accepts(
                action="models_fallback",
                request_id=8,
                provider="ccswitch",
                current_provider="ccswitch",
                model_request_id=8,
                probe_request_id=3,
            )
        )
        self.assertTrue(
            accepts(
                action="connect",
                request_id=3,
                provider="deepseek",
                current_provider="deepseek",
                model_request_id=8,
                probe_request_id=3,
            )
        )

    def test_polling_continues_while_a_later_request_is_still_pending(self):
        should_continue = getattr(settings_dialog, "should_continue_connection_poll", None)
        self.assertIsNotNone(should_continue)
        if should_continue is None:
            return
        self.assertTrue(should_continue(closed=False, pending_requests=1, queue_empty=True))
        self.assertFalse(should_continue(closed=True, pending_requests=1, queue_empty=False))


if __name__ == "__main__":
    unittest.main()
