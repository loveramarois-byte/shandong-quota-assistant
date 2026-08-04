from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.qt_main import QuotaQtApp
from themes.tokens import get_theme


class QtThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_dark_theme_covers_scroll_viewport_and_scrollbar_pages(self) -> None:
        window = QuotaQtApp()
        try:
            window.theme_name = "dark"
            window.tokens = get_theme("dark")
            window._apply_theme()
            stylesheet = window.styleSheet()
            self.assertIn("#feedScroll, #feedViewport, #messageFeed", stylesheet)
            self.assertIn(get_theme("dark").colors.background, stylesheet)
            self.assertIn("QScrollBar::add-page:vertical", stylesheet)
            self.assertIn("QScrollBar::sub-page:vertical", stylesheet)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
