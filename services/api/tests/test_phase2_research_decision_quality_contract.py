from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from scholarflow_api import research_memory as research_memory_module
from scholarflow_api.baseline_map import build_baseline_map
from scholarflow_api.research_decisions import (
    build_gap_decisions,
    gap_group_consistency_score,
    group_grounded_gap_evidence,
)
from scholarflow_api.research_memory import query_research_memory


def memory_record(paper_id: str, text: str, *, source: str = "pdf.full_text") -> dict[str, object]:
    return {
        "id": f"memory_{paper_id}",
        "project_id": "project_phase2",
        "paper_id": paper_id,
        "direction": "object hallucination",
        "round_index": 1,
        "title": f"Paper {paper_id}",
        "authors": "A. Researcher",
        "year": "2026",
        "venue": "CVPR",
        "source": "arxiv",
        "url": "",
        "abstract_translation": "",
        "sections_json": "[]",
        "weakest_assumption": "",
        "minimal_reproduction": "",
        "counterexample": "",
        "follow_up_idea": "",
        "why_selected": "",
        "memory_text": text,
        "keywords_json": json.dumps(["object hallucination", "visual grounding"]),
        "self_read_priority": 0,
        "created_at": "2026-07-20T00:00:00Z",
        "research_sight_json": json.dumps(
            {
                "evidence_pack": {
                    "evidence_level": "full_text" if source == "pdf.full_text" else "abstract_only",
                    "snippets": [
                        {
                            "id": f"snippet_{paper_id}",
                            "source": source,
                            "section": "results",
                            "page": 7,
                            "text": text,
                            "confidence": "high",
                        },
                    ],
                },
            },
        ),
    }


