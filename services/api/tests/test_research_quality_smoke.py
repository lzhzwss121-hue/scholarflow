from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scholarflow_api import literature
from scholarflow_api.baseline_map import build_baseline_map
from scholarflow_api.direction_review import (
    build_direction_review_bundle,
    build_direction_scope,
    render_direction_review_markdown,
)
from scholarflow_api.research_decisions import generate_research_decisions
from scholarflow_api.research_memory import score_memory_record
from scholarflow_api.text_utils import extract_terms


class ResearchQualitySmokeTest(unittest.TestCase):
    def test_literature_low_recall_relaxes_query_and_degrades_openalex(self) -> None:
        calls: list[tuple[str, bool]] = []

        def fake_arxiv(query: str, max_results: int, relaxed: bool = False) -> list[literature.PaperCandidate]:
            calls.append((query, relaxed))
            if not relaxed:
                return []
            return [
                literature.PaperCandidate(
                    title=f"Image Restoration Smoke Candidate {index}",
                    year="2025",
                    authors="A. Researcher",
                    abstract="A benchmark paper for image restoration metrics and datasets.",
                    type="Benchmark",
                    venue="arXiv cs.CV",
                    source="arxiv",
                    url=f"https://arxiv.org/abs/smoke{index}",
                    relation="",
                    priority="Medium",
                    relevance_score=0.1,
                )
                for index in range(3)
            ]

        def fake_openalex(query: str, max_results: int) -> list[literature.PaperCandidate]:
            raise literature.SourceDegradedError("openalex", query, 503, "temporary unavailable")

        with patch.object(literature, "search_arxiv", side_effect=fake_arxiv), patch.object(
            literature,
            "search_openalex",
            side_effect=fake_openalex,
        ):
            result = literature.search_literature("图像修复", max_results=8, sources=["arxiv", "openalex"])

        self.assertEqual(len(result.papers), 3)
        self.assertTrue(any(relaxed for _query, relaxed in calls))
        self.assertTrue(any("openalex" in warning and "503" in warning for warning in result.errors))
        self.assertTrue(any("low_recall" in warning for warning in result.errors))
        self.assertTrue(any("query_relaxed" in warning for warning in result.errors))

    def test_request_text_uses_in_memory_cache(self) -> None:
        literature.REQUEST_CACHE.clear()
        url = "https://example.test/search?q=cache-smoke"
        calls = {"count": 0}

        class FakeResponse:
            def __enter__(self):
                calls["count"] += 1
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b"cached payload"

        with patch.object(literature.urllib.request, "urlopen", return_value=FakeResponse()):
            first = literature.request_text(url)
            second = literature.request_text(url)

        self.assertEqual(first, "cached payload")
        self.assertEqual(second, "cached payload")
        self.assertEqual(calls["count"], 1)

    def test_retrieval_errors_are_compacted_without_losing_low_recall_signal(self) -> None:
        compacted = literature.compact_retrieval_errors(
            [
                "openalex:query one: degraded status=503: HTTP Error 503: Service Unavailable",
                "openalex:query two: degraded status=503: HTTP Error 503: Service Unavailable",
                "openalex:query three: degraded status=503: HTTP Error 503: Service Unavailable",
                "query_relaxed:short query: 初始检索召回不足，已自动放宽检索式。",
                "query_relaxed:shorter: 初始检索召回不足，已自动放宽检索式。",
                "low_recall: only 0 papers returned after query expansion and relaxation; results are partial.",
            ],
        )

        joined = "\n".join(compacted)
        self.assertIn("openalex_summary", joined)
        self.assertIn("3 retrieval warnings", joined)
        self.assertIn("query_relaxed_summary", joined)
        self.assertIn("low_recall", joined)
        self.assertLess(len(compacted), 6)

    def test_direction_review_marks_less_than_five_as_partial(self) -> None:
        baseline_map = build_baseline_map("图像修复", [], [])
        bundle = build_direction_review_bundle(
            direction="图像修复",
            round_index=1,
            scope=build_direction_scope("图像修复", 1),
            baseline_map=baseline_map,
            readings=[],
            previous_read_count=0,
            errors=[],
        )
        markdown = render_direction_review_markdown(bundle)

        self.assertEqual(bundle.review_status, "partial")
        self.assertEqual(bundle.target_paper_count, 10)
        self.assertTrue(any("partial_direction_review" in warning for warning in bundle.errors))
        self.assertIn("Partial Direction Review", markdown)
        self.assertIn("Coverage: 0/10", markdown)

    def test_memory_scoring_routes_experiment_baseline_and_counterexample_to_fields(self) -> None:
        question = "What one week experiment baseline and counterexample should I run?"
        terms = set(extract_terms(question, limit=16))
        record = {
            "title": "Faithful Visual Question Answering Requires Grounded Evidence",
            "keywords_json": json.dumps(["faithfulness", "visual grounding"]),
            "memory_text": "The paper studies evidence faithfulness and visual grounding.",
            "minimal_reproduction": "Dataset: VQA-v2. Metric: counterexample pass rate. Baseline: LLaVA.",
            "counterexample": "Replace grounded visual evidence with a conflicting object attribute.",
            "weakest_assumption": "The evidence retriever is assumed to be faithful.",
            "research_sight_json": json.dumps(
                {
                    "baseline_comparison": "Compare against LLaVA and a no-grounding baseline.",
                    "why_not_good": "The benchmark may miss counterexample failures.",
                    "better_angle": "Use counterexample evaluation.",
                    "next_step_proposal": "Run a minimal experiment on VQA-v2.",
                },
            ),
            "sections_json": "Experiment design includes dataset, metric, baseline, and ablation.",
            "self_read_priority": 1,
        }
        score = score_memory_record(record, terms, question)

        self.assertGreater(score.section_score, 0)
        self.assertGreater(score.total, score.priority_score)

        priority_only_record = {
            "title": "Unrelated Survey",
            "keywords_json": "[]",
            "memory_text": "unrelated background note",
            "self_read_priority": 1,
        }
        priority_only_score = score_memory_record(priority_only_record, terms, question)
        self.assertEqual(priority_only_score.priority_score, 0)
        self.assertEqual(priority_only_score.total, 0)

    def test_experiment_blocked_includes_unblock_suggestions(self) -> None:
        bundle = generate_research_decisions(
            project={"title": "Blocked Smoke", "keyword": "trustworthy VLM"},
            papers=[
                {
                    "id": "paper_method",
                    "title": "A Method Paper for Trustworthy VLM Evaluation",
                    "type": "Method",
                    "source": "arxiv",
                    "venue": "arXiv cs.CV",
                    "url": "https://arxiv.org/abs/2601.00001",
                    "abstract": "A method paper with benchmark discussion.",
                    "priority": "High",
                },
            ],
            paper_cards=[
                {
                    "paper_id": "paper_method",
                    "paper_title": "A Method Paper for Trustworthy VLM Evaluation",
                    "minimal_reproduction": "Claim: the method reduces hallucination.",
                    "sections_json": "The paper mentions benchmark evaluation but omits concrete fields.",
                    "weakest_assumption": "The benchmark exposes real failures.",
                },
            ],
            goal="build a one-week experiment",
        )

        self.assertEqual(bundle.experiment.status, "blocked")
        suggestions = " ".join(bundle.experiment.unblock_suggestions).lower()
        self.assertIn("dataset", suggestions)
        self.assertIn("baseline", suggestions)
        self.assertIn("metric", suggestions)

    def test_manual_or_seed_paper_card_cannot_unlock_experiment_plan(self) -> None:
        manual_bundle = generate_research_decisions(
            project={"title": "Manual Card", "keyword": "trustworthy VLM"},
            papers=[],
            paper_cards=[
                {
                    "paper_title": "Manual fallback paper",
                    "minimal_reproduction": "Claim: reduces hallucination. Dataset: POPE. Metric: accuracy. Baseline: LLaVA.",
                    "sections_json": "Dataset: POPE. Metric: accuracy. Baseline: LLaVA.",
                    "weakest_assumption": "Manual note is not linked to a real retrieved paper.",
                },
            ],
            goal="build a one-week experiment",
        )

        self.assertEqual(manual_bundle.experiment.status, "blocked")
        self.assertIn("真实检索论文", " ".join(manual_bundle.experiment.unblock_suggestions))

        seed_bundle = generate_research_decisions(
            project={"title": "Seed Card", "keyword": "trustworthy VLM"},
            papers=[
                {
                    "id": "paper_seed",
                    "title": "Synthetic Example: Selecting Reproducible Experiment Anchors",
                    "type": "Guide",
                    "source": "seed",
                    "venue": "Demo",
                    "code": "demo",
                    "url": "",
                    "abstract": "Dataset: POPE. Metric: accuracy. Baseline: LLaVA.",
                    "priority": "High",
                },
            ],
            paper_cards=[
                {
                    "paper_id": "paper_seed",
                    "paper_title": "Synthetic Example: Selecting Reproducible Experiment Anchors",
                    "minimal_reproduction": "Claim: reduces hallucination. Dataset: POPE. Metric: accuracy. Baseline: LLaVA.",
                    "sections_json": "Dataset: POPE. Metric: accuracy. Baseline: LLaVA.",
                },
            ],
            goal="build a one-week experiment",
        )

        self.assertEqual(seed_bundle.experiment.status, "blocked")

    def test_new_user_project_starts_with_empty_paper_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api.main import create_project, list_project_papers
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import ProjectCreate

                init_db()
                project = create_project(
                    ProjectCreate(
                        title="No Seed User Project",
                        keyword="vision language model hallucination",
                    ),
                )
                papers = list_project_papers(project.id)

        self.assertEqual(papers, [])


if __name__ == "__main__":
    unittest.main()
