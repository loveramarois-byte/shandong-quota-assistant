from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_demo_catalog import build_demo_catalog
from tools.compact_catalog import build_compact_catalog
from utils.catalog import search_catalog, validate_catalog_schema


class CompactCatalogTests(unittest.TestCase):
    def test_compact_catalog_keeps_only_structured_runtime_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = build_demo_catalog(root / "source.sqlite")
            output = root / "compact.sqlite"
            result = build_compact_catalog(source, output)

            self.assertTrue(output.is_file())
            self.assertFalse(result["fts5_included"])
            self.assertFalse(result["pdf_content_included"])
            self.assertLess(output.stat().st_size, source.stat().st_size)
            connection = sqlite3.connect(output)
            try:
                validate_catalog_schema(connection)
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertNotIn("chunks_fts", tables)
                self.assertNotIn("pages", tables)
                self.assertIn("idx_chunks_scope_title", {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    )
                })
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                    result["counts"]["chunks"],
                )
                self.assertEqual(
                    {
                        row[0]
                        for row in connection.execute(
                            "SELECT DISTINCT chunk_type FROM chunks"
                        )
                    },
                    {"quota_item", "bill_item"},
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM chunks "
                        "WHERE source_path IS NOT NULL OR pdf_page IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
            finally:
                connection.close()

            with patch.dict(os.environ, {"SHANDONG_QUOTA_DB": str(output)}):
                search = search_catalog(
                    "演示基础构件浇筑",
                    quota_edition="2025",
                    standard_edition="2024",
                    discipline="building",
                )
            self.assertTrue(search["quotas"])
            self.assertTrue(search["bills"])
            self.assertIsNone(search["quotas"][0]["source_path"])
            self.assertIsNone(search["quotas"][0]["pdf_page"])


if __name__ == "__main__":
    unittest.main()
