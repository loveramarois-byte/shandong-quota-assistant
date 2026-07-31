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
    def test_compact_catalog_keeps_runtime_records_without_fts_shadow_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = build_demo_catalog(root / "source.sqlite")
            output = root / "compact.sqlite"
            result = build_compact_catalog(source, output)

            self.assertTrue(output.is_file())
            self.assertFalse(result["fts5_included"])
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


if __name__ == "__main__":
    unittest.main()
