from __future__ import annotations

import unittest

from utils.ai_presentation import build_ai_suggestion_view_model, option_presentation


class AiPresentationTests(unittest.TestCase):
    def test_missing_method_is_explained_without_exposing_codes_in_headline(self) -> None:
        result = {
            "work_items": [
                {
                    "location": "地下室外墙",
                    "material": "SBS 防水卷材",
                    "attributes": [{"key": "thickness", "source": "4mm"}],
                }
            ],
            "clarification_questions": [
                {
                    "id": "Q1",
                    "field": "method",
                    "question": "本项采用哪种施工方式？",
                    "options": ["热熔法", "冷粘法", "自粘法", "热风焊接法"],
                }
            ],
            "proposals": [
                {
                    "status": "needs_clarification",
                    "bill_code": "010903001-000",
                    "bill_title": "墙面卷材防水",
                    "review_candidates": [{"code": "9-2-11", "title": "改性沥青卷材热熔法一层 立面"}],
                }
            ],
        }

        view = build_ai_suggestion_view_model("## 结论\n还需要确认施工方式。", result)

        self.assertEqual(view["state"], "needs_confirmation")
        self.assertIn("地下室外墙", view["headline"])
        self.assertIn("4mm SBS 防水卷材", view["headline"])
        self.assertIn("还需要确认施工方式", view["headline"])
        self.assertNotIn("010903001-000", view["headline"])
        self.assertNotIn("9-2-11", view["headline"])
        reasons = {(value["label"], value["value"], value["status"]) for value in view["reasons"]}
        self.assertIn(("使用部位", "地下室外墙", "confirmed"), reasons)
        self.assertIn(("材料类型", "SBS 防水卷材", "confirmed"), reasons)
        self.assertIn(("材料厚度", "4mm", "confirmed"), reasons)
        self.assertIn(("施工方式", "尚未确认", "missing"), reasons)
        self.assertEqual(view["question"]["options"][0]["display"], "使用喷灯加热粘贴  ·  热熔法")

    def test_ready_suggestion_keeps_professional_codes_in_details_only(self) -> None:
        result = {
            "work_items": [
                {
                    "location": "地下室外墙",
                    "material": "SBS 防水卷材",
                    "attributes": [
                        {"key": "thickness", "source": "4mm"},
                        {"key": "hot_melt", "source": "热熔"},
                    ],
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
                    "bill_work_content": "基层处理；铺贴卷材",
                    "quota_lines": [
                        {
                            "code": "9-2-11",
                            "title": "改性沥青卷材热熔法一层 立面",
                            "unit": "10m²",
                        }
                    ],
                }
            ],
        }

        view = build_ai_suggestion_view_model("## 结论\n方案已生成。", result)

        self.assertEqual(view["state"], "ready")
        self.assertIn("地下室外墙", view["headline"])
        self.assertIn("4mm SBS 防水卷材", view["headline"])
        self.assertIn("按热熔法施工", view["headline"])
        self.assertNotIn("010903001-000", view["headline"])
        self.assertNotIn("9-2-11", view["headline"])
        self.assertEqual(view["bill"]["code"], "010903001-000")
        self.assertIn("施工部位：地下室外墙", view["bill"]["feature_description"])
        self.assertEqual(view["bill"]["calculation_rule"], "按设计图示尺寸以面积计算")
        self.assertEqual(view["bill"]["work_content"], "基层处理；铺贴卷材")
        self.assertEqual(view["quotas"][0]["code"], "9-2-11")

    def test_quota_work_content_is_explained_in_plain_language_without_table_noise(self) -> None:
        result = {
            "proposals": [
                {
                    "status": "ready_for_review",
                    "bill_title": "墙面卷材防水",
                    "quota_lines": [
                        {
                            "record_id": "Q1",
                            "code": "9-2-11",
                            "title": "改性沥青卷材热熔法一层 立面",
                        }
                    ],
                }
            ],
            "quotas": [
                {
                    "record_id": "Q1",
                    "work_content": "清理基层,刷基底处理剂,收头钉压条等全部操作过程。 计量单位：10m² 定额编号 9-2-11",
                }
            ],
        }

        view = build_ai_suggestion_view_model("", result)

        summary = view["quotas"][0]["work_summary"]
        self.assertEqual(summary, "简单说，这项定额已经包括：清理基层、刷基底处理剂、收头钉压条等操作。")
        self.assertNotIn("计量单位", summary)
        self.assertNotIn("定额编号", summary)

    def test_missing_fields_degrade_to_clear_placeholder(self) -> None:
        view = build_ai_suggestion_view_model("", {"proposals": [{}]})

        self.assertEqual(view["state"], "empty")
        self.assertEqual(view["bill"]["name"], "未获取到")
        self.assertEqual(view["bill"]["code"], "未获取到")
        self.assertEqual(view["quotas"], [])

    def test_unknown_option_remains_selectable_without_inventing_explanation(self) -> None:
        presentation = option_presentation("其他工法")

        self.assertEqual(presentation["professional_name"], "其他工法")
        self.assertEqual(presentation["display"], "其他工法")

    def test_concrete_column_summary_names_the_member_and_separates_methods(self) -> None:
        result = {
            "work_items": [
                {
                    "object": "柱",
                    "material": "混凝土",
                    "attributes": [
                        {"key": "strength_grade", "source": "C30"},
                        {"key": "pump", "source": "泵送"},
                        {"key": "cast_in_place", "source": "现浇"},
                    ],
                }
            ],
            "proposals": [
                {
                    "status": "ready_for_review",
                    "bill_title": "钢筋混凝土柱",
                    "quota_lines": [{"title": "现浇混凝土 矩形柱"}],
                }
            ],
        }

        view = build_ai_suggestion_view_model("", result)

        self.assertIn("混凝土柱", view["headline"])
        self.assertIn("按泵送施工", view["headline"])
        reasons = {(value["label"], value["value"]) for value in view["reasons"]}
        self.assertIn(("混凝土输送", "泵送"), reasons)
        self.assertIn(("构件做法", "现浇"), reasons)


if __name__ == "__main__":
    unittest.main()
