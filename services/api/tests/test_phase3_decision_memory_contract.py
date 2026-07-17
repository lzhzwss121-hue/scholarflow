from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from scholarflow_api import research_memory as research_memory_module
from scholarflow_api.research_decisions import (
    collect_grounded_gap_evidence,
    generate_research_decisions,
    parse_decision_intent,
)
from scholarflow_api.research_memory import query_research_memory


def make_paper(paper_id: str, title: str, abstract: str) -> dict[str, object]:
    return {
        "id": paper_id,
        "title": title,
        "abstract": abstract,
        "type": "Benchmark",
        "source": "arxiv",
        "venue": "CVPR",
        "url": f"https://arxiv.org/abs/{paper_id}",
        "code": "unknown",
        "priority": "High",
        "relevance_quality": "strong",
    }


def make_anchor_card(paper_id: str, title: str, dataset: str) -> dict[str, object]:
    return {
        "paper_id": paper_id,
        "paper_title": title,
        "evidence_level": "full_text",
        "minimal_reproduction": "\n".join(
            [
                "Claim: the benchmark exposes multi-object hallucination failures.",
                f"Dataset: {dataset}",
                "Metric: accuracy",
                "Baseline: LLaVA-1.5",
            ],
        ),
        "sections_json": "Evaluation uses GPU inference and human annotation.",
        "weakest_assumption": "The benchmark reflects multi-object interactions.",
    }


def make_memory_record(paper_id: str, source: str, evidence_level: str) -> dict[str, object]:
    return {
        "id": f"memory_{paper_id}",
        "paper_id": paper_id,
        "project_id": "project_phase3",
        "direction": "object hallucination",
        "round_index": 1,
        "title": f"Object Hallucination Evidence {paper_id}",
        "authors": "A. Researcher",
        "year": "2026",
        "venue": "CVPR",
        "source": "arxiv",
        "url": f"https://arxiv.org/abs/{paper_id}",
        "keywords_json": json.dumps(["object hallucination", "visual grounding"]),
        "memory_text": "object hallucination evaluation and visual grounding",
        "research_sight_json": json.dumps(
            {
                "evidence_pack": {
                    "evidence_level": evidence_level,
                    "snippets": [
                        {
                            "id": f"snippet_{paper_id}",
                            "source": source,
                            "section": "results" if source == "pdf.full_text" else "abstract",
                            "page": 7 if source == "pdf.full_text" else None,
                            "text": "Object hallucination increases when visual grounding evidence conflicts.",
                            "confidence": "high" if source == "pdf.full_text" else "medium",
                        },
                    ],
                },
            },
        ),
        "self_read_priority": 1,
        "created_at": "now",
    }


class PhaseThreeDecisionMemoryContractTest(unittest.TestCase):
    def test_decision_intent_preserves_constraints_and_time_budget(self) -> None:
        intent = parse_decision_intent(
            "在 7 天内评估 multi-object hallucination，different from POPE，并且不要使用 POPE。",
            "VLM hallucination",
        )

        self.assertEqual(intent.time_budget_days, 7)
        self.assertEqual(intent.contribution_type, "evaluation")
        self.assertIn("multi-object", intent.required_terms)
        self.assertIn("pope", [term.lower() for term in intent.contrast_terms])
        self.assertIn("pope", [term.lower() for term in intent.excluded_terms])

    def test_experiment_anchor_must_match_goal_and_respect_exclusions(self) -> None:
        pope = make_paper("paper_pope", "POPE Object Hallucination Evaluation", "POPE benchmark.")
        multi = make_paper(
            "paper_multi",
            "Multi-Object Hallucination under Conflicting Visual Evidence",
            "A multi-object hallucination evaluation with visual grounding.",
        )
        bundle = generate_research_decisions(
            project={"title": "Goal aligned decision", "keyword": "object hallucination"},
            papers=[pope, multi],
            paper_cards=[
                make_anchor_card("paper_pope", str(pope["title"]), "POPE"),
                make_anchor_card("paper_multi", str(multi["title"]), "HallusionBench"),
            ],
            goal="7 day multi-object hallucination evaluation; do not use POPE",
        )

        self.assertEqual(bundle.experiment.status, "ready")
        self.assertEqual(bundle.experiment.anchor_paper_id, "paper_multi")
        self.assertEqual(bundle.experiment.goal_alignment["status"], "aligned")
        self.assertNotIn("50-100", bundle.experiment.resources)
        self.assertEqual(bundle.experiment.readiness_checks["code_or_api"], "unknown: 未发现可验证代码仓库或 API 权限信息")
        self.assertTrue(bundle.experiment.timeline[0].startswith("Day 1"))

    def test_gap_evidence_uses_the_limitation_quote_and_locator(self) -> None:
        paper = make_paper("paper_grounded", "Grounded Limitation Paper", "A benchmark paper.")
        card = {
            "paper_id": "paper_grounded",
            "signals": {
                "limitation": "本论文自身局限：Our evaluation is limited to single-object scenes.",
                "signal_evidence": {
                    "limitation": {
                        "field": "limitation",
                        "canonical_value": "Our evaluation is limited to single-object scenes.",
                        "raw_value": "Our evaluation is limited to single-object scenes.",
                        "source": "pdf.full_text",
                        "section": "limitations",
                        "page": 11,
                        "quote": "Our evaluation is limited to single-object scenes.",
                        "confidence": "high",
                        "validation_errors": [],
                    },
                },
            },
            "research_sight_json": json.dumps(
                {
                    "evidence_pack": {
                        "snippets": [
                            {
                                "id": "unrelated_result",
                                "source": "pdf.full_text",
                                "section": "results",
                                "page": 7,
                                "text": "Accuracy improves by five points.",
                            },
                        ],
                    },
                },
            ),
        }

        grounded = collect_grounded_gap_evidence([paper], [card])

        self.assertEqual(len(grounded), 1)
        self.assertEqual(grounded[0]["snippet"], "Our evaluation is limited to single-object scenes.")
        self.assertEqual(grounded[0]["section"], "limitations")
        self.assertEqual(grounded[0]["page"], "11")
        self.assertNotIn("Accuracy improves", grounded[0]["snippet"])

    def test_memory_returns_summary_claims_and_unanswered_boundaries(self) -> None:
        records = [
            make_memory_record("paper_full", "pdf.full_text", "full_text"),
            make_memory_record("paper_abstract", "metadata.abstract", "abstract_only"),
        ]
        with patch.object(research_memory_module, "backfill_project_research_memory", return_value=0), patch.object(
            research_memory_module,
            "fetch_memory_records",
            return_value=records,
        ), patch.object(research_memory_module, "fetch_direction_memory_snapshot", return_value=None):
            answer = query_research_memory(
                connection=None,
                project_id="project_phase3",
                question="What evidence explains object hallucination and visual grounding failure?",
                top_k=5,
                now="2026-07-17T00:00:00Z",
            )

        self.assertEqual(answer.reliability_status, "reliable")
        self.assertIn("共同覆盖", answer.answer_summary)
        self.assertEqual(len(answer.claims), 2)
        self.assertEqual(answer.claims[0].evidence_refs[0]["page"], "7")
        self.assertTrue(any("摘要证据" in item for item in answer.unanswered_parts))
        self.assertNotIn("方向级共识。可追溯证据", answer.answer_summary)


if __name__ == "__main__":
    unittest.main()
