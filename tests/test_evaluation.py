from __future__ import annotations

import unittest

from evaluation.run import ROOT, evaluate


class SyntheticEvaluationTests(unittest.TestCase):
    def test_committed_synthetic_baseline_has_no_regressions(self):
        report = evaluate(ROOT / "evaluation" / "datasets" / "synthetic_v1.jsonl")

        self.assertGreaterEqual(report["case_count"], 30)
        self.assertEqual(report["failures"], [])
        self.assertTrue(report["synthetic_only"])


if __name__ == "__main__":
    unittest.main()
