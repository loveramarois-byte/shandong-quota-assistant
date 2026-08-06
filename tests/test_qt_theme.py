from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QLayout, QPushButton, QSizePolicy, QWidget

from app.qt_main import QuotaQtApp, SettingsDialog, _load_qt_fonts
from components.qt_widgets import CheckRow, LoadingSpinner, _copy_row_button, bill_result_mime, candidate_row_mime
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
                            "bill_feature_description": "施工部位：地下室外墙\n卷材品种、规格、厚度：SBS防水卷材；4mm",
                            "bill_calculation_rule": "按设计图示尺寸以面积计算",
                            "bill_work_content": "基层处理；铺贴卷材",
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
            self.assertIsNotNone(card.findChild(QWidget, "billSheet"))
            feature = card.findChild(QLabel, "billFeatureDescription")
            self.assertIsNotNone(feature)
            self.assertIn("SBS防水卷材；4mm", feature.text())
        finally:
            window.close()

    def test_candidate_copy_mime_preserves_codes_as_excel_text(self) -> None:
        mime = candidate_row_mime(
            {
                "code": "010101001001",
                "title": "平整场地",
                "unit": "m2",
                "edition": "2025",
                "discipline": "building",
            }
        )
        self.assertEqual(mime.text(), "010101001001\t平整场地\tm²\t2025\t建筑\t")
        self.assertIn("mso-number-format", mime.html())
        self.assertIn("010101001001", mime.html())

    def test_formal_bill_copy_includes_feature_rule_and_work_content(self) -> None:
        mime = bill_result_mime(
            {
                "code": "010903001-000",
                "name": "墙面卷材防水",
                "feature_description": "卷材品种：SBS卷材；厚度：4mm",
                "unit": "m²",
                "calculation_rule": "按设计图示面积计算",
                "work_content": "基层处理；铺贴卷材",
            }
        )

        self.assertEqual(len(mime.text().split("\t")), 6)
        self.assertIn("卷材品种：SBS卷材；厚度：4mm", mime.text())
        self.assertIn("按设计图示面积计算", mime.text())
        self.assertIn("铺贴卷材", mime.text())

    def test_candidate_copy_button_writes_clipboard_and_shows_feedback(self) -> None:
        button = _copy_row_button(
            {
                "code": "010101001001",
                "title": "平整场地",
                "unit": "m2",
                "edition": "2025",
                "discipline": "building",
                "pdf_page": 42,
            }
        )
        try:
            button.click()
            self.app.processEvents()
            self.assertEqual(
                QApplication.clipboard().text(),
                "010101001001\t平整场地\tm²\t2025\t建筑\t42",
            )
            self.assertEqual(button.text(), "已复制")
            self.assertFalse(button.isEnabled())
            timer = button.findChild(QTimer)
            self.assertIsNotNone(timer)
            self.assertGreater(timer.remainingTime(), 1000)
            self.assertLessEqual(timer.remainingTime(), 1500)
        finally:
            button.deleteLater()

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
            self.assertIsNone(window.findChild(QLabel, "pageSubtitle"))
            self.assertIsNone(window.composer.findChild(QLabel, "composerMode"))
        finally:
            window.close()

    def test_compact_shell_has_keyboard_focus_and_semantic_connection_state(self) -> None:
        window = QuotaQtApp()
        try:
            window.show()
            self.app.processEvents()
            window.composer.focus_input()
            self.app.processEvents()
            self.assertTrue(window.composer.edit.hasFocus())
            window.settings.update({"ai_enabled": False, "ai_model": ""})
            window.ai_status.setText(window._ai_status_text())
            self.assertFalse(window.ai_status.property("connected"))
            window.settings.update({"ai_enabled": True, "ai_model": "deepseek-chat", "ai_provider": "deepseek"})
            window.ai_status.setText(window._ai_status_text())
            self.assertTrue(window.ai_status.property("connected"))
        finally:
            window._session = None
            window.close()

    def test_empty_history_uses_a_quiet_noninteractive_state(self) -> None:
        window = QuotaQtApp()
        try:
            window.sessions.set_sessions([])
            self.assertEqual(window.sessions.count(), 1)
            item = window.sessions.item(0)
            self.assertEqual(item.text(), "暂无历史分析")
            self.assertFalse(bool(item.flags() & Qt.ItemFlag.ItemIsEnabled))
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
            self.assertIn("候选定额，补充条件后确定", texts)
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

    def test_ai_conclusion_keeps_clarification_choices_actionable(self) -> None:
        window = QuotaQtApp()
        try:
            selected: list[tuple[str, str]] = []
            window.feed.clarification_selected.connect(lambda question, answer: selected.append((question, answer)))
            card = window.feed.add_ai(
                "## 结论\n还需要确认施工方式。",
                {
                    "work_items": [{"location": "地下室外墙", "material": "SBS 防水卷材"}],
                    "clarification_questions": [
                        {"id": "Q1", "field": "method", "question": "现场采用哪种施工方式？", "options": ["热熔法", "冷粘法"]}
                    ],
                    "proposals": [{"status": "needs_clarification", "bill_title": "墙面卷材防水"}],
                },
            )
            button = next(value for value in card.findChildren(QPushButton) if "热熔法" in value.text())
            button.click()
            self.assertEqual(selected, [("Q1", "热熔法")])
            self.assertIn("使用喷灯加热粘贴", button.text())
        finally:
            window.close()

    def test_confirmable_ai_result_emits_and_persists_manual_confirmation(self) -> None:
        window = QuotaQtApp()
        proposal = {
            "status": "ready_for_review",
            "bill_record_id": "B1",
            "bill_code": "010903001-000",
            "bill_title": "墙面卷材防水",
            "bill_unit": "m²",
            "hard_conflicts": [],
            "unresolved_question_ids": [],
            "quota_lines": [
                {"record_id": "Q1", "role": "main", "code": "9-2-11", "title": "改性沥青卷材热熔法一层 立面", "unit": "10m²"}
            ],
        }
        snapshot = {"work_items": [{}], "proposals": [proposal], "quotas": []}
        session = {
            "id": "session1",
            "schema_version": 2,
            "title": "防水",
            "created_at": 1.0,
            "updated_at": 1.0,
            "revision": 0,
            "turns": [
                {
                    "turn_id": "T1",
                    "query": "地下室外墙防水",
                    "filters": {},
                    "human_selections": {"primary": {}},
                    "human_edits": [],
                    "retrieval_snapshot": snapshot,
                    "ai_attempts": [],
                }
            ],
        }
        try:
            window._session = session
            with patch("app.qt_main.session_store.save_session"):
                card = window.feed.add_ai("## 结论\n方案已生成。", snapshot, context_id="T1")
                button = next(value for value in card.findChildren(QPushButton) if value.objectName() == "confirmButton")
                self.assertEqual(button.text(), "人工确认")
                button.click()
            self.assertTrue(proposal["confirmed"])
            self.assertEqual(button.text(), "已人工确认")
            stored = session["turns"][0]["human_selections"]["proposals"]
            self.assertTrue(stored[0]["confirmed"])
        finally:
            window._session = None
            window.close()

    def test_ai_suggestion_shows_primary_codes_and_keeps_extended_details_collapsed(self) -> None:
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
                            "bill_feature_description": "施工部位：地下室外墙\n卷材品种、规格、厚度：SBS防水卷材；4mm",
                            "bill_calculation_rule": "按设计图示尺寸以面积计算",
                            "bill_work_content": "基层处理；铺贴卷材；搭接缝处理",
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
            pricing_text = " ".join(
                value.text()
                for value in labels
                if value.objectName() in {"aiPricingType", "aiPricingCode", "aiPricingName", "aiPricingUnit"}
            )
            self.assertFalse(details.isVisible())
            self.assertIn("清单 010903001-000 墙面卷材防水 m²", pricing_text)
            self.assertIn("定额 9-2-11 改性沥青卷材热熔法一层 立面 10m²", pricing_text)
            bill_details = card.findChildren(QLabel, "aiPricingBillDetail")
            self.assertEqual(len(bill_details), 3)
            self.assertIn("项目特征：施工部位：地下室外墙", bill_details[0].text())
            self.assertIn("计算规则：按设计图示尺寸以面积计算", bill_details[1].text())
            self.assertIn("工作内容：基层处理；铺贴卷材；搭接缝处理", bill_details[2].text())
            self.assertIsNone(card.findChild(QWidget, "billSheet"))
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
            self.assertIn("010903001-000", visible_primary_text)
            self.assertIn("9-2-11", visible_primary_text)
        finally:
            window.close()

    def test_completed_session_shows_one_final_surface_instead_of_duplicate_results(self) -> None:
        window = QuotaQtApp()
        snapshot = {
            "work_items": [{"location": "地下室外墙", "material": "SBS防水卷材"}],
            "proposals": [
                {
                    "status": "ready_for_review",
                    "bill_code": "010903001-000",
                    "bill_title": "墙面卷材防水",
                    "bill_unit": "m²",
                    "quota_lines": [{"code": "9-2-11", "title": "改性沥青卷材热熔法一层 立面", "unit": "10m²"}],
                }
            ],
        }
        session = {
            "id": "S1",
            "turns": [
                {
                    "turn_id": "T1",
                    "query": "地下室外墙 4mm 厚 SBS 防水卷材",
                    "retrieval_snapshot": snapshot,
                    "ai_attempts": [{"status": "completed", "response": "## 结论\n采用热熔法施工。"}],
                }
            ],
        }
        try:
            with patch("app.qt_main.session_store.load_session", return_value=session):
                window._select_session("S1")
            self.app.processEvents()
            self.assertEqual(len(window.feed.findChildren(QWidget, "resultCard")), 0)
            self.assertEqual(len(window.feed.findChildren(QWidget, "aiSuggestionCard")), 1)
            self.assertIsNone(window._turn_widgets["T1"]["result"])
        finally:
            window.close()

    def test_manual_scroll_at_old_bottom_is_not_rearmed_by_a_stale_value_event(self) -> None:
        window = QuotaQtApp()
        try:
            window.resize(1080, 680)
            window.show()
            window.feed.clear_feed()
            for index in range(14):
                window.feed.add_user(f"历史施工描述 {index + 1}：用于形成足够长的滚动内容。")
            self.app.processEvents()
            bar = window.scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
            window._last_scroll_value = bar.value()
            window._pause_follow_latest()
            window._track_scroll_position(bar.value())
            self.assertTrue(window._manual_scroll_active)
            self.assertFalse(window._follow_latest)
        finally:
            window.close()

    def test_ai_result_replacement_restores_manual_reader_position(self) -> None:
        window = QuotaQtApp()
        try:
            window.resize(1080, 680)
            window.show()
            window.feed.clear_feed()
            for index in range(14):
                window.feed.add_user(f"历史施工描述 {index + 1}：用于形成足够长的滚动内容。")
            window.feed.add_status("AI 正在复核", "只基于本地候选方案生成解释。")
            self.app.processEvents()
            bar = window.scroll.verticalScrollBar()
            bar.setValue(max(bar.minimum(), bar.maximum() - 120))
            window._pause_follow_latest()
            reader_position = bar.value()
            epoch = window._manual_scroll_epoch
            window.feed.add_ai("## 结论\n复核完成。")
            window._restore_manual_scroll_position(reader_position, epoch)
            self.app.processEvents()
            self.assertEqual(bar.value(), reader_position)
            self.assertFalse(window._follow_latest)
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
