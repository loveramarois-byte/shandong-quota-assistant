from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QLayout, QPushButton, QSizePolicy, QWidget

from app.qt_main import QuotaQtApp, SettingsDialog, _load_qt_fonts
from components.qt_widgets import CheckRow, LoadingSpinner
from themes.tokens import get_theme


class QtThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        _load_qt_fonts()

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
            self.assertEqual(window.composer.maximumHeight(), 146)
        finally:
            window.close()

    def test_first_turn_removes_welcome_before_results_are_inserted(self) -> None:
        window = QuotaQtApp()
        try:
            self.assertIsNotNone(window.feed.findChild(QWidget, "welcomePanel"))
            window._clear_welcome_for_first_turn()
            self.app.processEvents()
            self.assertIsNone(window.feed.findChild(QWidget, "welcomePanel"))
        finally:
            window.close()

    def test_welcome_description_receives_its_full_wrapped_height(self) -> None:
        window = QuotaQtApp()
        try:
            window.resize(1190, 790)
            window.show()
            self.app.processEvents()
            detail = next(
                label
                for label in window.findChildren(QLabel)
                if label.text().startswith("从山东清单与定额资料中定位候选项")
            )
            required_height = detail.fontMetrics().boundingRect(
                QRect(0, 0, detail.width(), 1000),
                int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter),
                detail.text(),
            ).height()
            self.assertGreaterEqual(detail.height(), required_height)
            self.assertGreater(detail.width(), 400)
        finally:
            window.close()

    def test_analysis_status_has_a_compact_accessible_spinner(self) -> None:
        window = QuotaQtApp()
        try:
            card = window.feed.add_status("AI 正在复核", "只基于本地候选方案生成解释。")
            spinner = card.findChild(LoadingSpinner)
            self.assertIsNotNone(spinner)
            self.assertEqual((spinner.width(), spinner.height()), (16, 16))
            self.assertEqual(spinner.accessibleName(), "正在处理")
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
            proposal_label = next(label for label in card.findChildren(QLabel) if label.objectName() == "proposalTitle")
            self.assertGreater(proposal_label.height(), 0)
            rank = next(label for label in card.findChildren(QLabel) if label.objectName() == "rankBadge")
            self.assertEqual((rank.width(), rank.height()), (28, 24))
            self.assertEqual(rank.text(), "01")
        finally:
            window.close()

    def test_long_user_message_gets_a_readable_width_without_exceeding_the_feed(self) -> None:
        window = QuotaQtApp()
        try:
            card = window.feed.add_user("地下室外墙 4mm 厚 SBS 防水卷材，采用热熔法施工")
            label = card.findChild(QLabel)
            self.assertIsNotNone(label)
            self.assertGreater(label.minimumWidth(), 180)
            self.assertLessEqual(card.maximumWidth(), 620)
        finally:
            window.close()

    def test_art_direction_keeps_icon_actions_accessible_and_aligned(self) -> None:
        window = QuotaQtApp()
        try:
            window.show()
            self.app.processEvents()
            self.assertEqual(window.theme_button.width(), window.theme_button.height())
            self.assertTrue(window.theme_button.accessibleName())
            self.assertEqual(window.settings_button.width(), window.settings_button.height())
            self.assertTrue(window.settings_button.accessibleName())
            self.assertEqual(window.composer.maximumWidth(), window.feed.maximumWidth())
            window.composer.edit.setFocus()
            self.app.processEvents()
            self.assertTrue(window.composer.input_shell.property("focused"))
            self.assertEqual(window.brand_mark.width(), window.brand_mark.height())
            self.assertEqual(window.findChild(QLabel, "pageTitle").font().family(), "Source Han Serif SC")
            self.assertEqual(window.composer.status_label.font().family(), "Source Han Sans SC")
            self.assertEqual(window.edition.currentText(), "定额 2025")
            self.assertEqual(window.standard.currentText(), "清单 2024")
            self.assertEqual(window.discipline.currentText(), "专业 建筑")
            self.assertTrue(all(selector.chevron.pixmap() is not None for selector in window.context_selectors))
        finally:
            window.close()

    def test_unresolved_proposal_still_shows_candidate_quotas(self) -> None:
        window = QuotaQtApp()
        try:
            card = window.feed.add_result(
                {
                    "discipline": "building",
                    "work_items": [{}],
                    "proposals": [
                        {
                            "bill_code": "010903001-000",
                            "bill_title": "墙面卷材防水",
                            "bill_unit": "m²",
                            "status": "needs_clarification",
                            "quota_lines": [],
                            "review_candidates": [
                                {"code": "9-2-11", "title": "改性沥青卷材热熔法 一层 立面", "unit": "10m²"}
                            ],
                        }
                    ],
                }
            )
            self.app.processEvents()
            texts = [label.text() for label in card.findChildren(QLabel)]
            self.assertIn("候选定额 · 补充条件后确定", texts)
            self.assertIn("9-2-11", texts)
        finally:
            window.close()

    def test_clarification_choices_are_clickable_and_emit_the_selected_value(self) -> None:
        window = QuotaQtApp()
        try:
            selected: list[tuple[str, str]] = []
            window.feed.clarification_selected.connect(lambda question, answer: selected.append((question, answer)))
            card = window.feed.add_result(
                {
                    "discipline": "building",
                    "work_items": [{}],
                    "proposals": [{"bill_code": "010903001-000", "bill_title": "墙面卷材防水", "quota_lines": []}],
                    "clarification_questions": [
                        {"id": "Q1", "question": "本项采用哪种施工方式？", "options": ["热熔法", "冷粘法", "不确定"]}
                    ],
                }
            )
            self.app.processEvents()
            button = next(value for value in card.findChildren(QPushButton) if "热熔法" in value.text())
            self.assertIn("使用喷灯加热粘贴", button.text())
            button.click()
            self.assertEqual(selected, [("Q1", "热熔法")])
        finally:
            window.close()

    def test_ai_suggestion_hides_codes_until_details_are_expanded(self) -> None:
        window = QuotaQtApp()
        try:
            card = window.feed.add_ai(
                "## 结论\n已形成可确认的清单与定额组合建议。",
                {
                    "work_items": [
                        {
                            "location": "地下室外墙",
                            "material": "SBS 防水卷材",
                            "attributes": [{"key": "thickness", "source": "4mm"}],
                        }
                    ],
                    "proposals": [
                        {
                            "status": "ready_for_review",
                            "bill_code": "010903001-000",
                            "bill_title": "墙面卷材防水",
                            "bill_unit": "m²",
                            "evidence_refs": ["R1"],
                            "quota_lines": [
                                {
                                    "code": "9-2-11",
                                    "title": "改性沥青卷材热熔法一层 立面",
                                    "unit": "10m²",
                                    "evidence_refs": ["R18"],
                                }
                            ],
                        }
                    ],
                },
            )
            self.app.processEvents()
            details = next(value for value in card.findChildren(QWidget) if value.objectName() == "aiDetails")
            labels = card.findChildren(QLabel)
            code_labels = [value for value in labels if "010903001-000" in value.text() or "9-2-11" in value.text()]
            self.assertFalse(details.isVisible())
            self.assertTrue(code_labels)
            self.assertTrue(all(not value.isVisible() for value in code_labels))
            button = next(value for value in card.findChildren(QPushButton) if value.objectName() == "aiDetailsButton")
            button.click()
            self.app.processEvents()
            self.assertTrue(window._manual_scroll_active)
            self.assertFalse(window._follow_latest)
            self.assertFalse(details.isHidden())
            self.assertEqual(button.text(), "收起专业明细")
            button.click()
            self.assertTrue(details.isHidden())

            visible_primary_text = " ".join(value.text() for value in labels if not details.isAncestorOf(value))
            self.assertNotIn("010903001-000", visible_primary_text)
            self.assertNotIn("9-2-11", visible_primary_text)
        finally:
            window.close()

    def test_new_content_does_not_yank_a_reader_back_to_the_bottom(self) -> None:
        window = QuotaQtApp()
        try:
            window.resize(1080, 680)
            window.show()
            window.feed.clear_feed()
            for index in range(14):
                window.feed.add_user(f"历史施工描述 {index + 1}：用于形成足够长的滚动内容。")
            self.app.processEvents()
            bar = window.scroll.verticalScrollBar()
            bar.setValue(0)
            self.app.processEvents()
            self.assertFalse(window._follow_latest)
            window.feed.add_ai("补充复核意见：当前阅读位置应保持不变。")
            self.app.processEvents()
            self.assertEqual(bar.value(), 0)
            self.assertLess(bar.value(), bar.maximum())
        finally:
            window.close()

    def test_new_content_settles_at_latest_after_layout_updates(self) -> None:
        window = QuotaQtApp()
        try:
            window.resize(1080, 680)
            window.show()
            window.feed.clear_feed()
            window._follow_latest = True
            for index in range(8):
                window.feed.add_user(f"施工描述 {index + 1}：生成足够长的内容以触发布局和滚动范围更新。")
            self.app.processEvents()
            bar = window.scroll.verticalScrollBar()
            self.assertEqual(bar.value(), bar.maximum())
        finally:
            window.close()

    def test_growing_scroll_range_follows_latest_only_when_enabled(self) -> None:
        window = QuotaQtApp()
        try:
            bar = window.scroll.verticalScrollBar()
            window._follow_latest = True
            window._follow_growing_content(0, 37)
            self.assertEqual(bar.value(), bar.maximum())
            window._follow_latest = False
            original = bar.value()
            window._follow_growing_content(0, 99)
            self.assertEqual(bar.value(), original)
        finally:
            window.close()

    def test_manual_scroll_pause_blocks_range_growth_from_repositioning_reader(self) -> None:
        window = QuotaQtApp()
        try:
            bar = window.scroll.verticalScrollBar()
            window._follow_latest = True
            window._pause_follow_latest()
            self.assertFalse(window._follow_latest)
            self.assertTrue(window._manual_scroll_active)
            original = bar.value()
            window._follow_growing_content(0, 200)
            self.assertEqual(bar.value(), original)
        finally:
            window.close()

    def test_settings_use_application_owned_consent_rows(self) -> None:
        window = QuotaQtApp()
        dialog = SettingsDialog(window.settings, window)
        try:
            checks = dialog.findChildren(CheckRow)
            self.assertEqual(len(checks), 3)
            self.assertTrue(all(check.accessibleName() for check in checks))
            initial = dialog.description_consent.isChecked()
            dialog.description_consent.click()
            self.assertNotEqual(dialog.description_consent.isChecked(), initial)
            dialog._set_connection_message("连接失败", "error")
            self.assertEqual(dialog.connection_status.property("tone"), "error")
            dialog.show()
            self.app.processEvents()
            self.assertEqual(dialog.windowOpacity(), 1.0)
        finally:
            dialog.close()
            window.close()


if __name__ == "__main__":
    unittest.main()
