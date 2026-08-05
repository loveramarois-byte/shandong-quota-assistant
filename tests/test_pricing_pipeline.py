from __future__ import annotations

import unittest

from utils.pricing_pipeline import analyze_pricing_description, assemble_pricing_result, infer_discipline, merge_clarification_context, proposal_confirmable, validate_pricing_result
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
        "source_path": extra.pop("source_path", "D:/fixtures/source.pdf"),
        "pdf_page": extra.pop("pdf_page", 1),
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
        self.assertEqual(proposal["data_basis"], "structured_catalog")
        self.assertFalse(proposal["source_review_required"])
        self.assertTrue(all(line["source_status"] == "source_page_linked" for line in proposal["quota_lines"]))
        self.assertTrue(analysis["validation"]["valid"])

    def test_material_thickness_does_not_add_an_extra_layer_quota(self):
        item = extract_work_item("地下室外墙4mm SBS防水卷材", item_id="W1", discipline="building")
        analysis = assemble_pricing_result(
            item.source_span,
            [(item, {"bills": [self.bill], "quotas": [], "links": [self.main, self.adjustment], "guidance": [], "hints": []})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )

        proposal = analysis["proposals"][0]
        self.assertEqual([line["code"] for line in proposal["quota_lines"]], ["9-1-1"])

    def test_structured_only_relation_is_confirmable_without_pdf_page(self):
        main = dict(self.main, source_path="", pdf_page=None, alignment_status="master_only")
        adjustment = dict(self.adjustment, source_path="", pdf_page=None, alignment_status="master_only")
        analysis = assemble_pricing_result(
            self.item.source_span,
            [(self.item, {"bills": [self.bill], "quotas": [], "links": [main, adjustment], "guidance": [], "hints": []})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )

        proposal = analysis["proposals"][0]
        self.assertEqual(proposal["status"], "ready_for_review")
        self.assertFalse(proposal["evidence_located"])
        self.assertEqual(proposal["evidence_pages"], ["清单第1页"])
        self.assertTrue(proposal_confirmable(proposal))
        self.assertTrue(proposal["source_review_required"])
        self.assertIn("主定额暂无对应原书页", proposal["source_review_reasons"])
        self.assertEqual(proposal["quota_lines"][0]["source_status"], "structured_only")

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

    def test_plain_concrete_cushion_prefers_unreinforced_and_uses_thickness_conversion(self):
        item = extract_work_item("基础C15混凝土垫层，厚度100mm", item_id="W1", discipline="building")
        bill = _candidate("bill:2024:76", "010501001-000", "基础垫层", "bill_item", edition="2024", unit="m3")
        light_aggregate = _candidate(
            "link:2024:982", "2-1-26", "混凝土垫层 轻骨料", "bill_quota_link",
            quota_edition="2025", standard_edition="2024", bill_record_id=bill["record_id"],
            quota_record_id="quota:171:171", bill_code=bill["code"], unit="10m3", factor=1.0,
        )
        unreinforced = _candidate(
            "link:2024:984", "2-1-28", "混凝土垫层 无筋", "bill_quota_link",
            quota_edition="2025", standard_edition="2024", bill_record_id=bill["record_id"],
            quota_record_id="quota:171:173", bill_code=bill["code"], unit="10m2", factor=1.0,
        )

        analysis = assemble_pricing_result(
            item.source_span,
            [(item, {"bills": [bill], "quotas": [], "links": [light_aggregate, unreinforced], "guidance": [], "hints": []})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )

        proposal = analysis["proposals"][0]
        self.assertEqual(proposal["quota_lines"][0]["code"], "2-1-28")
        self.assertEqual(proposal["quota_lines"][0]["factor"], 1.0)
        self.assertEqual(proposal["status"], "ready_for_review")
        self.assertTrue(analysis["validation"]["valid"])
        self.assertTrue(any("100mm" in value for value in proposal["assumptions"]))
        self.assertTrue(proposal["source_review_required"])
        self.assertIn("方案包含假设或换算", proposal["source_review_reasons"])

    def test_concrete_cushion_bill_outranks_generic_concrete_rebar_bill(self):
        item = extract_work_item("基础C15混凝土垫层，厚度100mm", item_id="W1", discipline="building")
        cushion = _candidate("bill:2024:76", "010501001-000", "基础垫层", "bill_item", edition="2024", unit="m3")
        rebar = _candidate("bill:2024:161", "010506001-000", "现浇混凝土基础及联系梁钢筋", "bill_item", edition="2024", unit="t")
        main = _candidate(
            "link:2024:984", "2-1-28", "混凝土垫层 无筋", "bill_quota_link",
            quota_edition="2025", standard_edition="2024", bill_record_id=cushion["record_id"],
            quota_record_id="quota:171:173", bill_code=cushion["code"], unit="10m2", factor=1.0,
        )

        analysis = assemble_pricing_result(
            item.source_span,
            [(item, {"bills": [rebar, cushion], "quotas": [], "links": [main], "guidance": [], "hints": []})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )

        self.assertEqual(analysis["proposals"][0]["bill_code"], cushion["code"])
        self.assertEqual(analysis["proposals"][0]["status"], "ready_for_review")

    def test_non_unit_factor_requests_source_review_but_remains_confirmable(self):
        main = dict(self.main, factor=1.2)
        analysis = assemble_pricing_result(
            "SBS卷材防水一层",
            [(extract_work_item("SBS卷材防水一层", item_id="W1", discipline="building"), {"bills": [self.bill], "quotas": [], "links": [main], "guidance": [], "hints": []})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )

        proposal = analysis["proposals"][0]
        self.assertTrue(proposal_confirmable(proposal))
        self.assertTrue(proposal["source_review_required"])
        self.assertIn("方案包含非 1.0 系数", proposal["source_review_reasons"])

    def test_missing_conversion_thickness_becomes_a_clarification(self):
        item = extract_work_item("基础C15混凝土垫层", item_id="W1", discipline="building")
        bill = _candidate("bill:2024:76", "010501001-000", "基础垫层", "bill_item", edition="2024", unit="m3")
        main = _candidate(
            "link:2024:984", "2-1-28", "混凝土垫层 无筋", "bill_quota_link",
            quota_edition="2025", standard_edition="2024", bill_record_id=bill["record_id"],
            quota_record_id="quota:171:173", bill_code=bill["code"], unit="10m2", factor=1.0,
        )

        analysis = assemble_pricing_result(
            item.source_span,
            [(item, {"bills": [bill], "quotas": [], "links": [main], "guidance": [], "hints": []})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )

        self.assertEqual(analysis["proposals"][0]["status"], "needs_clarification")
        self.assertEqual(analysis["clarification_questions"][0]["field"], "thickness")
        self.assertTrue(analysis["validation"]["valid"])

    def test_cushion_without_location_always_requires_deterministic_clarification(self):
        item = extract_work_item("C15混凝土垫层，厚度100mm", item_id="W1", discipline="building")
        bill = _candidate("bill:2024:76", "010501001-000", "基础垫层", "bill_item", edition="2024", unit="m3")
        main = _candidate(
            "link:2024:984", "2-1-28", "混凝土垫层 无筋", "bill_quota_link",
            quota_edition="2025", standard_edition="2024", bill_record_id=bill["record_id"],
            quota_record_id="quota:171:173", bill_code=bill["code"], unit="10m2", factor=1.0,
        )

        analysis = assemble_pricing_result(
            item.source_span,
            [(item, {"bills": [bill], "quotas": [], "links": [main], "guidance": [], "hints": []})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="building",
        )

        question = analysis["clarification_questions"][0]
        self.assertEqual(analysis["proposals"][0]["status"], "needs_clarification")
        self.assertEqual(question["field"], "cushion_location")
        self.assertEqual(question["question"], "该垫层用于哪个部位？")
        self.assertEqual(question["options"], ["基础垫层", "楼地面垫层", "其他部位", "不确定"])
        self.assertTrue(analysis["validation"]["valid"])

    def test_empty_selected_discipline_retries_one_high_confidence_discipline(self):
        calls: list[str | None] = []
        bill = _candidate("bill:2024:76", "010501001-000", "基础垫层", "bill_item", edition="2024", unit="m3")
        main = _candidate(
            "link:2024:984", "2-1-28", "混凝土垫层 无筋", "bill_quota_link",
            quota_edition="2025", standard_edition="2024", bill_record_id=bill["record_id"],
            quota_record_id="quota:171:173", bill_code=bill["code"], unit="10m2", factor=1.0,
        )

        def search(_query, *, discipline=None, **_kwargs):
            calls.append(discipline)
            return {
                "bills": [bill] if discipline == "building" else [],
                "quotas": [],
                "links": [main] if discipline == "building" else [],
                "guidance": [],
                "hints": [],
            }

        analysis = analyze_pricing_description(
            "基础C15混凝土垫层，厚度100mm",
            quota_edition="2025",
            standard_edition="2024",
            discipline="installation",
            search_fn=search,
        )

        self.assertEqual(infer_discipline("基础C15混凝土垫层，厚度100mm"), "building")
        self.assertEqual(calls, ["installation", "building"])
        self.assertEqual(analysis["discipline"], "building")
        self.assertTrue(analysis["discipline_auto_switched"])
        self.assertEqual(analysis["decision_status"], "ready_for_review")

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

    def test_water_supply_install_cannot_select_protection_bill(self):
        item = extract_work_item("室内给水管道安装DN25", item_id="W1", discipline="installation")
        wrong_bill = _candidate("bill:2024:1780", "030813011-000", "管道安拆后的充气保护", "bill_item", edition="2024", discipline="installation", unit="项")
        analysis = assemble_pricing_result(item.source_span, [(item, {"bills": [wrong_bill], "quotas": [], "links": [], "guidance": [], "hints": []})], quota_edition="2025", standard_edition="2024", discipline="installation")
        proposal = analysis["proposals"][0]
        self.assertEqual(proposal["status"], "no_reliable_match")
        self.assertFalse(proposal["bill_record_id"] )
        self.assertFalse(proposal_confirmable(proposal))

    def test_pipe_insulation_cannot_select_hydraulic_test(self):
        item = extract_work_item("管道橡塑保温厚30mm", item_id="W1", discipline="installation")
        bill = _candidate("bill:2024:1689", "030801020-000", "低压直埋保温管道", "bill_item", edition="2024", discipline="installation", unit="m")
        wrong = _candidate("link:2024:20623", "8-5-1", "低中压管道液压试验 公称直径50mm以内", "bill_quota_link", quota_edition="2025", standard_edition="2024", bill_record_id=bill["record_id"], quota_record_id="quota:172:12881", discipline="installation", unit="100m")
        analysis = assemble_pricing_result(item.source_span, [(item, {"bills": [bill], "quotas": [], "links": [wrong], "guidance": [], "hints": []})], quota_edition="2025", standard_edition="2024", discipline="installation")
        proposal = analysis["proposals"][0]
        self.assertNotEqual(proposal["status"], "ready_for_review")
        self.assertFalse(proposal["quota_lines"] )
        self.assertFalse(proposal_confirmable(proposal))

    def test_wall_paint_cannot_select_concrete_wall(self):
        item = extract_work_item("外墙涂料两遍", item_id="W1", discipline="building")
        bill = _candidate("bill:2024:86", "010502009-000", "地下室外墙", "bill_item", edition="2024", unit="m3")
        wrong = _candidate("link:2024:1051", "5-1-25", "现浇混凝土 地下室外墙", "bill_quota_link", quota_edition="2025", standard_edition="2024", bill_record_id=bill["record_id"], quota_record_id="quota:171:508", unit="10m3")
        analysis = assemble_pricing_result(item.source_span, [(item, {"bills": [bill], "quotas": [], "links": [wrong], "guidance": [], "hints": []})], quota_edition="2025", standard_edition="2024", discipline="building")
        proposal = analysis["proposals"][0]
        self.assertEqual(proposal["status"], "no_reliable_match")
        self.assertFalse(proposal_confirmable(proposal))

    def test_landscape_without_size_requires_real_specification_choice(self):
        item = extract_work_item("栽植乔木20株", item_id="W1", discipline="landscape")
        bill = _candidate("bill:2024:2947", "050103001-000", "栽植乔木", "bill_item", edition="2024", discipline="landscape", unit="株")
        main = _candidate("link:2024:32974", "1-2-26", "栽植乔木(带土球) 土球直径20cm以内", "bill_quota_link", quota_edition="2025", standard_edition="2024", bill_record_id=bill["record_id"], quota_record_id="quota:174:152", discipline="landscape", unit="株")
        analysis = assemble_pricing_result(item.source_span, [(item, {"bills": [bill], "quotas": [], "links": [main], "guidance": [], "hints": []})], quota_edition="2025", standard_edition="2024", discipline="landscape")
        self.assertEqual(analysis["decision_status"], "needs_clarification")
        question = analysis["clarification_questions"][0]
        self.assertEqual(question["field"], "plant_spec")
        self.assertIn("土球直径20cm以内", question["options"] )

    def test_whole_order_uses_worst_item_status(self):
        ready = assemble_pricing_result("SBS卷材防水两道", [(self.item, {"bills": [self.bill], "quotas": [], "links": [self.main, self.adjustment], "guidance": [], "hints": []})], quota_edition="2025", standard_edition="2024", discipline="building")
        second = extract_work_item("外墙涂料两遍", item_id="W2", discipline="building")
        mixed = assemble_pricing_result("SBS卷材防水两道；外墙涂料两遍", [(self.item, {"bills": [self.bill], "quotas": [], "links": [self.main, self.adjustment], "guidance": [], "hints": []}), (second, {"bills": [], "quotas": [], "links": [], "guidance": [], "hints": []})], quota_edition="2025", standard_edition="2024", discipline="building")
        self.assertEqual(ready["decision_status"], "ready_for_review")
        self.assertEqual(mixed["decision_status"], "no_reliable_match")
        self.assertEqual(mixed["progress"], {"ready": 1, "total": 2})

    def test_installation_pipe_does_not_ask_irrelevant_manual_machine_question(self):
        item = extract_work_item("电线管埋墙里，20的JDG", item_id="W1", discipline="installation")
        bill = _candidate("bill:2024:100", "030412001-000", "电气配管", "bill_item", edition="2024", discipline="installation", unit="m")
        main = _candidate(
            "link:2024:100", "4-12-8", "砖混结构钢导管暗配 公称直径20mm以内", "bill_quota_link",
            quota_edition="2025", standard_edition="2024", bill_record_id=bill["record_id"],
            quota_record_id="quota:172:100", bill_code=bill["code"], discipline="installation", unit="100m",
        )
        analysis = assemble_pricing_result(
            item.source_span,
            [(item, {"bills": [bill], "quotas": [], "links": [main], "guidance": [], "hints": ["候选区分人工/机械施工方法，请补充施工方法"]})],
            quota_edition="2025",
            standard_edition="2024",
            discipline="installation",
        )
        self.assertNotIn("method", {value["field"] for value in analysis["clarification_questions"]})


@unittest.skipUnless(__import__("utils.paths", fromlist=["database_path"]).database_path().exists(), "完整结构化资料库未安装")
class RealCataloguePricingRegressionTests(unittest.TestCase):
    def _proposal_codes(self, query: str, discipline: str) -> tuple[dict, set[str], set[str]]:
        result = analyze_pricing_description(
            query,
            quota_edition="2025",
            standard_edition="2024",
            discipline=discipline,
            limit=8,
        )
        bills = {str(value.get("bill_code") or "") for value in result.get("proposals") or []}
        quotas = {
            str(line.get("code") or "")
            for proposal in result.get("proposals") or []
            for line in proposal.get("quota_lines") or []
            if line.get("role") == "main"
        }
        return result, bills, quotas

    def test_newcomer_jdg_wording_selects_20mm_dark_conduit(self):
        result, bills, quotas = self._proposal_codes("电线管埋墙里，20的JDG", "installation")
        self.assertIn("030412001-000", bills)
        self.assertIn("4-12-8", quotas)
        self.assertNotIn("method", {value["field"] for value in result.get("clarification_questions") or []})

    def test_spaced_sbs_query_returns_the_linked_main_quota(self):
        result, bills, quotas = self._proposal_codes("地下室外墙 4mm 厚 SBS 防水卷材", "building")
        self.assertIn("010903001-000", bills)
        self.assertIn("9-2-11", quotas)
        proposal = result["proposals"][0]
        self.assertEqual([line["code"] for line in proposal["quota_lines"]], ["9-2-11"])
        method = next(value for value in result["clarification_questions"] if value["field"] == "method")
        self.assertEqual(method["options"][:3], ["热熔法", "冷粘法", "自粘法"])

    def test_cast_in_place_concrete_column_does_not_drift_to_rebar_bill(self):
        result, bills, quotas = self._proposal_codes("现浇C30混凝土柱，泵送施工", "building")

        self.assertIn("010502006-000", bills)
        self.assertIn("5-1-15", quotas)
        self.assertNotIn("010506002-000", bills)

    def test_newcomer_road_base_wording_selects_water_stabilized_base(self):
        _result, bills, quotas = self._proposal_codes("道路基层18公分水稳", "municipal")
        self.assertIn("040202014-000", bills)
        self.assertIn("2-1-18", quotas)

    def test_newcomer_tree_wording_selects_80cm_soil_ball_bracket(self):
        _result, bills, quotas = self._proposal_codes("种一棵土球80公分的香樟", "landscape")
        self.assertIn("050103001-000", bills)
        self.assertIn("1-2-32", quotas)

    def test_newcomer_plain_concrete_wording_selects_foundation_cushion(self):
        _result, bills, quotas = self._proposal_codes("基础下面浇一层C15素混凝土，10公分", "building")
        self.assertIn("010501001-000", bills)
        self.assertIn("2-1-28", quotas)

    def test_bill_code_embedded_in_a_sentence_uses_exact_bill(self):
        _result, bills, _quotas = self._proposal_codes("只知道清单编码030412001", "installation")
        self.assertIn("030412001-000", bills)

    def test_scaffold_has_a_main_quota_and_only_asks_relevant_conditions(self):
        result, _bills, quotas = self._proposal_codes("外脚手架搭设", "building")
        self.assertTrue(quotas)
        self.assertTrue(result["validation"]["valid"])
        self.assertIn("scaffold_spec", {value["field"] for value in result.get("clarification_questions") or []})


if __name__ == "__main__":
    unittest.main()
