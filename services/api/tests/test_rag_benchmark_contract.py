from __future__ import annotations

import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from scholarflow_api.rag_benchmark import (
    PROJECT_ID,
    benchmark_cases,
    evidence_documents,
    run_benchmark,
    seed_benchmark,
)


class RagBenchmarkContractTest(unittest.TestCase):
    def test_fixed_offline_benchmark_has_required_scope_and_traps(self) -> None:
        cases = benchmark_cases()
        answerable = [case for case in cases if not case.should_refuse]
        refusal = [case for case in cases if case.should_refuse]

        self.assertGreaterEqual(len(answerable), 100)
        self.assertGreaterEqual(len(refusal), 30)
        self.assertGreaterEqual(len({case.direction for case in cases}), 3)
        self.assertTrue(any("是什么" in case.query for case in answerable))
        self.assertTrue(any("What" in case.query for case in answerable))

        traps = " ".join(
            document.adversarial_claim.lower()
            for document in evidence_documents()
        )
        for marker in (
            "does not",
            "higher",
            "lower",
            "causes",
            "unconditionally",
            "every coverage",
        ):
            self.assertIn(marker, traps)

    def test_offline_benchmark_meets_evidence_rag_acceptance_thresholds(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            db_path = Path(tmpdir) / "rag-eval.sqlite3"
            with patch.dict(
                os.environ,
                {
                    "SCHOLARFLOW_DB_PATH": str(db_path),
                    "SCHOLARFLOW_RAG_EMBEDDING_PROVIDER": "local",
                },
            ):
                from scholarflow_api.database import get_connection, init_db

                init_db()
                with get_connection() as connection:
                    seed_benchmark(connection)
                    result = run_benchmark(connection)

        metrics = result["metrics"]
        self.assertEqual(result["case_count"], 135)
        self.assertEqual(result["answerable_count"], 105)
        self.assertEqual(result["refusal_count"], 30)
        self.assertGreaterEqual(metrics["recall_at_5"], 0.85)
        self.assertGreaterEqual(metrics["citation_precision"], 0.95)
        self.assertEqual(metrics["citation_locatability"], 1.0)
        self.assertEqual(metrics["full_text_false_positive_rate"], 0.0)
        self.assertGreaterEqual(metrics["refusal_recall"], 0.90)
        self.assertLess(metrics["contradiction_escape_rate"], 0.05)

    def test_fts_provenance_gate_dedup_and_counterevidence_are_observable(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            db_path = Path(tmpdir) / "rag-contract.sqlite3"
            with patch.dict(
                os.environ,
                {"SCHOLARFLOW_DB_PATH": str(db_path)},
            ):
                from scholarflow_api.database import get_connection, init_db, utc_now
                from scholarflow_api.rag_index import replace_paper_chunks
                from scholarflow_api.rag_retrieval import retrieve_project_chunks
                from scholarflow_api.research_memory import query_research_memory

                init_db()
                with get_connection() as connection:
                    seed_benchmark(connection)
                    retrieval = retrieve_project_chunks(
                        connection,
                        project_id=PROJECT_ID,
                        query="HalluGuard object hallucination rate on POPE",
                        top_k=5,
                        refresh_embeddings=False,
                    )
                    self.assertLess(
                        retrieval["fts_candidate_chunks"],
                        retrieval["candidate_chunks"],
                    )
                    self.assertEqual(
                        [hit["paper_id"] for hit in retrieval["hits"]],
                        ["paper-halluguard"],
                    )
                    hit = retrieval["hits"][0]
                    self.assertTrue(hit["evidence_verified"])
                    self.assertTrue(hit["arxiv_id"])
                    self.assertEqual(hit["parser_version"], "offline_pdf_fixture.v1")
                    self.assertNotEqual(hit["section"], "unknown")
                    self.assertIsNotNone(hit["page_start"])
                    self.assertNotIn(
                        "paper-user-paste",
                        [item["paper_id"] for item in retrieval["hits"]],
                    )

                    now = utc_now()
                    original = connection.execute(
                        "SELECT * FROM papers WHERE id = 'paper-halluguard'"
                    ).fetchone()
                    connection.execute(
                        """
                        INSERT INTO papers (
                            id, project_id, title, authors, abstract, year, type,
                            venue, source, url, pdf_url, relation, priority, code,
                            relevance_score, relevance_quality, matched_terms_json,
                            review_required, created_at, canonical_work_id
                        )
                        VALUES (
                            'paper-halluguard-openalex', ?, ?, '', '', '2026',
                            'Journal', 'Offline', 'openalex', '', '', '', 'High',
                            '', 1.0, 'strong', '[]', 0, ?, ?
                        )
                        """,
                        (
                            PROJECT_ID,
                            original["title"],
                            now,
                            original["canonical_work_id"],
                        ),
                    )
                    replace_paper_chunks(
                        connection,
                        project_id=PROJECT_ID,
                        paper_id="paper-halluguard-openalex",
                        text=(
                            "[PDF page 3]\n[Section: results]\n"
                            "HalluGuard reduces object hallucination rate on POPE by 10%."
                        ),
                        source="pdf.full_text",
                        source_origin="publisher_pdf",
                        evidence_level="full_text",
                        evidence_verified=True,
                        parser_version="pypdf.v1",
                        now=now,
                    )
                    merged = retrieve_project_chunks(
                        connection,
                        project_id=PROJECT_ID,
                        query="HalluGuard object hallucination rate on POPE",
                        top_k=5,
                        refresh_embeddings=False,
                    )
                    self.assertEqual(len(merged["hits"]), 1)
                    self.assertTrue(merged["hits"][0]["duplicate_paper_ids"])

                    counter = retrieve_project_chunks(
                        connection,
                        project_id=PROJECT_ID,
                        query="VisionFence reduces hallucination rate on CHAIR.",
                        top_k=5,
                        refresh_embeddings=False,
                    )
                    self.assertEqual(counter["hits"][0]["stance"], "counterevidence")
                    self.assertGreaterEqual(counter["counterevidence_hits"], 1)

                    memory = query_research_memory(
                        connection,
                        PROJECT_ID,
                        "HalluGuard object hallucination rate on POPE",
                        5,
                        now,
                    )
                    self.assertEqual(memory.reliability_status, "reliable")
                    self.assertTrue(memory.source_chunks)
                    self.assertTrue(
                        all(
                            claim.evidence_refs[0]["snippet_id"]
                            for claim in memory.claims
                        )
                    )

    def test_preprint_and_formal_records_merge_by_persistent_identity(self) -> None:
        from scholarflow_api.literature import PaperCandidate, rank_and_deduplicate

        common = {
            "year": "2026",
            "authors": "A. Researcher",
            "abstract": "HalluGuard reduces object hallucination on POPE.",
            "type": "Method",
            "venue": "CVPR",
            "relation": "",
            "priority": "High",
        }
        preprint = PaperCandidate(
            title="HalluGuard for Object Hallucination",
            source="arxiv",
            url="https://arxiv.org/abs/2607.12345",
            pdf_url="https://arxiv.org/pdf/2607.12345.pdf",
            arxiv_id="2607.12345",
            **common,
        )
        formal = PaperCandidate(
            title="HalluGuard for Object Hallucination: Conference Version",
            source="openalex",
            url="https://doi.org/10.1000/halluguard",
            pdf_url="",
            doi="10.1000/halluguard",
            arxiv_id="2607.12345",
            openalex_id="W123456789",
            **common,
        )

        merged = rank_and_deduplicate(
            [preprint, formal],
            "object hallucination HalluGuard POPE",
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].arxiv_id, "2607.12345")
        self.assertEqual(merged[0].doi, "10.1000/halluguard")
        self.assertEqual(merged[0].openalex_id, "W123456789")


if __name__ == "__main__":
    unittest.main()
