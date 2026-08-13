from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scholarflow_api.rag_benchmark import (
    CONSTRUCTED_FIXTURE_DISCLAIMER,
    PROJECT_ID,
    benchmark_cases,
    build_evaluation_report,
    evidence_documents,
    render_evaluation_markdown,
    run_benchmark,
    seed_benchmark,
)
from scholarflow_api.real_paper_evaluation import load_real_paper_dataset


class RagBenchmarkContractTest(unittest.TestCase):
    def test_report_keeps_constructed_real_expert_and_live_sections_separate(self) -> None:
        constructed = {
            "benchmark_version": "evidence_hybrid_rag.v1",
            "case_count": 135,
            "metrics": {"recall_at_5": 1.0},
        }
        report = build_evaluation_report(
            constructed,
            real_dataset_path=Path("evals/real_papers/cases.development.json"),
            real_predictions_path=None,
        )

        self.assertEqual(
            set(report["sections"]),
            {
                "constructed_fixture",
                "development_benchmark",
                "expert_labelled_optional",
                "live_external_smoke",
            },
        )
        self.assertEqual(report["sections"]["constructed_fixture"]["status"], "complete")
        self.assertEqual(
            report["sections"]["development_benchmark"]["status"],
            "blocked_missing_resources",
        )
        self.assertEqual(
            report["sections"]["expert_labelled_optional"]["status"],
            "not_configured",
        )
        self.assertEqual(report["sections"]["live_external_smoke"]["status"], "not_run")
        self.assertFalse(report["sections"]["live_external_smoke"]["fixture_fallback_used"])
        self.assertIn("不得描述为真实论文", CONSTRUCTED_FIXTURE_DISCLAIMER)
        markdown = render_evaluation_markdown(report)
        self.assertIn("constructed_fixture", markdown)
        self.assertIn("development_benchmark", markdown)
        self.assertIn("expert_labelled_optional", markdown)
        self.assertIn("live_external_smoke", markdown)
        self.assertIn("不代表真实科研准确率", markdown)

    def test_repository_real_paper_records_are_valid_but_explicitly_unreviewed(self) -> None:
        dataset = load_real_paper_dataset(
            Path("evals/real_papers/cases.unreviewed.json"),
            allow_unreviewed=True,
        )
        self.assertEqual(dataset.evaluation_tier, "real_paper_unreviewed")
        self.assertTrue(all(case.adjudication_status == "unreviewed" for case in dataset.cases))
        self.assertTrue(
            all(
                case.page and case.section and case.locator.value
                for case in dataset.cases
            )
        )
        self.assertTrue(
            all(
                case.acceptable_citations
                for case in dataset.cases
                if case.answerable
            )
        )

    def test_legacy_unreviewed_dataset_has_explicit_compatibility_status(self) -> None:
        report = build_evaluation_report(
            {"benchmark_version": "test", "case_count": 135, "metrics": {}},
            real_dataset_path=Path("evals/real_papers/cases.unreviewed.json"),
            real_predictions_path=None,
        )
        development = report["sections"]["development_benchmark"]
        self.assertEqual(development["status"], "legacy_compatibility")
        self.assertIn("cases.development.json", development["reason"])

    def test_standard_report_rejects_schema_fixture_predictions(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            predictions_path = Path(tmpdir) / "fixture-predictions.json"
            predictions_path.write_text(
                json.dumps(
                    json.loads(
                        Path(
                            "evals/real_papers/predictions.schema-fixture.json"
                        ).read_text(encoding="utf-8")
                    )
                ),
                encoding="utf-8",
            )
            report = build_evaluation_report(
                {"benchmark_version": "test", "case_count": 0, "metrics": {}},
                real_dataset_path=Path("evals/real_papers/cases.development.json"),
                real_predictions_path=predictions_path,
                real_resources_available=True,
            )
        real_section = report["sections"]["development_benchmark"]
        self.assertEqual(real_section["status"], "blocked_invalid_predictions")
        self.assertEqual(real_section["prediction_source"], "offline_test_fixture")
        self.assertIn("offline_system_run", real_section["reason"])

    def test_empty_expert_dataset_is_optional_and_does_not_block_constructed_results(self) -> None:
        report = build_evaluation_report(
            {"benchmark_version": "test", "case_count": 0, "metrics": {}},
            real_dataset_path=Path("evals/real_papers/cases.development.json"),
            real_predictions_path=None,
            expert_dataset_path=Path("evals/real_papers/cases.expert.json"),
        )
        expert = report["sections"]["expert_labelled_optional"]
        self.assertEqual(expert["status"], "not_configured")
        self.assertEqual(report["sections"]["constructed_fixture"]["status"], "complete")
        self.assertNotIn("0/50", expert["reason"])

    def test_validated_development_predictions_produce_complete_metrics(self) -> None:
        from services.api.tests.test_real_paper_evaluation_contract import (
            correct_predictions,
            dataset_fixture,
        )

        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            root = Path(tmpdir)
            dataset_path = root / "development.json"
            prediction_path = root / "predictions.json"
            dataset_path.write_text(
                json.dumps(dataset_fixture(tier="development_benchmark")),
                encoding="utf-8",
            )
            predictions = correct_predictions()
            predictions["prediction_source"] = "offline_system_run"
            for prediction in predictions["cases"]:
                prediction["source_identity"] = {
                    "paper_id": "paper-a",
                    "doi": "10.0000/test",
                    "arxiv_id": "",
                    "openalex_id": "",
                    "version": "v2",
                    "source_url": "https://example.org/paper-a/v2",
                    "sha256": "a" * 64,
                    "page_count": 8,
                    "resource_identifier": "fixture/paper-a/v2",
                }
                prediction["runtime_metadata"] = {
                    "runner_version": "test-runner",
                    "rag_service": "rag_service.create_project_rag_answer",
                    "database_isolation_id": prediction["case_id"],
                    "ingestion_status": "complete",
                    "retrieval_status": "complete",
                    "answer_status": "complete",
                    "external_data_transfer": False,
                }
            prediction_path.write_text(json.dumps(predictions), encoding="utf-8")
            report = build_evaluation_report(
                {"benchmark_version": "test", "case_count": 135, "metrics": {}},
                real_dataset_path=dataset_path,
                real_predictions_path=prediction_path,
                real_resources_available=True,
            )
        development = report["sections"]["development_benchmark"]
        self.assertEqual(development["status"], "complete")
        self.assertEqual(development["case_count"], 2)
        self.assertEqual(development["metrics"]["citation_precision"], 1.0)
        self.assertIn("不代表真实科研准确率", development["interpretation"])
        wording = development["interpretation"].casefold()
        for forbidden in ("expert accuracy", "human accuracy", "adjudicated accuracy"):
            self.assertNotIn(forbidden, wording)

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
