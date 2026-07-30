from __future__ import annotations

import unittest

from components.message import ai_references, evidence_button_text, format_ai_plain_text, logical_wrap_width, parse_ai_items, parse_ai_sections, strip_ai_reference_markers
from components.result import compact_analysis_content, proposal_decision_summary


class AiMessageFormatTests(unittest.TestCase):
    def test_compact_result_keeps_one_decision_and_hides_duplicate_candidates(self):
        summary, details = compact_analysis_content([
            ("结论", "- 已形成可复核的清单与定额组合建议。"),
            ("建议候选", "- 清单 010501001-000 基础垫层\n- 定额 2-1-28 混凝土垫层 无筋"),
            ("工程量与换算", "- 已按100mm厚度换算，系数为1。"),
        ])

        self.assertEqual(summary, "已形成可复核的清单与定额组合建议。")
        self.assertEqual(details, [("工程量与换算", ["已按100mm厚度换算，系数为1。"])])

    def test_first_screen_decision_names_the_bill_and_main_quota(self):
        result = {
            "clarification_questions": [],
            "proposals": [{
                "status": "ready_for_review", "bill_code": "010501001-000", "bill_title": "基础垫层",
                "quota_lines": [{"role": "main", "code": "2-1-28", "title": "混凝土垫层 无筋"}],
            }],
        }

        self.assertEqual(
            proposal_decision_summary(result),
            "建议清单 010501001-000 基础垫层，主定额 2-1-28 混凝土垫层 无筋。",
        )

    def test_first_screen_decision_prioritizes_the_local_question(self):
        result = {
            "clarification_questions": [{"question": "该垫层用于哪个部位？"}],
            "proposals": [{"status": "needs_clarification"}],
        }

        self.assertEqual(proposal_decision_summary(result), "先确认：该垫层用于哪个部位？")

    def test_markdown_sections_are_cleaned_for_card_rendering(self):
        text = """## 结论
需要补充工程专业和施工方法。 [R1][R2]

## 建议候选
建筑专业可优先复核 1-2-9。 [R2]

## 工程量与换算
按体积计算，单位差异需换算。 [R4]
"""

        sections = parse_ai_sections(text)

        self.assertEqual([section[0] for section in sections], ["结论", "建议候选", "工程量与换算"])
        self.assertNotIn("##", sections[0][1])
        self.assertIn("[R1] [R2]", sections[0][1])
        plain = format_ai_plain_text(sections)
        self.assertIn("结论：", plain)
        self.assertNotIn("##", plain)

    def test_unstructured_answer_has_a_readable_fallback_section(self):
        sections = parse_ai_sections("建议补充施工方法后复核 [R1]。")

        self.assertEqual(sections, [("AI 分析", "建议补充施工方法后复核 [R1]。")])

    def test_markdown_noise_is_removed_and_optional_empty_section_is_hidden(self):
        sections = parse_ai_sections("""## 1. 结论
- **可套**沟槽土方清单 [R2][R1]
## 风险提示
- 暂无
本建议仅供专业造价人员复核参考。
""")

        self.assertEqual(sections, [("结论", "- 可套沟槽土方清单 [R2] [R1]")])
        self.assertEqual(parse_ai_items(sections[0][1]), ["可套沟槽土方清单 [R2] [R1]"])
        self.assertEqual(ai_references(sections[0][1]), ["R1", "R2"])

    def test_sections_follow_decision_first_order_even_if_model_does_not(self):
        sections = parse_ai_sections("""## 风险
- 需确认运距。
## 判断依据
- 名称与条件匹配 [R3]。
## 结论
- 暂不能确定。
""")

        self.assertEqual([heading for heading, _body in sections], ["结论", "依据", "风险"])

    def test_wrap_width_accounts_for_windows_dpi_scaling(self):
        self.assertEqual(logical_wrap_width(932, 1.5), 600)
        self.assertEqual(logical_wrap_width(932, 1.0), 896)

    def test_internal_reference_ids_are_hidden_from_user_facing_text(self):
        text = "可套基础垫层 [R1][R7]，并复核关联项 [R15]。"

        self.assertEqual(strip_ai_reference_markers(text), "可套基础垫层，并复核关联项。")
        self.assertEqual(ai_references(text), ["R1", "R7", "R15"])

    def test_combined_reference_syntax_is_hidden_and_still_discovered(self):
        text = "结论依据 [R1,R7]。"

        self.assertEqual(strip_ai_reference_markers(text), "结论依据。")
        self.assertEqual(ai_references(text), ["R1", "R7"])

    def test_reference_id_touching_chinese_text_is_hidden(self):
        text = "清单定额关联R15确认可对应2-1-28。"

        self.assertEqual(strip_ai_reference_markers(text), "清单定额关联确认可对应2-1-28。")
        self.assertEqual(ai_references(text), ["R15"])

    def test_evidence_buttons_use_readable_source_names(self):
        self.assertEqual(evidence_button_text({"record_id": "bill:2024:76", "pdf_page": 35}), "清单原书 · 第 35 页")
        self.assertEqual(evidence_button_text({"record_id": "quota:171:173", "pdf_page": 42}), "定额原书 · 第 42 页")


if __name__ == "__main__":
    unittest.main()
