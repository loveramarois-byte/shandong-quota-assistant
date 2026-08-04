from __future__ import annotations

import unittest
from unittest import mock

from utils.single_instance import activate_existing_window


class ExistingWindowActivationTests(unittest.TestCase):
    def test_empty_title_is_rejected_without_native_calls(self) -> None:
        self.assertFalse(activate_existing_window(""))

    def test_missing_window_returns_false(self) -> None:
        user32 = mock.Mock()
        user32.FindWindowW.return_value = 0
        with mock.patch("utils.single_instance.os.name", "nt"), mock.patch(
            "utils.single_instance.ctypes.WinDLL", return_value=user32
        ):
            self.assertFalse(activate_existing_window("不存在的窗口"))
        user32.ShowWindow.assert_not_called()

    def test_existing_window_is_restored_and_raised(self) -> None:
        user32 = mock.Mock()
        user32.FindWindowW.return_value = 1234
        with mock.patch("utils.single_instance.os.name", "nt"), mock.patch(
            "utils.single_instance.ctypes.WinDLL", return_value=user32
        ):
            self.assertTrue(activate_existing_window("山东定额助手"))
        user32.ShowWindow.assert_called_once()
        user32.BringWindowToTop.assert_called_once()
        user32.SetForegroundWindow.assert_called_once()


if __name__ == "__main__":
    unittest.main()
