from __future__ import annotations

import unittest

from utils.pricing_pipeline import assemble_pricing_result, merge_clarification_context, validate_pricing_result
from utils.work_items import extract_work_item


def _candidate(record_id: str, code: str, title: str, kind: str, **extra):
    return {
        "record_id": record_id,
        "chunk_id": record_id,
        "code": code,
        "title": title,
        "type": kind,
        "entity_type": kind,
        "edition": extra.pop("edition", "2025"),
        "discipline": extra.pop("discipline", "building"),
        "unit": extra.pop("unit", "10m2"),
        "match_reasons": extra.pop("match_reasons", ["测试命中"]),
        "missing_conditions": extra.pop("missing_conditions", []),
        "conflicts": extra.pop("conflicts", []),
        **extra,
    }


class PricingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.item = extract_work_item("SBS卷材防水两道", item_id="W1", discipline="building")
        self.bill = _candidate("bill:2024:10", "010902001-000", "屋面卷材防水", "bill_item", edition="2024", unit="m2")
        self.main = _candidate(
            "link:2024:20", "9-1-1", "SBS改性沥青卷材防水", "bill_quota_link",
            quota_edition="2025", standard_edition="2024", bill_record_id=self.bill["record_id"],
            quota_record_id="quota:8:1", bill_code=self.bill["code"], unit="10m2",
        )
        self.adjustment = _candidate(
            "link:2024:21", "9-1-2", "卷材防水每增加一层", "bill_quota_link",
            quota_edition="2025", standard_edition="2024", bill_record_id=self.bill["record_id"],
            quota_record_id="quota:8:2", bill_code=self.bill["code"], unit="10m2",
        )

    def test_one_bill_can_assemble_multiple_role_tagged_quota_lines(self):
        analysis = assemble_pricing_result(
            "SBS卷材防水两道",
            [(self.item, {"bills": [self.bill], "quotas": [], "links": [self.main, self.adjustment], "guidance": [], "hints": []})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )

        proposal = analysis["proposals"][0]
        self.assertEqual(proposal["bill_record_id"], self.bill["record_id"])
        self.assertEqual([line["role"] for line in proposal["quota_lines"]], ["main", "adjustment"])
        self.assertEqual(proposal["status"], "ready_for_review")
        self.assertTrue(analysis["validation"]["valid"])

    def test_unknown_record_id_is_rejected_by_deterministic_validator(self):
        analysis = assemble_pricing_result(
            "SBS卷材防水两道",
            [(self.item, {"bills": [self.bill], "quotas": [], "links": [self.main], "guidance": [], "hints": []})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )
        analysis["proposals"][0]["quota_lines"][0]["record_id"] = "quota:forged:999"

        validation = validate_pricing_result(analysis)

        self.assertFalse(validation["valid"])
        self.assertTrue(any("白名单" in error for error in validation["errors"]))

    def test_missing_material_condition_becomes_a_structured_question(self):
        uncertain_main = dict(self.main, missing_conditions=["未说明防水材料类型"])
        analysis = assemble_pricing_result(
            "地下室外墙防水",
            [(extract_work_item("地下室外墙防水", item_id="W1", discipline="building"), {"bills": [self.bill], "quotas": [], "links": [uncertain_main], "guidance": [], "hints": ["请补充防水材料类型"]})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )

        self.assertEqual(analysis["proposals"][0]["status"], "needs_clarification")
        self.assertLessEqual(len(analysis["clarification_questions"]), 3)
        self.assertEqual(analysis["clarification_questions"][0]["work_item_id"], "W1")

    def test_short_follow_up_is_merged_into_original_work_item(self):
        previous = {
            "work_items": [{"id": "W1", "source_span": "墙面SBS卷材防水两道"}],
            "clarification_questions": [{"id": "Q1", "work_item_id": "W1", "field": "method"}],
        }

        merged = merge_clarification_context(previous, "热熔法")

        self.assertEqual(merged, ("墙面SBS卷材防水两道，热熔法", "Q1"))

    def test_new_full_description_is_not_mistaken_for_a_follow_up(self):
        previous = {
            "work_items": [{"id": "W1", "source_span": "墙面防水"}],
            "clarification_questions": [{"id": "Q1", "work_item_id": "W1", "field": "method"}],
        }

        self.assertIsNone(merge_clarification_context(previous, "电气配管DN20暗配；电缆敷设"))


if __name__ == "__main__":
    unittest.main()