class Phase2ResearchDecisionQualityContractTest(unittest.TestCase):
    def test_memory_reports_partial_question_coverage_instead_of_implying_full_answer(self) -> None:
        record = memory_record(
            "partial",
            "Object hallucination is associated with weak visual grounding in multi-object scenes.",
        )
        with patch.object(research_memory_module, "backfill_project_research_memory", return_value=0), patch.object(
            research_memory_module,
            "fetch_memory_records",
            return_value=[record],
        ), patch.object(research_memory_module, "fetch_direction_memory_snapshot", return_value=None):
            answer = query_research_memory(
                connection=None,
                project_id="project_phase2",
                question=(
                    "Why does object hallucination increase under visual grounding conflict, "
                    "and which dataset metric baseline should verify the causal mechanism?"
                ),
                top_k=5,
                now="2026-07-20T00:00:00Z",
            )

        self.assertEqual(answer.reliability_status, "reliable")
        self.assertGreater(answer.query_coverage["coverage"], 0)
        self.assertLess(answer.query_coverage["coverage"], 1)
        self.assertTrue(answer.query_coverage["missing_terms"])
        self.assertTrue(any("回答只覆盖问题的一部分" in warning for warning in answer.warnings))
        self.assertTrue(any("原文证据尚未覆盖" in item for item in answer.unanswered_parts))
        self.assertGreater(answer.hits[0].query_coverage, 0)
        self.assertTrue(answer.hits[0].matched_query_terms)

    def test_gap_classification_requires_semantically_related_independent_evidence(self) -> None:
        unrelated = [
            {
                "paper_id": "paper_a",
                "title": "Single Object Evaluation",
                "snippet_id": "a",
                "source": "pdf.full_text",
                "snippet": "Object hallucination evaluation is limited to single-object scenes.",
                "limitation": "object hallucination evaluation is limited to single-object scenes",
                "section": "limitations",
                "page": "9",
                "evidence_level": "full_text",
                "verified_full_text": True,
            },
            {
                "paper_id": "paper_b",
                "title": "Language Coverage Study",
                "snippet_id": "b",
                "source": "pdf.full_text",
                "snippet": "The object hallucination benchmark only covers English prompts.",
                "limitation": "object hallucination benchmark only covers English prompts",
                "section": "limitations",
                "page": "11",
                "evidence_level": "full_text",
                "verified_full_text": True,
            },
        ]
        groups = group_grounded_gap_evidence(unrelated)
        gaps = build_gap_decisions("complete", "Paper A, Paper B", unrelated, groups)

        self.assertEqual(len(groups), 2)
        self.assertFalse(any(gap.kind == "true_gap" for gap in gaps))
        self.assertTrue(all(gap.support_status == "single_source" for gap in gaps))

    def test_abstract_evidence_cannot_upgrade_a_gap_to_corroborated(self) -> None:
        mixed_evidence = [
            {
                "paper_id": "paper_a",
                "title": "Single Object Evaluation A",
                "snippet_id": "a",
                "source": "pdf.full_text",
                "snippet": "Our evaluation is limited to single-object scenes.",
                "limitation": "limited to single-object scenes",
                "section": "limitations",
                "page": "9",
                "evidence_level": "full_text",
            },
            {
                "paper_id": "paper_b",
                "title": "Single Object Evaluation B",
                "snippet_id": "b",
                "source": "metadata.abstract",
                "snippet": "The benchmark covers only single-object scenes.",
                "limitation": "covers only single-object scenes",
                "section": "abstract",
                "page": "",
                "evidence_level": "abstract_only",
            },
        ]
        groups = group_grounded_gap_evidence(mixed_evidence)
        gaps = build_gap_decisions("complete", "Paper A, Paper B", mixed_evidence, groups)
        gap = gaps[0]

        self.assertEqual(len(groups), 1)
        self.assertNotEqual(gap.kind, "true_gap")
        self.assertNotEqual(gap.support_status, "corroborated")

    def test_gap_classification_requires_two_consistent_full_text_sources(self) -> None:
        corroborated = [
            {
                "paper_id": "paper_a",
                "title": "Single Object Evaluation A",
                "snippet_id": "a",
                "source": "pdf.full_text",
                "snippet": "Our evaluation is limited to single-object scenes.",
                "limitation": "limited to single-object scenes",
                "section": "limitations",
                "page": "9",
                "evidence_level": "full_text",
                "verified_full_text": True,
            },
            {
                "paper_id": "paper_b",
                "title": "Single Object Evaluation B",
                "snippet_id": "b",
                "source": "pdf.full_text",
                "snippet": "The benchmark covers only single-object scenes.",
                "limitation": "covers only single-object scenes",
                "section": "limitations",
                "page": "11",
                "evidence_level": "full_text",
                "verified_full_text": True,
            },
        ]
        groups = group_grounded_gap_evidence(corroborated)
        gaps = build_gap_decisions("complete", "Paper A, Paper B", corroborated, groups)
        gap = gaps[0]

        self.assertEqual(len(groups), 1)
        self.assertGreaterEqual(gap_group_consistency_score(groups[0]), 0.70)
        self.assertEqual(gap.kind, "true_gap")
        self.assertEqual(gap.support_status, "corroborated")
        self.assertEqual(gap.confidence, "medium")
        self.assertEqual(gap.paper_ids, ["paper_a", "paper_b"])
        self.assertEqual(len(gap.evidence_refs), 2)
        self.assertTrue(gap.validation_requirements)

    def test_complete_link_does_not_chain_incompatible_failure_modes(self) -> None:
        evidence = [
            {
                "paper_id": "paper_a",
                "title": "Single Object A",
                "source": "pdf.full_text",
                "snippet": "Evaluation is limited to single-object scenes.",
                "limitation": "limited to single-object scenes",
            },
            {
                "paper_id": "paper_b",
                "title": "Single Object B",
                "source": "pdf.full_text",
                "snippet": "The benchmark only covers single-object scenes.",
                "limitation": "only covers single-object scenes",
            },
            {
                "paper_id": "paper_c",
                "title": "English Coverage",
                "source": "pdf.full_text",
                "snippet": "The benchmark only supports English prompts.",
                "limitation": "only supports English prompts",
            },
        ]

        groups = group_grounded_gap_evidence(evidence)

        self.assertEqual(sorted(len(group) for group in groups), [1, 2])

    def test_baseline_map_exposes_actionability_and_does_not_promote_age_alone(self) -> None:
        verified_text = (
            "[PDF page 4]\n[Section: method]\nWe propose a decoding intervention.\n"
            "[PDF page 8]\n[Section: experiments]\nWe use COCO, CHAIR, and LLaVA.\n"
            + "Supporting implementation context " * 80
        )
        qualification = {
            "level": "full_text",
            "verified": True,
            "source_origin": "arxiv_pdf",
            "character_count": len(verified_text),
            "page_count": 8,
            "section_names": ["method", "experiments"],
            "reason": "Test fixture models a successfully parsed PDF.",
        }
        selected = [
            {
                "title": "Traceable Hallucination Baseline",
                "abstract": "We propose a method evaluated on COCO with CHAIR against LLaVA.",
                "year": "2026",
                "venue": "CVPR",
                "source": "arxiv",
                "url": "https://arxiv.org/abs/traceable",
                "code": "https://github.com/example/traceable",
                "full_text": verified_text,
                "evidence_qualification": qualification,
                "full_text_provenance": {
                    "status": "extracted",
                    "source": "arxiv_pdf",
                    "character_count": len(verified_text),
                    "page_count": 8,
                },
                "paper_signals": {
                    "method": "We propose a decoding intervention.",
                    "dataset": "COCO",
                    "metric": "CHAIR",
                    "baseline": "LLaVA",
                },
            },
            {
                "title": "Old Topic Paper",
                "abstract": "A related hallucination paper.",
                "year": "2022",
                "venue": "arXiv",
                "source": "arxiv",
                "url": "https://arxiv.org/abs/old",
                "paper_signals": {},
            },
        ]

        baseline_map = build_baseline_map("object hallucination evaluation", [], selected)
        ready = baseline_map.recent_strong_baselines[0]

        self.assertEqual(baseline_map.classic_baselines, [])
        self.assertEqual(ready.actionability_status, "ready")
        self.assertEqual(ready.experiment_anchor["dataset"], "COCO")
        self.assertEqual(ready.experiment_anchor["metric"], "CHAIR")
        self.assertIn("ready", " ".join(baseline_map.action_plan))
        self.assertIn("COCO", baseline_map.common_benchmarks)
        self.assertIn("CHAIR", baseline_map.common_benchmarks)
        self.assertNotIn("task-specific benchmark", baseline_map.common_benchmarks)


if __name__ == "__main__":
    unittest.main()
