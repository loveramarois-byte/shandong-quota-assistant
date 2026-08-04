from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QLayout, QSizePolicy

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
            self.assertIn("QComboBox QAbstractItemView", stylesheet)
            self.assertIn("selection-color", stylesheet)
            self.assertIn(get_theme("dark").colors.text, stylesheet)
            self.assertIn("#composer", stylesheet)
            self.assertIn("#filterBar", stylesheet)
        finally:
            window.close()

    def test_chat_surface_is_bounded_and_composer_stays_compact(self) -> None:
        window = QuotaQtApp()
        try:
            self.assertEqual(window.sidebar.width(), window.tokens.sidebar_width)
            self.assertEqual(window.feed.maximumWidth(), window.tokens.content_max_width)
            self.assertTrue(window.scroll.alignment() & Qt.AlignmentFlag.AlignHCenter)
            self.assertEqual(window.feed.layout.sizeConstraint(), QLayout.SizeConstraint.SetMinimumSize)
            self.assertEqual(window.composer.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Maximum)
            self.assertEqual(window.composer.maximumHeight(), 150)
        finally:
            window.close()

    def test_result_rows_are_not_compressed_to_zero_height(self) -> None:
        window = QuotaQtApp()
        try:
            window.resize(1280, 820)
            window.show()
            window.feed.add_user("地下室外墙 4mm 厚 SBS 防水卷材")
            window.feed.add_status("正在查找本地资料", "筛选候选项")
            card = window.feed.add_result(
                {
                    "discipline": "building",
                    "work_items": [{}],
                    "proposals": [
                        {
                            "bill_code": "010903001-000",
                            "bill_title": "墙面卷材防水",
                            "bill_unit": "m²",
                            "quota_lines": [{"code": "9-2-11", "title": "改性沥青卷材热熔法", "unit": "10m²"}],
                        }
                    ],
                }
            )
            self.app.processEvents()
            proposal_label = next(label for label in card.findChildren(QLabel) if label.text().startswith("1. "))
            self.assertGreater(proposal_label.height(), 0)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
