from __future__ import annotations

import unittest

from utils.formatting import discipline_label, enrich_item, normalize_unit, parse_sections


class FormattingTests(unittest.TestCase):
    def test_discipline_and_unit_labels(self):
        self.assertEqual(discipline_label("building"), "建筑")
        self.assertEqual(discipline_label("municipal"), "市政")
        self.assertEqual(normalize_unit("m3"), "m³")
        self.assertEqual(normalize_unit("10m3"), "10m³")

    def test_bill_sections_are_extracted(self):
        sections = parse_sections("""项目名称: 挖沟槽土方
单位: m3
项目特征:
1.土类别
2.开挖深度
工程量计算规则:
按设计图示尺寸以体积计算
工作内容:
1.开挖
2.运输
""")
        self.assertEqual(sections["单位"], "m³")
        self.assertIn("土类别", sections["项目特征"])
        self.assertIn("体积计算", sections["工程量计算规则"])
        self.assertIn("运输", sections["工作内容"])

    def test_quota_resources_are_readable(self):
        item = enrich_item({
            "type": "quota_item",
            "discipline": "building",
            "edition": "2025",
            "text": "定额编号: 1-1-1\n定额名称: 人工挖土方\n单位: 10m3\n工作内容：挖土。\n人材机:\n综合工日(土建)  1.45 工日",
            "metadata": {"resources": [{"name": "综合工日(土建)", "quantity": 1.45, "unit": "工日"}]},
        })
        self.assertEqual(item["unit"], "10m³")
        self.assertEqual(item["resources"], ["综合工日(土建) 1.45 工日"])
        self.assertIn("挖土", item["work_content"])


if __name__ == "__main__":
    unittest.main()
