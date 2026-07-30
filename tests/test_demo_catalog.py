from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import utils.catalog as catalog
from tools.build_demo_catalog import DISCIPLINES, build_demo_catalog


class DemoCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = build_demo_catalog(Path(self.temporary.name) / "demo_catalog.sqlite")

    def _environment(self):
        catalog._validated_database_signature = None
        return patch.dict(os.environ, {"SHANDONG_QUOTA_DB": str(self.path)}, clear=False)

    def test_generated_database_matches_public_schema_and_counts(self):
        connection = sqlite3.connect(self.path)
        try:
            catalog.validate_catalog_schema(connection)
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM quota_items").fetchone()[0], 8)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM bill_items").fetchone()[0], 8)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM bill_quota_links").fetchone()[0], 8)
        finally:
            connection.close()

    def test_every_discipline_completes_search_and_link_flow(self):
        with self._environment():
            for discipline, (_bill, query, _bill_unit, _quota_unit) in DISCIPLINES.items():
                with self.subTest(discipline=discipline):
                    result = catalog.search_catalog(
                        query,
                        quota_edition="2025",
                        standard_edition="2024",
                        discipline=discipline,
                    )
                    self.assertTrue(result["bills"])
                    self.assertTrue(result["quotas"])
                    self.assertTrue(result["links"])
                    for group in ("bills", "quotas", "links"):
                        self.assertEqual({item["discipline"] for item in result[group]}, {discipline})

    def test_demo_versions_are_hard_isolated(self):
        with self._environment():
            current = catalog.search_catalog(
                "演示基础构件浇筑",
                quota_edition="2025",
                standard_edition="2024",
                discipline="building",
            )
            legacy = catalog.search_catalog(
                "演示基础构件浇筑",
                quota_edition="2016",
                standard_edition="2013",
                discipline="building",
            )
        self.assertEqual({item["edition"] for item in current["quotas"]}, {"2025"})
        self.assertEqual({item["edition"] for item in legacy["quotas"]}, {"2016"})
        self.assertEqual({item["edition"] for item in current["bills"]}, {"2024"})
        self.assertEqual({item["edition"] for item in legacy["bills"]}, {"2013"})

    def test_demo_records_are_visibly_synthetic(self):
        connection = sqlite3.connect(self.path)
        try:
            names = [row[0] for row in connection.execute("SELECT name FROM quota_items UNION ALL SELECT name FROM bill_items")]
            texts = [row[0] for row in connection.execute("SELECT text FROM chunks")]
        finally:
            connection.close()
        self.assertTrue(names)
        self.assertTrue(all("演示" in name for name in names))
        self.assertTrue(any("不对应任何真实定额" in text for text in texts))


if __name__ == "__main__":
    unittest.main()
