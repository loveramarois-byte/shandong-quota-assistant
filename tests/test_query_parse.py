from __future__ import annotations

import unittest

from utils.query_parse import parse_query_conditions, rank_conditions


class QueryParseTests(unittest.TestCase):
    def test_common_shandong_conditions_are_normalized(self):
        conditions = parse_query_conditions("人工挖沟槽，三类土，槽深2.5m，弃土运距5km")
        self.assertEqual(conditions.object_type, "沟槽")
        self.assertEqual(conditions.soil_type, "坚土")
        self.assertEqual(conditions.method, "人工")
        self.assertEqual(conditions.depth_m, 2.5)
        self.assertEqual(conditions.distance_m, 5000)

    def test_specification_conditions_are_normalized(self):
        conditions = parse_query_conditions("C30垫层，厚度100mm，直径DN25")
        self.assertEqual(conditions.strength_grade, "C30")
        self.assertEqual(conditions.thickness_mm, 100)
        self.assertEqual(conditions.diameter_mm, 25)

    def test_short_thickness_wording_is_normalized(self):
        conditions = parse_query_conditions("道路水泥稳定碎石基层厚18cm")
        self.assertEqual(conditions.thickness_mm, 180)

    def test_conflicting_depth_is_not_ranked_as_a_match(self):
        score, reasons, missing, conflicts = rank_conditions(
            {"title": "人工挖沟槽土方 槽深≤2m 普通土"},
            parse_query_conditions("挖沟槽，三类土，深度2.5m"),
        )
        self.assertLess(score, 0)
        self.assertTrue(conflicts)
        self.assertFalse(reasons and any("深度 2.5m 落在" in value for value in reasons))

    def test_diameter_brackets_with_chinese_suffix_are_ranked(self):
        conditions = parse_query_conditions("室内给水管道安装 DN25")
        exact = rank_conditions({"title": "室内塑料给水管 外径25mm以内"}, conditions)
        too_small = rank_conditions({"title": "室内塑料给水管 外径20mm以内"}, conditions)
        larger = rank_conditions({"title": "室内塑料给水管 外径32mm以内"}, conditions)
        unspecified = rank_conditions({"title": "室内塑料给水管安装"}, conditions)
        self.assertGreater(exact[0], larger[0])
        self.assertGreater(exact[0], unspecified[0])
        self.assertLess(too_small[0], 0)
        self.assertTrue(too_small[3])
        self.assertTrue(unspecified[2])


if __name__ == "__main__":
    unittest.main()
