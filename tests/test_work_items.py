from __future__ import annotations

import unittest

from utils.work_items import extract_work_item, segment_description


class WorkItemSegmentationTests(unittest.TestCase):
    def test_structural_member_outranks_generic_concrete_material(self):
        item = extract_work_item("现浇C30混凝土柱，泵送施工", item_id="W1", discipline="building")

        self.assertEqual(item.object, "柱")
        self.assertEqual(item.material, "混凝土")

    def test_spaced_sbs_name_keeps_the_specific_material(self):
        item = segment_description("地下室外墙 4mm 厚 SBS 防水卷材", discipline="building")[0]
        self.assertEqual(item.material, "SBS防水卷材")

    def test_compound_description_is_split_into_independent_items(self):
        text = "地下室外墙外侧做4mm SBS防水两道，20厚水泥砂浆保护层，外侧回填三七灰土，机械夯实。"

        items = segment_description(text, discipline="building")

        self.assertEqual(len(items), 3)
        self.assertIn("SBS防水两道", items[0].source_span)
        self.assertIn("水泥砂浆保护层", items[1].source_span)
        self.assertIn("机械夯实", items[2].source_span)
        self.assertEqual([item.id for item in items], ["W1", "W2", "W3"])

    def test_conditions_do_not_become_detached_work_items(self):
        items = segment_description("挖沟槽土方，三类土，机械开挖，深2.5m", discipline="building")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_span, "挖沟槽土方，三类土，机械开挖，深2.5m")

    def test_road_material_grade_and_suffix_thickness_stay_on_one_item(self):
        items = segment_description("我要在小区修一条内部路,用C20混凝土30cm厚", discipline="municipal")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].object, "路面")
        attributes = {attribute.key: attribute for attribute in items[0].attributes}
        self.assertEqual(attributes["strength_grade"].value, "C20")
        self.assertEqual(attributes["thickness"].value, 300.0)
        self.assertEqual(attributes["thickness"].unit, "mm")

    def test_typed_attributes_and_negative_constraints_keep_source_text(self):
        item = extract_work_item(
            "4mm SBS防水两道，不含保护层和外运",
            item_id="W1",
            discipline="building",
        )

        attributes = {attribute.key: attribute for attribute in item.attributes}
        self.assertEqual(attributes["thickness"].value, 4.0)
        self.assertEqual(attributes["thickness"].unit, "mm")
        self.assertEqual(attributes["layers"].value, 2)
        self.assertTrue(any(value.key == "protection_layer" for value in item.negative_constraints))
        self.assertTrue(any(value.key == "transport" for value in item.negative_constraints))
        self.assertTrue(all(value.source for value in [*item.attributes, *item.negative_constraints]))


if __name__ == "__main__":
    unittest.main()
