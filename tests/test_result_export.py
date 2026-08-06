from __future__ import annotations

import unittest

from tests.support import requires_authorized_catalog

from components.result import candidate_copy_lines, result_markdown
from utils.catalog import search_catalog
from utils.result_export import confirmed_proposal_payload, proposal_csv, result_csv


@requires_authorized_catalog
class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = search_catalog("挖沟槽土方，三类土，深度2.5米", quota_edition="2025", discipline="building", limit=6)

    def test_csv_rows_cover_groups(self):
        rows = result_csv(self.result)
        self.assertEqual(rows[0][0], "类型")
        labels = {row[0] for row in rows[1:]}
        self.assertIn("定额", labels)
        self.assertGreater(len(rows), 2)

    def test_candidate_copy_lines_are_tab_separated(self):
        text = candidate_copy_lines(self.result["quotas"][:2])
        for line in text.splitlines():
            parts = line.split("\t")
            self.assertEqual(len(parts), 3)
            self.assertTrue(parts[0])

    def test_markdown_contains_key_sections_and_disclaimer(self):
        text = result_markdown(self.result, {"primary": {"quota": self.result["quotas"][0]}}, "AI 解释文本 [R1]")
        self.assertIn("# 本地检索记录", text)
        self.assertIn("已暂存候选", text)
        self.assertIn("清单候选", text)
        self.assertIn("AI 解释", text)
        self.assertIn("人工复核", text)
        self.assertNotIn("完全准确", text)
        self.assertNotIn("无需审核", text)

    def test_markdown_without_ai_is_still_valid(self):
        text = result_markdown(self.result)
        self.assertIn("定额候选", text)

    def test_proposal_export_only_contains_confirmed_rows(self):
        proposal_result = {
            "analysis_version": "1",
            "query": "测试",
            "work_items": [{"id": "W1", "source_span": "测试事项"}],
            "proposals": [{
                "work_item_id": "W1", "confirmed": False, "status": "ready_for_review",
                "bill_record_id": "bill:1", "bill_code": "0101", "bill_title": "测试清单", "bill_unit": "m2",
                "bill_feature_description": "材料品种：SBS卷材\n厚度：4mm",
                "bill_calculation_rule": "按设计图示尺寸以面积计算",
                "bill_work_content": "基层处理；铺贴卷材",
                "quota_lines": [{"record_id": "quota:1", "role": "main", "code": "1-1", "title": "测试定额", "unit": "10m2", "evidence_refs": ["R2"]}],
                "evidence_refs": ["R1"], "evidence_pages": ["清单第1页", "定额第2页"], "evidence_located": True, "unresolved_question_ids": [], "hard_conflicts": [],
            }],
        }
        self.assertEqual(len(proposal_csv(proposal_result)), 1)
        self.assertEqual(confirmed_proposal_payload(proposal_result)["proposals"], [])
        proposal_result["proposals"][0]["confirmed"] = True
        self.assertEqual(len(proposal_csv(proposal_result)), 3)
        self.assertEqual(len(confirmed_proposal_payload(proposal_result)["proposals"]), 1)
        self.assertIn("假设/换算", proposal_csv(proposal_result)[0])
        self.assertIn("资料依据", proposal_csv(proposal_result)[0])
        self.assertIn("项目特征描述", proposal_csv(proposal_result)[0])
        self.assertIn("工程量计算规则", proposal_csv(proposal_result)[0])
        self.assertIn("工作内容", proposal_csv(proposal_result)[0])
        header = proposal_csv(proposal_result)[0]
        bill_row = proposal_csv(proposal_result)[1]
        self.assertIn("材料品种：SBS卷材", bill_row[header.index("项目特征描述")])
        self.assertEqual(bill_row[header.index("工程量计算规则")], "按设计图示尺寸以面积计算")

    def test_confirmed_structured_proposal_exports_without_pdf_evidence(self):
        result = {
            "analysis_version": "1", "query": "测试", "work_items": [{"id": "W1", "source_span": "测试事项"}],
            "proposals": [{
                "work_item_id": "W1", "confirmed": True, "status": "ready_for_review",
                "bill_record_id": "bill:1", "bill_code": "0101", "bill_title": "测试清单", "bill_unit": "m2",
                "quota_lines": [{"record_id": "quota:1", "role": "main", "code": "1-1", "title": "测试定额", "unit": "10m2"}],
                "evidence_refs": [], "evidence_pages": [], "evidence_located": False,
                "unresolved_question_ids": [], "hard_conflicts": [], "data_basis": "structured_catalog",
            }],
        }

        rows = proposal_csv(result)

        self.assertEqual(len(rows), 3)
        self.assertTrue(all("结构化定额库已匹配" in row[-1] for row in rows[1:]))
        self.assertEqual(len(confirmed_proposal_payload(result)["proposals"]), 1)


if __name__ == "__main__":
    unittest.main()
