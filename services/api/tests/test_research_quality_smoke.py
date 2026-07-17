from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scholarflow_api import literature
from scholarflow_api.baseline_map import build_baseline_map
from scholarflow_api.direction_review import (
    DirectionPaperReading,
    build_direction_review_bundle,
    build_direction_scope,
    determine_review_status,
    enforce_research_sight_diversity,
    render_direction_review_markdown,
    select_top_direction_papers,
)
from scholarflow_api.paper_card import generate_deep_paper_card
from scholarflow_api.research_decisions import generate_research_decisions
from scholarflow_api import research_memory as research_memory_module
from scholarflow_api.research_memory import query_research_memory, score_memory_record
from scholarflow_api.research_sight import build_research_sight
from scholarflow_api.text_utils import extract_terms


class ResearchQualitySmokeTest(unittest.TestCase):
    def test_literature_coverage_distinguishes_eligible_from_returned_limit(self) -> None:
        papers = [
            literature.PaperCandidate(
                title=f"Evidence Faithfulness Benchmark {index}",
                year="2026",
                authors="A. Researcher",
                abstract="A VQA evidence faithfulness benchmark.",
                type="Benchmark",
                venue="arXiv cs.CV",
                source="arxiv",
                url=f"https://arxiv.org/abs/2601.{index:05d}",
                relation="direct match",
                priority="High",
                relevance_score=1.5,
                relevance_quality="strong",
            )
            for index in range(6)
        ]
        ranked = literature.RankedPaperSet(
            papers=papers,
            coverage={
                "candidate_count": 6,
                "returned_count": 6,
                "strong_match_count": 6,
                "medium_match_count": 0,
                "weak_match_count": 0,
                "off_topic_count": 0,
                "filtered_count": 0,
            },
        )

        with patch.object(literature, "expand_queries", return_value=["evidence faithfulness"]), patch.object(
            literature,
            "search_sources_for_query",
            return_value=papers,
        ), patch.object(literature, "rank_and_deduplicate_result", return_value=ranked):
            result = literature.search_literature("evidence faithfulness", max_results=2, sources=["arxiv"])

        self.assertEqual(len(result.papers), 2)
        self.assertEqual(result.relevance_coverage["candidate_count"], 6)
        self.assertEqual(result.relevance_coverage["eligible_count"], 6)
        self.assertEqual(result.relevance_coverage["returned_count"], 2)
        self.assertEqual(result.relevance_coverage["truncated_count"], 4)

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

        with patch.object(literature, "get_cached_retrieval", return_value=None), patch.object(
            literature,
            "save_cached_retrieval",
        ), patch.object(literature, "search_arxiv", side_effect=fake_arxiv), patch.object(
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

    def test_chinese_multimodal_vqa_query_filters_off_topic_openalex_results(self) -> None:
        candidates = [
            literature.PaperCandidate(
                title="Evaluating Object Hallucination in Large Vision-Language Models",
                year="2025",
                authors="A. Researcher",
                abstract="This benchmark evaluates object hallucination and visual grounding in VLMs.",
                type="Benchmark",
                venue="arXiv cs.CV",
                source="openalex",
                url="https://openalex.org/W1",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="Assessment and Classroom Learning",
                year="2025",
                authors="B. Researcher",
                abstract="This paper studies evidence-based classroom assessment and student learning evaluation.",
                type="article",
                venue="Education Journal",
                source="openalex",
                url="https://openalex.org/W2",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="PRISMA-guided Meta-analysis of Clinical Assessment Evidence",
                year="2024",
                authors="C. Researcher",
                abstract="A systematic review and meta-analysis of clinical assessment evidence.",
                type="article",
                venue="Medical Evidence Review",
                source="openalex",
                url="https://openalex.org/W3",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="BRATS Medical Image Segmentation Benchmark Evaluation",
                year="2025",
                authors="D. Researcher",
                abstract="This benchmark evaluates MRI brain tumor segmentation models on BRATS.",
                type="article",
                venue="Medical Journal",
                source="openalex",
                url="https://openalex.org/W4",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="Clinical Evaluation of Tuberculosis Treatment Outcomes",
                year="2025",
                authors="E. Researcher",
                abstract="This work evaluates treatment outcomes for tuberculosis patients.",
                type="article",
                venue="Medical Journal",
                source="openalex",
                url="https://openalex.org/W5",
                relation="",
                priority="Medium",
            ),
        ]

        ranked = literature.rank_and_deduplicate_result(
            candidates,
            "多模态大模型在视觉问答中的证据忠实性评估",
        )

        returned_titles = {paper.title for paper in ranked.papers}
        self.assertIn("Evaluating Object Hallucination in Large Vision-Language Models", returned_titles)
        self.assertNotIn("Assessment and Classroom Learning", returned_titles)
        self.assertNotIn("PRISMA-guided Meta-analysis of Clinical Assessment Evidence", returned_titles)
        self.assertNotIn("BRATS Medical Image Segmentation Benchmark Evaluation", returned_titles)
        self.assertNotIn("Clinical Evaluation of Tuberculosis Treatment Outcomes", returned_titles)
        self.assertEqual(ranked.coverage["off_topic_count"], 4)
        self.assertEqual(ranked.coverage["filtered_count"], 4)
        self.assertTrue(all(paper.priority != "High" for paper in candidates[1:]))
        self.assertTrue(all(paper.relevance_quality not in {"strong", "medium"} for paper in candidates[1:]))

    def test_chinese_multimodal_vqa_query_recalls_bilingual_related_papers(self) -> None:
        calls: list[tuple[str, bool]] = []
        positive_candidates = [
            literature.PaperCandidate(
                title="POPE: Polling-based Object Probing Evaluation for Object Hallucination",
                year="2025",
                authors="A. Researcher",
                abstract=(
                    "A hallucination benchmark for large vision-language models using VQA-style prompts "
                    "to evaluate object hallucination and visual grounding."
                ),
                type="Benchmark",
                venue="arXiv cs.CV",
                source="arxiv",
                url="https://arxiv.org/abs/positive1",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="Faithful Visual Question Answering Requires Grounded Evidence",
                year="2025",
                authors="B. Researcher",
                abstract=(
                    "This work studies evidence faithfulness and visual grounding for visual question "
                    "answering in large vision-language models."
                ),
                type="Method",
                venue="arXiv cs.CV",
                source="arxiv",
                url="https://arxiv.org/abs/positive2",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="Evaluating Object Hallucination in Large Vision-Language Models",
                year="2025",
                authors="C. Researcher",
                abstract=(
                    "The paper evaluates object hallucination in LVLMs with visual question answering "
                    "and grounded visual evidence."
                ),
                type="Benchmark",
                venue="arXiv cs.CV",
                source="arxiv",
                url="https://arxiv.org/abs/positive3",
                relation="",
                priority="Medium",
            ),
        ]
        off_topic_candidates = [
            literature.PaperCandidate(
                title="Assessment and Classroom Learning",
                year="2025",
                authors="D. Researcher",
                abstract="Evidence-based classroom assessment and student learning evaluation.",
                type="article",
                venue="Education Journal",
                source="arxiv",
                url="https://arxiv.org/abs/offtopic1",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="PRISMA-guided Meta-analysis of Clinical Assessment Evidence",
                year="2024",
                authors="E. Researcher",
                abstract="A systematic review and meta-analysis of clinical assessment evidence.",
                type="article",
                venue="Medical Evidence Review",
                source="arxiv",
                url="https://arxiv.org/abs/offtopic2",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="BRATS Medical Image Segmentation Benchmark Evaluation",
                year="2025",
                authors="F. Researcher",
                abstract="This benchmark evaluates MRI brain tumor segmentation models on BRATS.",
                type="article",
                venue="Medical Journal",
                source="arxiv",
                url="https://arxiv.org/abs/offtopic3",
                relation="",
                priority="Medium",
            ),
        ]

        def fake_arxiv(query: str, max_results: int, relaxed: bool = False) -> list[literature.PaperCandidate]:
            calls.append((query, relaxed))
            lower = query.lower()
            if any(signal in lower for signal in ["object hallucination", "pope", "visual question answering", "visual grounding"]):
                return [*positive_candidates, *off_topic_candidates]
            return off_topic_candidates

        with patch.object(literature, "get_cached_retrieval", return_value=None), patch.object(
            literature,
            "save_cached_retrieval",
            return_value=None,
        ), patch.object(literature, "search_arxiv", side_effect=fake_arxiv):
            result = literature.search_literature(
                "多模态大模型在视觉问答中的证据忠实性评估",
                max_results=8,
                sources=["arxiv"],
            )

        returned_titles = [paper.title for paper in result.papers]
        self.assertGreaterEqual(len(result.papers), 3)
        self.assertGreaterEqual(
            sum(1 for paper in result.papers if paper.relevance_quality in {"strong", "medium"}),
            3,
        )
        self.assertTrue(
            all(
                any(
                    signal in paper.title.lower()
                    for signal in ["hallucination", "vision-language", "vlm", "lvlm", "pope", "grounding", "visual question"]
                )
                for paper in result.papers[:3]
            ),
        )
        self.assertNotIn("Assessment and Classroom Learning", returned_titles)
        self.assertNotIn("PRISMA-guided Meta-analysis of Clinical Assessment Evidence", returned_titles)
        self.assertNotIn("BRATS Medical Image Segmentation Benchmark Evaluation", returned_titles)
        self.assertGreaterEqual(result.relevance_coverage.get("off_topic_count", 0), 3)
        self.assertTrue(any("object hallucination" in query.lower() or "visual question answering" in query.lower() for query, _ in calls))

    def test_chinese_multimodal_vqa_relaxed_queries_are_not_support_only(self) -> None:
        expanded = literature.expand_queries("多模态大模型在视觉问答中的证据忠实性评估")
        relaxed = literature.build_relaxed_queries("多模态大模型在视觉问答中的证据忠实性评估", expanded)

        self.assertTrue(relaxed)
        self.assertFalse(any(literature.is_support_only_query(query) for query in relaxed))
        pure_support = {"assessment", "benchmark", "evaluating", "evaluation", "assessment benchmark evaluating"}
        self.assertTrue(pure_support.isdisjoint({query.lower() for query in relaxed}))

    def test_support_only_assessment_evidence_terms_do_not_reach_medium(self) -> None:
        candidate = literature.PaperCandidate(
            title="Evidence Assessment Benchmark for Classroom Learning",
            year="2026",
            authors="A. Teacher",
            abstract="This evaluation benchmark studies evidence assessment in classroom learning.",
            type="article",
            venue="Education Assessment",
            source="openalex",
            url="https://openalex.org/W_support_only",
            relation="",
            priority="Medium",
        )

        relevance = literature.score_candidate(
            candidate,
            literature.build_query_intent("多模态大模型在视觉问答中的证据忠实性评估"),
        )

        self.assertIn(relevance.quality, {"weak", "off_topic"})
        self.assertNotIn(relevance.quality, {"strong", "medium"})

    def test_object_hallucination_direction_excludes_medical_ocr_and_humanities_papers(self) -> None:
        direction = "多模态大模型对象幻觉评估"
        candidates = [
            literature.PaperCandidate(
                title="POPE: Object Hallucination Evaluation for Large Vision-Language Models",
                year="2025",
                authors="A. Researcher",
                abstract="We benchmark object hallucination in LVLMs with VQA-style object probing.",
                type="Benchmark",
                venue="CVPR",
                source="arxiv",
                url="https://arxiv.org/abs/2601.00010",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="Detecting and Evaluating Medical Hallucinations in Large Vision Language Models",
                year="2025",
                authors="B. Researcher",
                abstract="We evaluate medical hallucination in clinical large vision-language models.",
                type="Method",
                venue="Medical AI Journal",
                source="openalex",
                url="https://openalex.org/medical",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="OCR Hallucination Detection for Document Understanding",
                year="2025",
                authors="C. Researcher",
                abstract="A document OCR benchmark detects hallucination in text recognition.",
                type="Benchmark",
                venue="Document AI",
                source="openalex",
                url="https://openalex.org/ocr",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="Ancient Greek Hallucination Analysis in Language Models",
                year="2025",
                authors="D. Researcher",
                abstract="We evaluate hallucination when translating ancient Greek manuscripts.",
                type="Analysis",
                venue="Digital Humanities",
                source="openalex",
                url="https://openalex.org/greek",
                relation="",
                priority="Medium",
            ),
        ]

        selected = select_top_direction_papers(candidates, direction, [], limit=10)
        selected_titles = {paper.title for paper in selected}

        self.assertIn("POPE: Object Hallucination Evaluation for Large Vision-Language Models", selected_titles)
        self.assertNotIn("Detecting and Evaluating Medical Hallucinations in Large Vision Language Models", selected_titles)
        self.assertNotIn("OCR Hallucination Detection for Document Understanding", selected_titles)
        self.assertNotIn("Ancient Greek Hallucination Analysis in Language Models", selected_titles)
        self.assertEqual(determine_review_status(len(selected), 0, 3, 10), "partial")
        self.assertTrue(selected[0].matched_terms)

    def test_object_hallucination_top_three_is_direct_for_chinese_and_english_queries(self) -> None:
        direct_candidates = [
            literature.PaperCandidate(
                title="POPE: Polling-based Object Probing Evaluation for Object Hallucination",
                year="2026",
                authors="A",
                abstract="We evaluate object hallucination in large vision-language models with the POPE benchmark.",
                type="Benchmark",
                venue="CVPR",
                source="arxiv",
                url="https://arxiv.org/abs/direct1",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="Evaluating Visual Object Hallucination in Large Vision-Language Models",
                year="2025",
                authors="B",
                abstract="This evaluation measures visual object hallucination and object grounding in LVLMs.",
                type="Analysis",
                venue="ICCV",
                source="arxiv",
                url="https://arxiv.org/abs/direct2",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="Object Grounding Benchmark for Hallucination Detection in VLMs",
                year="2025",
                authors="C",
                abstract="A benchmark probes object grounding failures and hallucination in VLM answers.",
                type="Benchmark",
                venue="ACL",
                source="arxiv",
                url="https://arxiv.org/abs/direct3",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="A Diagnostic Study of Object Hallucination in LVLMs",
                year="2024",
                authors="D",
                abstract="We analyze object hallucination and evaluate component-level causes in LVLMs.",
                type="Analysis",
                venue="arXiv cs.CV",
                source="arxiv",
                url="https://arxiv.org/abs/direct4",
                relation="",
                priority="Medium",
            ),
        ]
        cross_domain = [
            literature.PaperCandidate(
                title="Detecting and Evaluating Medical Hallucinations in Large Vision Language Models",
                year="2026",
                authors="M",
                abstract="We evaluate medical hallucination in clinical VLMs.",
                type="Method",
                venue="Medical AI",
                source="openalex",
                url="https://openalex.org/medical-hallucination",
                relation="",
                priority="Medium",
            ),
            literature.PaperCandidate(
                title="OCR Hallucination Benchmark for Document Understanding",
                year="2026",
                authors="O",
                abstract="We detect OCR hallucination in document recognition systems.",
                type="Benchmark",
                venue="Document AI",
                source="openalex",
                url="https://openalex.org/ocr-hallucination",
                relation="",
                priority="Medium",
            ),
        ]

        for query in ["多模态大模型对象幻觉评估", "visual object hallucination evaluation benchmark POPE"]:
            selected = select_top_direction_papers([*direct_candidates, *cross_domain], query, [], limit=10)
            top_three_titles = [paper.title for paper in selected[:3]]
            self.assertEqual(len(top_three_titles), 3, query)
            self.assertFalse(any("Medical" in title or "OCR" in title for title in top_three_titles), query)
            self.assertTrue(all(paper.relevance_quality in {"strong", "medium"} for paper in selected), query)
            self.assertTrue(all("直接证据" in paper.relation for paper in selected[:3]), query)
            self.assertEqual(determine_review_status(len(selected), 0, len(cross_domain), 10), "partial")

    def test_memory_query_returns_no_reliable_hit_for_zero_score_records(self) -> None:
        record = {
            "title": "Unrelated Language Modeling Survey",
            "keywords_json": json.dumps(["language modeling", "survey"]),
            "memory_text": "A background note about unrelated language modeling.",
            "self_read_priority": 1,
        }
        with patch.object(research_memory_module, "backfill_project_research_memory", return_value=0), patch.object(
            research_memory_module,
            "fetch_memory_records",
            return_value=[record],
        ), patch.object(research_memory_module, "fetch_direction_memory_snapshot", return_value=None):
            answer = query_research_memory(
                connection=None,
                project_id="project_memory",
                question="如何评估对象幻觉？",
                top_k=5,
                now="2026-07-15T00:00:00Z",
            )

        self.assertEqual(answer.reliability_status, "no_reliable_hit")
        self.assertEqual(answer.hits, [])
        self.assertIn("没有可靠证据", answer.answer)
        self.assertNotIn("最相关的证据来自", answer.answer)
        self.assertTrue(any("未把零分" in warning for warning in answer.warnings))
        self.assertTrue(any("主题词" in warning for warning in answer.warnings))

    def test_memory_reliable_answer_binds_paper_id_and_evidence_quality(self) -> None:
        record = {
            "id": "memory_grounded",
            "paper_id": "paper_grounded",
            "project_id": "project_memory",
            "direction": "对象幻觉评估",
            "round_index": 1,
            "title": "POPE Object Hallucination Evaluation",
            "authors": "A",
            "year": "2026",
            "venue": "CVPR",
            "source": "arxiv",
            "url": "https://arxiv.org/abs/grounded",
            "keywords_json": json.dumps(["object hallucination", "POPE"]),
            "memory_text": "generated memory text must not be the reliability source",
            "research_sight_json": json.dumps(
                {
                    "evidence_pack": {
                        "evidence_level": "abstract_only",
                        "snippets": [
                            {
                                "id": "abstract_1",
                                "source": "metadata.abstract",
                                "kind": "evaluation",
                                "text": "We evaluate object hallucination in LVLMs with the POPE benchmark.",
                                "confidence": "medium",
                            },
                        ],
                    },
                },
            ),
            "self_read_priority": 1,
            "created_at": "now",
        }
        with patch.object(research_memory_module, "backfill_project_research_memory", return_value=0), patch.object(
            research_memory_module,
            "fetch_memory_records",
            return_value=[record],
        ), patch.object(research_memory_module, "fetch_direction_memory_snapshot", return_value=None):
            answer = query_research_memory(
                connection=None,
                project_id="project_memory",
                question="如何评估多模态大模型对象幻觉？",
                top_k=5,
                now="2026-07-15T00:00:00Z",
            )

        self.assertEqual(answer.reliability_status, "reliable")
        self.assertEqual(len(answer.hits), 1)
        self.assertIn("paper_id=paper_grounded", answer.answer)
        self.assertIn("evidence_quality=abstract_only", answer.answer)
        self.assertIn("snippet=abstract_1", answer.answer)

    def test_research_sight_without_source_text_does_not_invent_claim_metric_or_dataset(self) -> None:
        paper = {
            "title": "Sparse Metadata Paper",
            "abstract": "",
            "year": "2026",
            "venue": "arXiv",
            "source": "arxiv",
            "url": "https://arxiv.org/abs/sparse",
        }
        card = generate_deep_paper_card(paper)
        sight = build_research_sight(
            paper,
            [section.to_dict() for section in card.sections],
            build_baseline_map("对象幻觉评估", [], []),
            "对象幻觉评估",
            card.signals,
        )

        self.assertIn("无法判断", sight.why_not_good)
        self.assertIn("无法判断", sight.better_angle)
        self.assertTrue(all(item.evidence_snippet_id == "none" for item in sight.critique_evidence))
        self.assertNotIn("POPE", sight.why_not_good)

    def test_direction_round_deduplicates_template_follow_up_ideas(self) -> None:
        baseline_map = build_baseline_map("对象幻觉评估", [], [])
        readings: list[DirectionPaperReading] = []
        for index in range(2):
            paper = {
                "id": f"paper_repeat_{index}",
                "title": f"Sparse Object Hallucination Paper {index}",
                "abstract": "",
                "year": "2026",
                "venue": "arXiv",
                "source": "arxiv",
                "url": f"https://arxiv.org/abs/repeat{index}",
            }
            card = generate_deep_paper_card(paper)
            sight = build_research_sight(
                paper,
                [section.to_dict() for section in card.sections],
                baseline_map,
                "对象幻觉评估",
                card.signals,
            )
            readings.append(
                DirectionPaperReading(
                    paper=paper,
                    abstract_translation="",
                    card=card,
                    full_text={},
                    research_sight=sight,
                    why_selected="test",
                    venue_signal="arXiv",
                    self_read_priority=False,
                ),
            )

        enforce_research_sight_diversity(readings)

        self.assertNotEqual(readings[0].card.follow_up_idea, readings[1].card.follow_up_idea)
        self.assertIn("无法提出独立 follow-up", readings[1].card.follow_up_idea)

    def test_two_metadata_only_cards_do_not_emit_long_repeated_research_templates(self) -> None:
        cards = [
            generate_deep_paper_card({"title": "Metadata-only Object Hallucination Paper A"}),
            generate_deep_paper_card({"title": "Metadata-only Object Hallucination Paper B"}),
        ]

        for card in cards:
            self.assertEqual(card.evidence_level, "metadata_only")
            self.assertTrue(all(len(section.content) < 180 for section in card.sections))
            self.assertNotIn("counterexample-first", " ".join(section.content for section in card.sections))
            self.assertIn("无法判断", card.weakest_assumption)
        self.assertNotEqual(cards[0].sections[0].content, cards[1].sections[0].content)

    def test_abstract_without_dataset_metric_claim_keeps_research_sight_bounded(self) -> None:
        paper = {
            "title": "Understanding Object Hallucination in Vision-Language Models",
            "abstract": "This paper discusses object hallucination in large vision-language models.",
            "year": "2026",
            "venue": "arXiv",
            "source": "arxiv",
            "url": "https://arxiv.org/abs/abstract-only",
        }
        card = generate_deep_paper_card(paper)
        sight = build_research_sight(
            paper,
            [section.to_dict() for section in card.sections],
            build_baseline_map("对象幻觉评估", [], []),
            "对象幻觉评估",
            card.signals,
        )

        self.assertEqual(card.evidence_level, "abstract_only")
        self.assertIn("当前证据不足", card.signals.dataset)
        self.assertIn("当前证据不足", card.signals.metric)
        self.assertIn("当前证据不足", card.signals.claim)
        self.assertIn("无法判断", sight.why_not_good)
        self.assertIn("无法判断", sight.better_angle)
        self.assertNotIn("counterexample-first", sight.better_angle)

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

    def test_source_level_backoff_skips_openalex_after_transient_failure(self) -> None:
        openalex_calls = {"count": 0}

        def fake_arxiv(query: str, max_results: int, relaxed: bool = False) -> list[literature.PaperCandidate]:
            return []

        def fake_openalex(query: str, max_results: int) -> list[literature.PaperCandidate]:
            openalex_calls["count"] += 1
            raise literature.SourceDegradedError("openalex", query, 503, "temporary unavailable")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db

                init_db()
                with patch.object(literature, "search_arxiv", side_effect=fake_arxiv), patch.object(
                    literature,
                    "search_openalex",
                    side_effect=fake_openalex,
                ):
                    result = literature.search_literature("hallucination", max_results=8, sources=["arxiv", "openalex"])

        self.assertEqual(openalex_calls["count"], 1)
        self.assertTrue(any("openalex_cooldown" in warning for warning in result.errors))
        self.assertFalse(any(paper.source in {"seed", "demo"} for paper in result.papers))

    def test_sqlite_retrieval_cache_hit_avoids_external_source_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db

                init_db()
                cached_paper = literature.PaperCandidate(
                    title="Cached Evidence Faithfulness Benchmark",
                    year="2026",
                    authors="A. Researcher",
                    abstract="Cached paper about evidence faithfulness.",
                    type="Benchmark",
                    venue="arXiv cs.CL",
                    source="openalex",
                    url="https://openalex.org/W123",
                    relation="cached",
                    priority="High",
                )
                literature.save_cached_retrieval("openalex", "cached query", 5, [cached_paper], [])

                with patch.object(literature, "search_openalex", side_effect=AssertionError("external source called")):
                    errors: list[str] = []
                    papers = literature.search_sources_for_query("cached query", 5, ["openalex"], errors)

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].title, "Cached Evidence Faithfulness Benchmark")
        self.assertTrue(any("using_cached_results" in warning for warning in errors))

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

    def test_direction_review_marks_zero_strong_matches_as_blocked(self) -> None:
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

        self.assertEqual(bundle.review_status, "blocked")
        self.assertEqual(bundle.target_paper_count, 10)
        self.assertTrue(any("blocked_direction_review" in warning for warning in bundle.errors))
        self.assertIn("Blocked Direction Review", markdown)
        self.assertIn("Coverage: 0/10", markdown)

    def test_direction_review_does_not_complete_from_off_topic_ten_count(self) -> None:
        baseline_map = build_baseline_map("多模态大模型在视觉问答中的证据忠实性评估", [], [])
        bundle = build_direction_review_bundle(
            direction="多模态大模型在视觉问答中的证据忠实性评估",
            round_index=1,
            scope=build_direction_scope("多模态大模型在视觉问答中的证据忠实性评估", 1),
            baseline_map=baseline_map,
            readings=[],
            previous_read_count=0,
            errors=[],
            relevance_coverage={
                "candidate_count": 10,
                "returned_count": 0,
                "strong_match_count": 0,
                "medium_match_count": 0,
                "weak_match_count": 0,
                "off_topic_count": 10,
                "filtered_count": 10,
            },
        )

        self.assertEqual(bundle.review_status, "blocked")
        self.assertEqual(bundle.relevant_read_count, 0)
        self.assertEqual(bundle.off_topic_count, 10)
        self.assertTrue(any("blocked_direction_review" in warning for warning in bundle.errors))

    def test_direction_review_artifact_uses_v2_flat_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import direction_review as direction_review_module
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import DirectionReviewRequest, ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Direction V2 Schema", keyword="evidence faithfulness benchmark"),
                )
                fake_result = literature.LiteratureSearchResult(
                    query="evidence faithfulness benchmark",
                    expanded_queries=["evidence faithfulness benchmark"],
                    papers=[
                        literature.PaperCandidate(
                            title="Evidence Faithfulness Benchmark for VQA",
                            year="2026",
                            authors="A. Researcher",
                            abstract=(
                                "Dataset: POPE. Metric: accuracy. Baseline: LLaVA. "
                                "Claim: the benchmark exposes hallucination failures."
                            ),
                            type="Benchmark",
                            venue="CVPR",
                            source="arxiv",
                            url="https://arxiv.org/abs/2601.00002",
                            relation="matches evidence faithfulness benchmark",
                            priority="High",
                            relevance_score=1.4,
                        )
                    ],
                    errors=[],
                )
                with patch.object(direction_review_module, "search_literature", return_value=fake_result):
                    response = main_module.create_project_direction_review(
                        project.id,
                        DirectionReviewRequest(direction=project.keyword, round=1),
                    )
                review_ref = next(artifact for artifact in response.artifact_refs if "direction_review" in artifact.title)
                artifact = main_module.get_artifact(review_ref.id)
                payload = json.loads(artifact.content_json)

        self.assertEqual(payload["schema_version"], "direction_review.v2")
        self.assertEqual(payload["round_read_count"], 1)
        self.assertIn("papers", payload)
        self.assertIn("sections", payload["papers"][0])
        self.assertEqual(len(payload["papers"][0]["sections"]), 12)
        for key in [
            "paper",
            "signals",
            "research_sight",
            "weakest_assumption",
            "minimal_reproduction",
            "counterexample",
            "follow_up_idea",
            "why_selected",
            "venue_signal",
            "self_read_priority",
        ]:
            self.assertIn(key, payload["papers"][0])

    def test_research_memory_artifact_uses_v2_flat_hit_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import direction_review as direction_review_module
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import (
                    DirectionReviewRequest,
                    ProjectCreate,
                    ResearchMemoryQueryRequest,
                )

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Memory V2 Schema", keyword="evidence faithfulness benchmark"),
                )
                fake_result = literature.LiteratureSearchResult(
                    query="evidence faithfulness benchmark",
                    expanded_queries=["evidence faithfulness benchmark"],
                    papers=[
                        literature.PaperCandidate(
                            title="Evidence Faithfulness Benchmark for VQA",
                            year="2026",
                            authors="A. Researcher",
                            abstract=(
                                "Dataset: POPE. Metric: accuracy. Baseline: LLaVA. "
                                "Claim: the benchmark exposes hallucination failures."
                            ),
                            type="Benchmark",
                            venue="CVPR",
                            source="arxiv",
                            url="https://arxiv.org/abs/2601.00002",
                            relation="matches evidence faithfulness benchmark",
                            priority="High",
                            relevance_score=1.4,
                        )
                    ],
                    errors=[],
                )
                with patch.object(direction_review_module, "search_literature", return_value=fake_result):
                    main_module.create_project_direction_review(
                        project.id,
                        DirectionReviewRequest(direction=project.keyword, round=1),
                    )
                response = main_module.query_project_research_memory(
                    project.id,
                    ResearchMemoryQueryRequest(
                        question="What dataset metric baseline counterexample should I test?",
                        direction=project.keyword,
                        top_k=3,
                    ),
                )
                payload = json.loads(response.artifact.content_json)

        self.assertEqual(payload["schema_version"], "research_memory_answer.v2")
        self.assertGreaterEqual(len(payload["hits"]), 1)
        hit = payload["hits"][0]
        self.assertNotIn("memory", hit)
        for key in [
            "paper",
            "direction",
            "round",
            "score",
            "snippets",
            "research_sight",
            "weakest_assumption",
            "minimal_reproduction",
            "counterexample",
            "follow_up_idea",
        ]:
            self.assertIn(key, hit)

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
                    "evidence_level": "abstract_only",
                },
            ],
            goal="build a one-week experiment",
        )

        self.assertEqual(bundle.experiment.status, "blocked")
        self.assertEqual(bundle.evidence_quality["abstract_only_card_count"], 1)
        self.assertEqual(bundle.evidence_quality["full_text_card_count"], 0)
        self.assertTrue(any("摘要级/元数据级证据" in warning for warning in bundle.warnings))
        suggestions = " ".join(bundle.experiment.unblock_suggestions).lower()
        self.assertIn("dataset", suggestions)
        self.assertIn("baseline", suggestions)
        self.assertIn("metric", suggestions)

    def test_literature_response_includes_workflow_step_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import LiteratureSearchRequest, ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Workflow Step Literature", keyword="evidence faithfulness"),
                )
                fake_result = literature.LiteratureSearchResult(
                    query=project.keyword,
                    expanded_queries=[project.keyword],
                    papers=[
                        literature.PaperCandidate(
                            title="Evidence Faithfulness Benchmark",
                            year="2026",
                            authors="A. Researcher",
                            abstract="Dataset: POPE. Metric: accuracy.",
                            type="Benchmark",
                            venue="arXiv cs.CV",
                            source="arxiv",
                            url="https://arxiv.org/abs/2601.00004",
                            relation="matches evidence faithfulness",
                            priority="High",
                            relevance_score=1.2,
                        )
                    ],
                    errors=["using_cached_results:arxiv:evidence faithfulness: 使用缓存。"],
                )
                with patch.object(main_module, "search_literature", return_value=fake_result):
                    response = main_module.search_project_literature(
                        project.id,
                        LiteratureSearchRequest(query=project.keyword),
                    )

        self.assertEqual(len(response.workflow_steps), 1)
        step = response.workflow_steps[0]
        self.assertEqual(step.step_id, "paper-table")
        self.assertEqual(step.status, "partial")
        self.assertTrue(step.warnings)
        self.assertEqual(step.artifact_refs[0].title, "paper_table.md")

    def test_research_decision_response_marks_blocked_experiment_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import ProjectCreate, ResearchDecisionRequest

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Blocked Workflow Step", keyword="trustworthy VLM"),
                )
                response = main_module.create_project_research_decisions(
                    project.id,
                    ResearchDecisionRequest(goal="one-week experiment"),
                )

        experiment_step = next(step for step in response.workflow_steps if step.step_id == "experiment-planner")
        self.assertEqual(response.experiment.status, "blocked")
        self.assertEqual(experiment_step.status, "blocked")
        self.assertTrue(experiment_step.warnings)

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

    def test_project_paper_card_generation_produces_twelve_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import PaperCardCreateRequest, ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Paper Card Smoke", keyword="evidence faithfulness benchmark"),
                )
                response = main_module.create_project_paper_card(
                    project.id,
                    PaperCardCreateRequest(
                        title="Evidence Faithfulness Benchmark for VQA",
                        abstract=(
                            "Dataset: POPE. Metric: accuracy. Baseline: LLaVA. "
                            "Claim: the benchmark exposes hallucination failures."
                        ),
                    ),
                )

        self.assertEqual(len(response.card.sections), 12)
        self.assertTrue(response.card.weakest_assumption)
        self.assertTrue(response.artifact.id)

    def test_paper_card_metadata_and_abstract_levels_mark_evidence_boundary(self) -> None:
        from scholarflow_api.paper_card import generate_deep_paper_card, render_card_markdown

        metadata_card = generate_deep_paper_card({"title": "Unknown Metadata Only Paper"})
        abstract_card = generate_deep_paper_card(
            {
                "title": "Faithful Visual Question Answering Requires Grounded Evidence",
                "abstract": "This paper studies visual grounding and evidence faithfulness in VQA.",
            },
        )

        self.assertEqual(metadata_card.evidence_level, "metadata_only")
        self.assertEqual(abstract_card.evidence_level, "abstract_only")
        self.assertNotIn("全文级深读", metadata_card.sections[0].content)
        self.assertTrue(
            all("证据边界（abstract_only）：" not in section.content for section in abstract_card.sections),
        )
        self.assertEqual(len({section.content for section in abstract_card.sections}), 12)
        rendered = render_card_markdown(abstract_card, {"title": abstract_card.paper_title})
        self.assertIn("Evidence boundary: 证据边界（abstract_only）", rendered)
        self.assertIn("不能当作已讲清整篇论文", rendered)
        self.assertIn("Status: blocked", abstract_card.minimal_reproduction)

    def test_full_text_card_extracts_dataset_metric_baseline_and_ready_minimal_reproduction(self) -> None:
        from scholarflow_api.paper_card import generate_deep_paper_card

        paper_text = (
            "We propose a grounded evidence evaluation method for visual question answering. "
            "The method builds contrastive visual evidence and evaluates answers with evidence rationales. "
            "Experiments use Dataset: POPE, A-OKVQA and GQA. "
            "Evaluation metrics include accuracy and F1 for answer correctness and grounding faithfulness. "
            "Baselines include LLaVA, BLIP-2, and a no-grounding prompting baseline. "
            "Compared with LLaVA, our method improves evidence faithfulness and reduces hallucination rate. "
            "We show the benchmark exposes object hallucination failures under conflicting visual evidence."
        )
        card = generate_deep_paper_card(
            {
                "title": "Grounded Evidence Evaluation for Visual Question Answering",
                "abstract": "We propose a grounded evidence evaluation method for VQA.",
            },
            paper_text,
        )

        self.assertEqual(card.evidence_level, "full_text")
        self.assertIn("POPE", card.signals.dataset)
        self.assertIn("A-OKVQA", card.signals.dataset)
        self.assertIn("GQA", card.signals.dataset)
        self.assertTrue("accuracy" in card.signals.metric.lower() or "F1" in card.signals.metric)
        self.assertIn("LLaVA", card.signals.baseline)
        self.assertIn("Status: ready", card.minimal_reproduction)
        self.assertIn("Baseline:", card.minimal_reproduction)

    def test_memory_and_gap_do_not_use_off_topic_papers(self) -> None:
        from scholarflow_api.paper_card import generate_deep_paper_card
        from scholarflow_api.research_sight import build_research_sight
        from scholarflow_api.research_memory import (
            upsert_direction_reading_memories,
        )

        baseline_map = build_baseline_map("evidence faithfulness", [], [])
        off_topic_paper = {
            "id": "off_topic",
            "project_id": "project_quality",
            "title": "Clinical Evaluation of Tuberculosis Treatment Outcomes",
            "authors": "D. Researcher",
            "abstract": "This paper evaluates tuberculosis treatment outcomes.",
            "year": "2025",
            "type": "article",
            "venue": "Medical Journal",
            "source": "openalex",
            "url": "https://openalex.org/W4",
            "relation": "离题过滤",
            "priority": "Watch",
            "code": "unknown",
            "relevance_score": 0.2,
            "relevance_quality": "off_topic",
            "matched_terms_json": "[]",
            "review_required": 0,
            "created_at": "now",
        }
        card = generate_deep_paper_card(off_topic_paper)
        sections = [section.to_dict() for section in card.sections]
        reading = type(
            "Reading",
            (),
            {
                "paper": off_topic_paper,
                "card": card,
                "abstract_translation": "",
                "why_selected": "off-topic",
                "research_sight": build_research_sight(
                    off_topic_paper,
                    sections,
                    baseline_map,
                    "evidence faithfulness",
                    card.signals,
                ),
                "self_read_priority": False,
            },
        )()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import get_connection, init_db

                init_db()
                with get_connection() as connection:
                    memory_ids = upsert_direction_reading_memories(
                        connection,
                        "project_quality",
                        "evidence faithfulness",
                        1,
                        [reading],
                        "now",
                    )

        self.assertEqual(memory_ids, [])

        bundle = generate_research_decisions(
            project={"title": "Off Topic Gap", "keyword": "evidence faithfulness"},
            papers=[off_topic_paper],
            paper_cards=[
                {
                    "paper_id": "off_topic",
                    "paper_title": off_topic_paper["title"],
                    "minimal_reproduction": "Claim: works. Dataset: POPE. Metric: accuracy. Baseline: LLaVA.",
                    "weakest_assumption": "Off-topic evidence should not unlock gap evidence.",
                },
            ],
            goal="gap",
        )

        self.assertIn("当前没有 strong/medium 相关论文", bundle.gaps[0].evidence)
        self.assertNotIn("Clinical Evaluation of Tuberculosis", bundle.gaps[0].evidence)

    def test_artifact_summary_endpoint_is_lightweight_and_reports_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import ArtifactCreate, ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Summary Smoke", keyword="artifact schema"),
                )
                large_json = json.dumps(
                    {
                        "schema_version": "direction_review.v2",
                        "payload": "x" * 5000,
                    },
                    ensure_ascii=False,
                )
                artifact = main_module.save_artifact(
                    ArtifactCreate(
                        project_id=project.id,
                        title="direction_review_round_1.md",
                        kind="markdown",
                        content_markdown="# Direction Review\n\n" + "details " * 800,
                        content_json=large_json,
                    ),
                )
                summaries = main_module.list_project_artifact_summaries(project.id)
                detail = main_module.get_artifact(artifact.id)

        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(summary.json_schema_version, "direction_review.v2")
        self.assertEqual(summary.json_bytes, len(detail.content_json.encode("utf-8")))
        self.assertLess(len(summary.markdown_preview), len(detail.content_markdown))
        self.assertFalse(hasattr(summary, "content_json"))
        self.assertFalse(hasattr(summary, "content_markdown"))

    def test_agent_plan_contains_real_research_tool_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import AgentPlanRequest, ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Agent Plan Smoke", keyword="trustworthy VLM"),
                )
                plan = main_module.create_agent_plan(
                    AgentPlanRequest(
                        project_id=project.id,
                        task="Run a trustworthy VLM research workflow",
                        provider="local",
                    ),
                )

        tools = [step.tool for step in plan.steps]
        for required_tool in [
            "literature_search",
            "direction_review",
            "research_memory_query",
            "research_decision",
            "save_artifact",
            "update_timeline",
        ]:
            self.assertIn(required_tool, tools)
        self.assertNotIn("search_mock_papers", tools)

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

    def test_projects_list_orders_real_projects_before_demo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(
                        title="Real Project",
                        keyword="vision language evidence faithfulness",
                    ),
                )
                projects = main_module.list_projects()

        self.assertEqual(projects[0].id, project.id)
        self.assertFalse(projects[0].is_demo)
        self.assertEqual(projects[-1].id, "local-bootstrap")
        self.assertTrue(projects[-1].is_demo)

    def test_agent_plan_blocks_demo_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import AgentPlanRequest

                init_db()
                with self.assertRaises(Exception) as context:
                    main_module.create_agent_plan(
                        AgentPlanRequest(
                            project_id="local-bootstrap",
                            task="Run real research workflow on demo",
                            provider="local",
                        ),
                    )

        self.assertIn("Demo project is read-only", str(context.exception))

    def test_research_decisions_are_partial_when_gap_evidence_is_insufficient(self) -> None:
        papers = [
            {
                "id": "paper_method",
                "title": "Evidence Faithfulness Benchmark for VQA",
                "abstract": "A VQA benchmark for evidence faithfulness.",
                "type": "Benchmark",
                "source": "arxiv",
                "venue": "arXiv cs.CV",
                "url": "https://arxiv.org/abs/2601.00003",
                "priority": "High",
                "relevance_quality": "strong",
            },
            {
                "id": "paper_survey",
                "title": "A Survey of Trustworthy Vision-Language Models",
                "abstract": "A survey of VLM safety.",
                "type": "Survey",
                "source": "arxiv",
                "venue": "arXiv cs.CV",
                "url": "https://arxiv.org/abs/2601.00004",
                "priority": "High",
                "relevance_quality": "strong",
            },
        ]

        bundle = generate_research_decisions(
            project={"title": "Evidence Quality Project", "keyword": "VQA evidence faithfulness"},
            papers=papers,
            paper_cards=[],
            goal="Find a gap",
        )

        self.assertEqual(bundle.decision_status, "partial")
        self.assertEqual(bundle.evidence_quality["gap_evidence_paper_count"], 1)
        self.assertIn("暂不输出确定性研究判断", bundle.validation.idea)
        self.assertIn("Evidence Faithfulness Benchmark for VQA", bundle.gaps[0].evidence)
        self.assertNotIn("A Survey of Trustworthy Vision-Language Models", bundle.gaps[0].evidence)

    def test_agent_run_reports_literature_step_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import direction_review as direction_review_module
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import AgentExecuteRequest, AgentPlanRequest, ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(
                        title="Agent Metrics Smoke",
                        keyword="evidence faithfulness benchmark",
                    ),
                )
                fake_result = literature.LiteratureSearchResult(
                    query="evidence faithfulness benchmark",
                    expanded_queries=["evidence faithfulness benchmark"],
                    papers=[
                        literature.PaperCandidate(
                            title="Evidence Faithfulness Benchmark for VQA",
                            year="2026",
                            authors="A. Researcher",
                            abstract="Dataset: POPE. Metric: accuracy. Baseline: LLaVA. Claim: reduces hallucination.",
                            type="Benchmark",
                            venue="arXiv cs.CV",
                            source="arxiv",
                            url="https://arxiv.org/abs/2601.00002",
                            relation="matches evidence faithfulness benchmark",
                            priority="High",
                            relevance_score=1.4,
                        )
                    ],
                    errors=[],
                )

                with patch.object(main_module, "search_literature", return_value=fake_result), patch.object(
                    direction_review_module,
                    "search_literature",
                    return_value=fake_result,
                ):
                    plan = main_module.create_agent_plan(
                        AgentPlanRequest(
                            project_id=project.id,
                            task="Run an evidence faithfulness benchmark workflow",
                            provider="local",
                        ),
                    )
                    result = main_module.execute_agent_run(plan.run_id, AgentExecuteRequest(confirmed=True))
                    self.assertEqual(result.status, "running")
                    status = result
                    for _ in range(80):
                        polled = main_module.get_agent_run_status(plan.run_id)
                        if polled.status in {"completed", "completed_with_warnings", "partial", "failed", "cancelled"}:
                            status = polled
                            break
                        time.sleep(0.05)
                    timeline = main_module.get_project_timeline(project.id)

        literature_step = next(step for step in status.steps if step.tool == "literature_search")
        self.assertIn(status.status, {"partial", "completed_with_warnings"})
        self.assertEqual(literature_step.status, "done")
        self.assertGreater(status.paper_count, 0)
        self.assertGreater(int(literature_step.metrics.get("paper_count") or 0), 0)
        self.assertTrue(status.warnings)
        self.assertTrue(status.run_status_summary)
        self.assertTrue(any(step.step_id == "experiment-planner" for step in status.workflow_steps))
        self.assertIsNotNone(status.artifact)
        self.assertEqual(int(status.summary_metrics.get("warning_count") or 0), len(status.warnings))
        self.assertTrue(any(event.tool == "agent.execute" and event.status == "partial" for event in timeline))

    def test_agent_run_cancel_marks_planned_run_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                try:
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.schemas import AgentPlanRequest, ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(
                        title="Agent Cancel Smoke",
                        keyword="trustworthy VLM cancellation",
                    ),
                )
                plan = main_module.create_agent_plan(
                    AgentPlanRequest(
                        project_id=project.id,
                        task="Run then cancel a trustworthy VLM workflow",
                        provider="local",
                    ),
                )
                status = main_module.cancel_agent_run(plan.run_id)
                timeline = main_module.get_project_timeline(project.id)

        self.assertEqual(status.status, "cancelled")
        self.assertTrue(any(step.status == "cancelled" for step in status.steps))
        self.assertFalse(any(step.status == "running" for step in status.steps))
        self.assertTrue(any(event.tool == "agent.cancel" for event in timeline))


if __name__ == "__main__":
    unittest.main()
