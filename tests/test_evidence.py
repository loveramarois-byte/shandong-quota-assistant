from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils.ai_validate import validate_ai_answer
from utils.evidence import hydrate_result_sources, open_source_page, reference_evidence, resolve_source_path


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.pdf = self.root / "原书.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        self.database = self.root / "catalog.sqlite"
        connection = sqlite3.connect(self.database)
        connection.execute(
            "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, source_path TEXT, pdf_page INTEGER)"
        )
        connection.execute(
            "INSERT INTO chunks VALUES (?,?,?)",
            ("quota:fixture:1", str(self.pdf), 42),
        )
        connection.commit()
        connection.close()

    def _result(self) -> dict:
        return {
            "quota_edition": "2025",
            "standard_edition": "2024",
            "discipline": "building",
            "bills": [],
            "quotas": [{
                "record_id": "quota:fixture:1",
                "reference": "R1",
                "code": "2-1-28",
                "title": "混凝土垫层",
                "unit": "10m3",
                "edition": "2025",
                "discipline": "building",
            }],
            "links": [],
            "guidance": [],
        }

    def test_hydrates_path_and_page_by_stable_record_id(self):
        hydrated = hydrate_result_sources(self._result(), catalog_path=self.database)

        item = hydrated["quotas"][0]
        self.assertEqual(item["source_path"], str(self.pdf))
        self.assertEqual(item["pdf_page"], 42)

    def test_reference_status_distinguishes_located_and_missing_file(self):
        located = reference_evidence("R1", {"source_path": str(self.pdf), "pdf_page": 42}, catalog_path=self.database)
        missing = reference_evidence("R2", {"source_path": str(self.root / "missing.pdf"), "pdf_page": 7}, catalog_path=self.database)

        self.assertEqual(located["status"], "located")
        self.assertEqual(missing["status"], "file_missing")

    def test_validation_reports_partial_evidence_per_reference(self):
        result = self._result()
        result["quotas"][0].update({"source_path": str(self.pdf), "pdf_page": 42})
        result["bills"] = [{
            "record_id": "bill:fixture:2",
            "reference": "R2",
            "code": "010501001-000",
            "title": "基础垫层",
            "unit": "m3",
            "edition": "2024",
            "discipline": "building",
        }]

        validation = validate_ai_answer("依据 [R1] [R2]", result)

        self.assertEqual(validation["evidence_status"], "partial")
        self.assertEqual(validation["evidence_located"], 1)
        self.assertEqual(validation["evidence_total"], 2)
        self.assertEqual(validation["unlocated_references"][0]["reference"], "R2")

    def test_open_source_uses_pdf_page_fragment(self):
        with mock.patch("utils.evidence.os.startfile") as startfile:
            opened = open_source_page(self.pdf, 42)

        self.assertTrue(opened)
        self.assertTrue(startfile.call_args.args[0].endswith("#page=42"))

    def test_resolve_source_returns_none_for_uninstalled_file(self):
        self.assertIsNone(resolve_source_path(self.root / "missing.pdf", catalog_path=self.database))

    def test_non_pdf_and_network_sources_are_rejected(self):
        executable = self.root / "source.exe"
        executable.write_bytes(b"fixture")

        self.assertIsNone(resolve_source_path(executable, catalog_path=self.database))
        self.assertIsNone(resolve_source_path(r"\\HOST\share\source.pdf", catalog_path=self.database))


if __name__ == "__main__":
    unittest.main()
