from __future__ import annotations

import unittest
from unittest.mock import patch

from scholarflow_api.literature import PaperCandidate
from scholarflow_api.rag_live_smoke import run_live_external_smoke


class RagLiveSmokeContractTest(unittest.TestCase):
    def test_live_success_uses_real_record_shape_without_metrics_or_fixture(self) -> None:
        candidate = PaperCandidate(
            title="Live Paper",
            year="2026",
            authors="A. Author",
            abstract="Live abstract",
            type="Method",
            venue="arXiv",
            source="arxiv",
            url="https://arxiv.org/abs/2601.00001",
            pdf_url="https://arxiv.org/pdf/2601.00001.pdf",
            relation="",
            priority="High",
            arxiv_id="2601.00001",
        )
        with patch(
            "scholarflow_api.rag_live_smoke.search_arxiv",
            return_value=[candidate],
        ):
            report = run_live_external_smoke(query="live query")

        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["evaluation_tier"], "live_external_smoke")
        self.assertIsNone(report["metrics"])
        self.assertFalse(report["fixture_fallback_used"])
        self.assertEqual(report["papers"][0]["arxiv_id"], "2601.00001")

    def test_live_failure_remains_blocked_without_fixture_fallback(self) -> None:
        with patch(
            "scholarflow_api.rag_live_smoke.search_arxiv",
            side_effect=TimeoutError("offline"),
        ):
            report = run_live_external_smoke(query="live query")

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["fixture_fallback_used"])
        self.assertEqual(report["papers"], [])
        self.assertIn("no fixture replacement", report["reason"])


if __name__ == "__main__":
    unittest.main()
