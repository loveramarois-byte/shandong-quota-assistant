from __future__ import annotations

import unittest

from utils.ai_structured import parse_structured_ai_response, validate_structured_ai_response


class StructuredAiTests(unittest.TestCase):
    def test_json_code_fence_is_parsed(self):
        payload = parse_structured_ai_response('```json\n{"analysis_version":"1","work_items":[],"clarification_questions":[],"proposals":[]}\n```')
        self.assertEqual(payload["analysis_version"], "1")

    def test_forged_record_id_is_blocked(self):
        result = {
            "discipline": "building",
            "work_items": [{"id": "W1"}],
            "bills": [{"record_id": "bill:2024:1", "discipline": "building", "edition": "2024"}],
            "quotas": [],
            "links": [{
                "record_id": "link:2024:1", "quota_record_id": "quota:1:1", "bill_record_id": "bill:2024:1",
                "discipline": "building", "quota_edition": "2025", "standard_edition": "2024",
            }],
        }
        payload = {
            "analysis_version": "1",
            "work_items": [{"id": "W1"}],
            "clarification_questions": [],
            "proposals": [{
                "work_item_id": "W1", "bill_record_id": "bill:2024:1",
                "quota_lines": [{"record_id": "quota:forged:9", "role": "main", "factor": None, "reason": "x", "evidence_refs": []}],
                "assumptions": [], "risks": [], "status": "ready_for_review",
            }],
        }

        validation = validate_structured_ai_response(payload, result)

        self.assertFalse(validation["valid"])
        self.assertTrue(any("白名单" in value for value in validation["errors"]))

    def test_every_local_work_item_must_have_exactly_one_proposal(self):
        result = {
            "discipline": "building", "quota_edition": "2025", "standard_edition": "2024",
            "work_items": [{"id": "W1"}, {"id": "W2"}], "clarification_questions": [],
            "bills": [], "quotas": [], "links": [],
        }
        payload = {"analysis_version": "1", "work_items": [{"id": "W1"}, {"id": "W2"}], "clarification_questions": [], "proposals": [{"work_item_id": "W1", "bill_record_id": None, "quota_lines": [], "status": "no_reliable_match"}]}

        validation = validate_structured_ai_response(payload, result)

        self.assertFalse(validation["valid"])
        self.assertTrue(any("W2" in value for value in validation["errors"]))

    def test_ai_cannot_clear_a_locally_assembled_proposal(self):
        result = {
            "discipline": "building", "quota_edition": "2025", "standard_edition": "2024",
            "work_items": [{"id": "W1"}], "clarification_questions": [],
            "bills": [{"record_id": "bill:2024:1", "discipline": "building", "edition": "2024", "unit": "m2"}],
            "quotas": [],
            "links": [{
                "record_id": "link:2024:1", "quota_record_id": "quota:1:1", "bill_record_id": "bill:2024:1",
                "discipline": "building", "quota_edition": "2025", "standard_edition": "2024", "unit": "10m2",
            }],
            "proposals": [{
                "work_item_id": "W1", "bill_record_id": "bill:2024:1",
                "quota_lines": [{"record_id": "quota:1:1", "role": "main"}], "status": "ready_for_review",
            }],
        }
        payload = {
            "analysis_version": "1", "work_items": [{"id": "W1"}], "clarification_questions": [],
            "proposals": [{"work_item_id": "W1", "bill_record_id": None, "quota_lines": [], "status": "no_reliable_match"}],
        }

        validation = validate_structured_ai_response(payload, result)

        self.assertFalse(validation["valid"])
        self.assertTrue(any("不得清空" in value for value in validation["errors"]))

    def test_ai_cannot_add_a_clarification_field(self):
        result = {
            "discipline": "building", "quota_edition": "2025", "standard_edition": "2024",
            "work_items": [{"id": "W1"}], "clarification_questions": [],
            "bills": [], "quotas": [], "links": [],
            "proposals": [{"work_item_id": "W1", "bill_record_id": None, "quota_lines": [], "status": "no_reliable_match"}],
        }
        payload = {
            "analysis_version": "1", "work_items": [{"id": "W1"}],
            "clarification_questions": [{"id": "Q1", "work_item_id": "W1", "field": "method", "question": "施工方式？", "options": ["人工", "机械"]}],
            "proposals": [{"work_item_id": "W1", "bill_record_id": None, "quota_lines": [], "status": "no_reliable_match"}],
        }

        validation = validate_structured_ai_response(payload, result)

        self.assertFalse(validation["valid"])
        self.assertTrue(any("不得新增" in value for value in validation["errors"]))

    def test_ai_cannot_remove_a_local_clarification_field(self):
        local_question = {"id": "Q1", "work_item_id": "W1", "field": "cushion_location", "question": "该垫层用于哪个部位？", "options": ["基础垫层", "楼地面垫层", "不确定"]}
        result = {
            "discipline": "building", "quota_edition": "2025", "standard_edition": "2024",
            "work_items": [{"id": "W1"}], "clarification_questions": [local_question],
            "bills": [], "quotas": [], "links": [],
            "proposals": [{"work_item_id": "W1", "bill_record_id": None, "quota_lines": [], "status": "needs_clarification"}],
        }
        payload = {
            "analysis_version": "1", "work_items": [{"id": "W1"}], "clarification_questions": [],
            "proposals": [{"work_item_id": "W1", "bill_record_id": None, "quota_lines": [], "status": "needs_clarification"}],
        }

        validation = validate_structured_ai_response(payload, result)

        self.assertFalse(validation["valid"])
        self.assertTrue(any("不得删除" in value for value in validation["errors"]))

    def test_ai_cannot_randomly_downgrade_a_ready_local_proposal(self):
        result = {
            "discipline": "building", "quota_edition": "2025", "standard_edition": "2024",
            "work_items": [{"id": "W1"}], "clarification_questions": [],
            "bills": [{"record_id": "bill:2024:1", "discipline": "building", "edition": "2024", "unit": "m2"}],
            "quotas": [],
            "links": [{
                "record_id": "link:2024:1", "quota_record_id": "quota:1:1", "bill_record_id": "bill:2024:1",
                "discipline": "building", "quota_edition": "2025", "standard_edition": "2024", "unit": "m2",
            }],
            "proposals": [{
                "work_item_id": "W1", "bill_record_id": "bill:2024:1",
                "quota_lines": [{"record_id": "quota:1:1", "role": "main"}], "status": "ready_for_review",
            }],
        }
        payload = {
            "analysis_version": "1", "work_items": [{"id": "W1"}], "clarification_questions": [],
            "proposals": [{
                "work_item_id": "W1", "bill_record_id": "bill:2024:1",
                "quota_lines": [{"record_id": "quota:1:1", "role": "main"}], "status": "needs_clarification",
            }],
        }

        validation = validate_structured_ai_response(payload, result)

        self.assertFalse(validation["valid"])
        self.assertTrue(any("不得随机降级" in value for value in validation["errors"]))


if __name__ == "__main__":
    unittest.main()
