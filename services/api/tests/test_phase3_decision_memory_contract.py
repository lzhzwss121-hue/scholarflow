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

    def test_complex_chinese_goal_keeps_research_constraints_without_action_fragments(self) -> None:
        intent = parse_decision_intent(
            (
                "在 7 天内设计一个区别于 POPE 的 multi-object hallucination 证据忠实性评估；"
                "明确不要使用 POPE，并给出可复现数据集、指标、baseline 与失败判据。"
            ),
            "VLM hallucination",
        )

        self.assertEqual(intent.time_budget_days, 7)
        self.assertEqual(intent.contribution_type, "evaluation")
        self.assertEqual([term.lower() for term in intent.contrast_terms], ["pope"])
        self.assertEqual([term.lower() for term in intent.excluded_terms], ["pope"])
        self.assertTrue({"multi-object", "证据忠实性", "数据集", "指标", "baseline", "失败判据"}.issubset(intent.required_terms))
        self.assertFalse(any("使用" in term or "天内" in term or "给出" in term for term in intent.required_terms))

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

    def test_experiment_is_blocked_when_explicit_hard_constraints_are_missing(self) -> None:
        paper = make_paper(
            "paper_partial_anchor",
            "DAMRO Object Hallucination Evaluation",
            "A method for object hallucination evaluation with GPU inference.",
        )
        bundle = generate_research_decisions(
            project={"title": "Hard constraint decision", "keyword": "object hallucination"},
            papers=[paper],
            paper_cards=[make_anchor_card("paper_partial_anchor", str(paper["title"]), "POPE")],
            goal=(
                "在 7 天内设计一个可在单张 24GB GPU 上完成的实验，"
                "比较 attention-grounding 根因假设与 language-prior 根因假设；"
                "必须包含 POPE 或 CHAIR、强 baseline、失败样本切片和证据忠实性指标。"
            ),
        )

        self.assertEqual(bundle.experiment.status, "blocked")
        self.assertEqual(bundle.experiment.anchor_paper_id, "paper_partial_anchor")
        self.assertEqual(bundle.experiment.goal_alignment["status"], "mismatch")
        self.assertIn("24GB", bundle.experiment.goal_alignment["missing_hard_constraints"])
        self.assertIn("single GPU", bundle.experiment.goal_alignment["missing_hard_constraints"])
        self.assertIn("attention-grounding", bundle.experiment.goal_alignment["missing_hard_constraints"])
        self.assertIn("language-prior", bundle.experiment.goal_alignment["missing_hard_constraints"])
        self.assertIn("failure sample slices", bundle.experiment.goal_alignment["missing_hard_constraints"])
        self.assertIn("evidence faithfulness metric", bundle.experiment.goal_alignment["missing_hard_constraints"])
        self.assertEqual(bundle.experiment.goal_alignment["hard_constraint_checks"]["POPE / CHAIR"], "ready")
        self.assertEqual(bundle.experiment.goal_alignment["hard_constraint_checks"]["strong baseline"], "ready")
        self.assertTrue(bundle.experiment.readiness_checks["goal_constraints"].startswith("blocked:"))
        self.assertEqual(bundle.decision_status, "partial")

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

    def test_memory_prefers_relevant_pdf_reference_over_earlier_abstract_reference(self) -> None:
        record = make_memory_record("paper_mixed", "metadata.abstract", "full_text")
        sight = json.loads(str(record["research_sight_json"]))
        sight["evidence_pack"]["snippets"].append(
            {
                "id": "pdf_mechanism",
                "source": "pdf.full_text",
                "section": "results",
                "page": 9,
                "text": (
                    "Object hallucination increases because conflicting visual grounding evidence "
                    "causes incorrect attribute binding."
                ),
                "confidence": "high",
            },
        )
        record["research_sight_json"] = json.dumps(sight)

        with patch.object(research_memory_module, "backfill_project_research_memory", return_value=0), patch.object(
            research_memory_module,
            "fetch_memory_records",
            return_value=[record],
        ), patch.object(research_memory_module, "fetch_direction_memory_snapshot", return_value=None):
            answer = query_research_memory(
                connection=None,
                project_id="project_phase3",
                question="Why does object hallucination increase when visual grounding evidence conflicts?",
                top_k=5,
                now="2026-07-17T00:00:00Z",
            )

        reference = answer.claims[0].evidence_refs[0]
        self.assertEqual(reference["source"], "pdf.full_text")
        self.assertEqual(reference["page"], "9")
        self.assertIn("1 条回答证据直接来自 PDF 全文", answer.answer_summary)
        self.assertFalse(any("摘要证据" in item for item in answer.unanswered_parts))

    def test_memory_query_safely_falls_back_to_the_only_saved_direction(self) -> None:
        record = make_memory_record("paper_only_direction", "pdf.full_text", "full_text")
        with patch.object(research_memory_module, "backfill_project_research_memory", return_value=0), patch.object(
            research_memory_module,
            "fetch_memory_records",
            side_effect=[[], [record]],
        ) as fetch_records, patch.object(
            research_memory_module,
            "fetch_direction_memory_snapshot",
            return_value=None,
        ) as fetch_snapshot:
            answer = query_research_memory(
                connection=None,
                project_id="project_phase3",
                question="What evidence explains object hallucination under visual grounding conflict?",
                top_k=5,
                now="2026-07-17T00:00:00Z",
                direction="stale project keyword",
            )

        self.assertEqual(answer.total_memories, 1)
        self.assertEqual(answer.reliability_status, "reliable")
        self.assertTrue(any("已安全回退到 `object hallucination`" in warning for warning in answer.warnings))
        self.assertEqual(fetch_records.call_count, 2)
        fetch_snapshot.assert_called_once_with(None, "project_phase3", "object hallucination")

    def test_memory_query_does_not_merge_multiple_directions_on_stale_filter(self) -> None:
        first = make_memory_record("paper_direction_a", "pdf.full_text", "full_text")
        second = make_memory_record("paper_direction_b", "pdf.full_text", "full_text")
        second["direction"] = "medical hallucination"
        with patch.object(research_memory_module, "backfill_project_research_memory", return_value=0), patch.object(
            research_memory_module,
            "fetch_memory_records",
            side_effect=[[], [first, second]],
        ), patch.object(
            research_memory_module,
            "fetch_direction_memory_snapshot",
            return_value=None,
        ):
            answer = query_research_memory(
                connection=None,
                project_id="project_phase3",
                question="What evidence explains object hallucination?",
                top_k=5,
                now="2026-07-17T00:00:00Z",
                direction="stale project keyword",
            )

        self.assertEqual(answer.total_memories, 0)
        self.assertEqual(answer.reliability_status, "no_memory")
        self.assertFalse(any("已安全回退" in warning for warning in answer.warnings))


if __name__ == "__main__":
    unittest.main()
