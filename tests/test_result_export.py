from __future__ import annotations

import unittest

from components.result import candidate_copy_lines, result_markdown
from utils.catalog import search_catalog
from utils.result_export import result_csv


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


if __name__ == "__main__":
    unittest.main()
