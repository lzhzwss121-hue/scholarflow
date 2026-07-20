from __future__ import annotations

import json
import os
import ssl
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from scholarflow_api import full_text, literature
from scholarflow_api.baseline_map import build_baseline_map
from scholarflow_api.direction_review import build_direction_readings


def build_minimal_text_pdf() -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    text = (
        "Method experiment dataset POPE metric accuracy baseline LLaVA benchmark analysis mitigation. " * 30
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 10 Tf 20 700 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class FullTextEvidenceContractTest(unittest.TestCase):
    def test_pdf_selection_preserves_page_sections_and_excludes_references_tail(self) -> None:
        pages = [
            (
                "ScholarFlow Conference 2026\n"
                "Abstract\n"
                "We study grounded evidence faithfulness for visual question answering.\n"
                "1"
            ),
            (
                "ScholarFlow Conference 2026\n"
                "1 Introduction\n"
                "Existing methods suffer from object hallucination under conflicting visual evidence.\n"
                "2"
            ),
            (
                "ScholarFlow Conference 2026\n"
                "3 Method\n"
                "We propose a counterfactual grounding intervention for large vision-language models.\n"
                "3"
            ),
            (
                "ScholarFlow Conference 2026\n"
                "4 Experiments\n"
                "Experiments use GQA and report grounding accuracy against LLaVA.\n"
                "4"
            ),
            (
                "ScholarFlow Conference 2026\n"
                "References\n"
                "[1] POPE: Polling-based Object Probing Evaluation.\n"
                "5"
            ),
        ]

        selected = full_text.select_research_text(pages, max_chars=10000)

        self.assertIn("[PDF page 3]", selected)
        self.assertIn("[Section: method]", selected)
        self.assertIn("[Section: experiments]", selected)
        self.assertNotIn("References", selected)
        self.assertNotIn("POPE", selected)
        self.assertNotIn("ScholarFlow Conference 2026", selected)

    def test_paper_signals_ignore_reference_names_and_separate_prior_work_from_own_limitation(self) -> None:
        from scholarflow_api.paper_card import extract_paper_signals

        structured_text = """
[PDF page 2]
[Section: related_work]
However, these models suffer from object hallucination under conflicting visual evidence.

[PDF page 4]
[Section: method]
We propose a counterfactual grounding intervention for visual question answering.

[PDF page 7]
[Section: experiments]
Experiments use Dataset: GQA. Evaluation metrics include accuracy and acc.
Baselines include LLaVA and BLIP-2. We show improved grounding accuracy.

[PDF page 12]
[Section: references]
POPE: Polling-based Object Probing Evaluation for Object Hallucination.
"""
        signals = extract_paper_signals(
            title="Counterfactual Grounding for Visual Question Answering",
            abstract="We propose a grounded evaluation method for visual question answering.",
            paper_text=structured_text,
            venue="CVPR",
        )

        self.assertEqual(signals.dataset, "GQA")
        self.assertNotIn("POPE", signals.dataset)
        self.assertEqual(set(signals.metric.split(", ")), {"accuracy", "grounding accuracy"})
        self.assertNotIn("acc,", signals.metric.lower())
        self.assertIn("当前证据不足", signals.limitation)
        self.assertIn("these models suffer", signals.prior_work_limitation)
        dataset_evidence = signals.signal_evidence["dataset"]
        self.assertEqual(dataset_evidence.source, "pdf.full_text")
        self.assertEqual(dataset_evidence.section, "experiments")
        self.assertEqual(dataset_evidence.page, 7)
        self.assertIn("Dataset: GQA", dataset_evidence.quote)

    def test_explicit_own_limitation_is_grounded_to_limitation_section(self) -> None:
        from scholarflow_api.paper_card import extract_paper_signals

        signals = extract_paper_signals(
            title="Grounded Evaluation for VQA",
            abstract="We introduce a grounded evaluation protocol.",
            paper_text=(
                "[PDF page 9]\n"
                "[Section: limitations]\n"
                "Our method is limited to English prompts and we cannot verify multilingual transfer."
            ),
            venue="ACL",
        )

        self.assertIn("Our method is limited", signals.limitation)
        evidence = signals.signal_evidence["limitation"]
        self.assertEqual(evidence.section, "limitations")
        self.assertEqual(evidence.page, 9)

    def test_unlisted_dataset_names_are_extracted_and_prior_gap_resolution_is_not_own_limitation(self) -> None:
        from scholarflow_api.paper_card import extract_paper_signals

        signals = extract_paper_signals(
            title="Grounded Decoder for Multi-Object Hallucination",
            abstract="We study multi-object hallucination evaluation.",
            paper_text=(
                "[PDF page 3]\n"
                "[Section: introduction]\n"
                "To address this limitation, we propose a grounded decoder.\n\n"
                "[PDF page 8]\n"
                "[Section: experiments]\n"
                "We evaluate our method on OmniHall, ObjectScope, and SceneFaith-500 benchmarks. "
                "Evaluation uses accuracy."
            ),
            venue="CVPR",
        )

        self.assertEqual(signals.dataset, "OmniHall, ObjectScope, SceneFaith-500")
        self.assertIn("当前证据不足", signals.limitation)
        evidence = signals.signal_evidence["dataset"]
        self.assertEqual(evidence.source, "pdf.full_text")
        self.assertEqual(evidence.page, 8)
        self.assertIn("SceneFaith-500", evidence.quote)

    def test_evidence_pack_reserves_slots_for_pdf_before_abstract_metadata(self) -> None:
        from scholarflow_api.evidence import build_paper_evidence_pack

        pack = build_paper_evidence_pack(
            {
                "title": "Evidence Ordering",
                "abstract": (
                    "Object hallucination appears in visual grounding. "
                    "Evidence faithfulness remains difficult in evaluation."
                ),
                "venue": "CVPR",
                "year": "2026",
                "url": "https://example.org/evidence-ordering",
                "evidence_level": "full_text",
                "full_text": (
                    "[PDF page 6]\n"
                    "[Section: results]\n"
                    "Object hallucination increases because conflicting visual grounding evidence "
                    "causes the decoder to bind attributes to the wrong object."
                ),
            },
            [
                {"id": f"section-{index}", "title": f"Section {index}", "content": "Generated secondary analysis."}
                for index in range(1, 5)
            ],
            "object hallucination visual grounding",
        )

        sources = [snippet.source for snippet in pack.snippets]
        self.assertIn("pdf.full_text", sources)
        self.assertLess(sources.index("pdf.full_text"), sources.index("metadata.abstract"))
        self.assertLessEqual(len(pack.snippets), 7)

    def test_pdf_source_does_not_force_high_semantic_extraction_confidence(self) -> None:
        from scholarflow_api.evidence import build_paper_evidence_pack

        full_text_value = (
            "[PDF page 4]\n"
            "[Section: method]\n"
            "We propose a grounded intervention method and describe its architecture for evidence faithfulness. "
            "The method uses a visual encoder and a language decoder in a controlled pipeline."
        )
        pack = build_paper_evidence_pack(
            {
                "title": "Grounded Intervention for VQA",
                "abstract": "We study evidence faithfulness in visual question answering.",
                "venue": "CVPR",
                "url": "https://example.org/paper",
                "evidence_level": "full_text",
                "full_text": full_text_value,
            },
            [{"id": "method", "title": "Method", "content": "Grounded intervention."}],
            "VQA evidence faithfulness",
        )

        self.assertEqual(pack.source_confidence, "high")
        self.assertEqual(pack.extraction_confidence, "medium")
        self.assertEqual(pack.confidence, "medium")
        pdf_snippet = next(snippet for snippet in pack.snippets if snippet.source == "pdf.full_text")
        self.assertEqual(pdf_snippet.section, "method")
        self.assertEqual(pdf_snippet.page, 4)

    def test_open_pdf_download_uses_certifi_ca_context_without_disabling_tls_verification(self) -> None:
        pdf_url = "https://arxiv.org/pdf/2601.00003.pdf"
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = pdf_url
        response.headers.get.return_value = str(len(b"%PDF-1.7 fixture"))
        response.read.return_value = b"%PDF-1.7 fixture"
        context = object()

        with patch.object(full_text.certifi, "where", return_value="/private/tmp/ca-certificates.pem") as certifi_where, patch.object(
            full_text.ssl,
            "create_default_context",
            return_value=context,
        ) as create_context, patch.object(full_text.urllib.request, "urlopen", return_value=response) as urlopen:
            payload = full_text.download_pdf_bytes(pdf_url)

        self.assertEqual(payload, b"%PDF-1.7 fixture")
        certifi_where.assert_called_once_with()
        create_context.assert_called_once_with(cafile="/private/tmp/ca-certificates.pem")
        self.assertIs(urlopen.call_args.kwargs["context"], context)

    def test_trusted_ssl_context_keeps_hostname_and_certificate_verification_enabled(self) -> None:
        context = full_text.trusted_ssl_context()

        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_arxiv_and_openalex_results_preserve_open_pdf_urls(self) -> None:
        arxiv_atom = """
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry>
            <title>Grounded Evidence Evaluation for VQA</title>
            <summary>We evaluate evidence faithfulness in visual question answering.</summary>
            <published>2026-01-03T00:00:00Z</published>
            <author><name>A. Researcher</name></author>
            <link rel="alternate" href="https://arxiv.org/abs/2601.00003" />
            <link title="pdf" href="https://arxiv.org/pdf/2601.00003" type="application/pdf" />
            <arxiv:primary_category term="cs.CV" />
          </entry>
        </feed>
        """
        with patch.object(literature, "request_text", return_value=arxiv_atom):
            arxiv_papers = literature.search_arxiv("grounded evidence VQA", max_results=1)

        self.assertEqual(len(arxiv_papers), 1)
        self.assertEqual(arxiv_papers[0].url, "https://arxiv.org/abs/2601.00003")
        self.assertEqual(arxiv_papers[0].pdf_url, "https://arxiv.org/pdf/2601.00003")

        openalex_payload = {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "doi": "https://doi.org/10.1000/grounded-vqa",
                    "display_name": "Grounded Evidence Evaluation for VQA",
                    "publication_year": 2026,
                    "authorships": [{"author": {"display_name": "A. Researcher"}}],
                    "abstract_inverted_index": {"Evidence": [0], "faithfulness": [1]},
                    "primary_location": {
                        "landing_page_url": "https://publisher.example/paper",
                        "source": {"display_name": "CVPR"},
                    },
                    "best_oa_location": {"pdf_url": "https://repository.example/paper.pdf"},
                    "type": "article",
                    "cited_by_count": 12,
                },
            ],
        }
        with patch.object(literature, "request_text", return_value=json.dumps(openalex_payload)):
            openalex_papers = literature.search_openalex("grounded evidence VQA", max_results=1)

        self.assertEqual(len(openalex_papers), 1)
        self.assertEqual(openalex_papers[0].pdf_url, "https://repository.example/paper.pdf")

    def test_duplicate_candidates_keep_an_available_pdf_url(self) -> None:
        common = {
            "title": "Grounded Evidence Evaluation for Visual Question Answering",
            "year": "2026",
            "authors": "A. Researcher",
            "abstract": (
                "This visual question answering benchmark evaluates evidence faithfulness, "
                "visual grounding, and object hallucination in large vision-language models."
            ),
            "type": "Benchmark",
            "venue": "CVPR",
            "relation": "",
            "priority": "High",
        }
        candidates = [
            literature.PaperCandidate(
                **common,
                source="arxiv",
                url="https://arxiv.org/abs/2601.00003",
                pdf_url="",
            ),
            literature.PaperCandidate(
                **common,
                source="openalex",
                url="https://openalex.org/W123",
                pdf_url="https://repository.example/paper.pdf",
            ),
        ]

        ranked = literature.rank_and_deduplicate_result(
            candidates,
            "visual question answering evidence faithfulness hallucination",
        )

        self.assertEqual(len(ranked.papers), 1)
        self.assertEqual(ranked.papers[0].pdf_url, "https://repository.example/paper.pdf")

    def test_successful_open_pdf_resolution_records_provenance_without_embedding_text(self) -> None:
        pdf_url = "https://arxiv.org/pdf/2601.00003.pdf"
        extracted_text = "Method experiment dataset baseline ablation results. " * 40

        with patch.object(full_text, "download_pdf_bytes", return_value=b"%PDF-1.7 fixture") as download, patch.object(
            full_text,
            "extract_research_text_from_pdf",
            return_value=(extracted_text, 9),
        ):
            result = full_text.resolve_open_full_text(
                {
                    "title": "Grounded Evidence Evaluation for VQA",
                    "source": "arxiv",
                    "pdf_url": pdf_url,
                },
            )

        download.assert_called_once_with(pdf_url)
        self.assertEqual(result.status, "extracted")
        self.assertEqual(result.source, "arxiv_pdf")
        self.assertEqual(result.page_count, 9)
        self.assertEqual(result.character_count, len(extracted_text))
        self.assertTrue(result.is_extracted)
        provenance = result.to_provenance()
        self.assertNotIn("text", provenance)
        self.assertEqual(provenance["pdf_url"], pdf_url)

    def test_download_failure_is_reported_and_never_looks_extracted(self) -> None:
        pdf_url = "https://arxiv.org/pdf/2601.00003.pdf"
        with patch.object(
            full_text,
            "download_pdf_bytes",
            side_effect=full_text.FullTextFetchError("download_failed", "network timeout"),
        ), patch.object(full_text, "extract_research_text_from_pdf") as extract:
            result = full_text.resolve_open_full_text(
                {"source": "arxiv", "pdf_url": pdf_url},
            )

        extract.assert_not_called()
        self.assertEqual(result.status, "download_failed")
        self.assertFalse(result.is_extracted)
        self.assertEqual(result.character_count, 0)
        self.assertIn("network timeout", result.error)
        self.assertEqual(result.pdf_url, pdf_url)
        self.assertEqual(result.failure_stage, "download")
        self.assertTrue(result.recovery_hint)

    def test_short_or_missing_pdf_text_layer_is_parse_failed_not_full_text(self) -> None:
        short_text = "abstract-like text only"
        with patch.object(full_text, "download_pdf_bytes", return_value=b"%PDF-1.7 fixture"), patch.object(
            full_text,
            "extract_research_text_from_pdf",
            return_value=(short_text, 12),
        ):
            result = full_text.resolve_open_full_text(
                {"source": "openalex", "pdf_url": "https://repository.example/scan.pdf"},
            )

        self.assertEqual(result.status, "parse_failed")
        self.assertFalse(result.is_extracted)
        self.assertEqual(result.page_count, 12)
        self.assertEqual(result.character_count, len(short_text))
        self.assertIn(str(full_text.PDF_MIN_TEXT_CHARS), result.error)

    def test_user_provided_full_text_uses_same_status_enum_but_distinct_source(self) -> None:
        supplied = "Method experiment dataset metric baseline ablation result. " * 40

        result = full_text.provided_full_text(supplied)

        self.assertEqual(result.status, "extracted")
        self.assertEqual(result.source, "user_provided")
        self.assertTrue(result.is_extracted)
        self.assertEqual(result.pdf_url, "")

    def test_component_analysis_paper_is_not_misclassified_as_survey_from_incidental_review_words(self) -> None:
        from scholarflow_api.paper_card import extract_paper_signals

        signals = extract_paper_signals(
            title="A Comprehensive Analysis for Visual Object Hallucination in Large Vision-Language Models",
            abstract=(
                "We analyze component-level causes of visual object hallucination in large vision-language models, "
                "introduce a mitigation method, and develop a benchmark for evaluating hallucination."
            ),
            paper_text=(
                "Related work may review earlier hallucination benchmarks. "
                "Our method reduces hallucination through component-aware intervention. "
                "We introduce the VOH benchmark and evaluate against LLaVA baselines."
            ),
            venue="CVPR",
        )

        self.assertNotEqual(signals.contribution_type, "survey")
        self.assertIn(signals.contribution_type, {"analysis", "method", "benchmark"})
        self.assertTrue(signals.contribution_evidence)
        self.assertNotIn("Related work may review", signals.contribution_evidence)

    def test_method_and_claim_prefer_the_paper_own_contribution_over_prior_work(self) -> None:
        from scholarflow_api.paper_card import extract_paper_signals

        signals = extract_paper_signals(
            title="First Logit Boosting for Object Hallucination Mitigation",
            abstract=(
                "Although several approaches such as retraining and external grounding methods have been explored, "
                "they require expensive supervision. We introduce First Logit Boosting (FLB), a training-free "
                "decoding intervention for large vision-language models. We show that FLB reduces object "
                "hallucination while preserving answer accuracy on POPE."
            ),
            paper_text=(
                "[PDF page 2]\n[Section: related_work]\n"
                "Existing retraining methods improve benchmark accuracy but require additional data.\n"
                "[PDF page 4]\n[Section: method]\n"
                "We introduce First Logit Boosting (FLB), which amplifies visually grounded first-token logits.\n"
                "[PDF page 8]\n[Section: experiments]\n"
                "Baselines include LLaV A-1.5, InstructBLIP, and GPT-4V. "
                "We show that FLB reduces hallucination rate on POPE.\n"
            ),
            venue="CVPR",
        )

        self.assertEqual(signals.contribution_type, "method")
        self.assertIn("First Logit Boosting", signals.method)
        self.assertNotIn("several approaches", signals.method)
        self.assertIn("We show that FLB reduces", signals.claim)
        self.assertNotIn("Existing retraining methods", signals.claim)
        self.assertEqual(signals.baseline, "Baseline evidence: LLaVA-1.5, InstructBLIP, GPT-4V")

    def test_full_text_fields_remain_useful_when_author_does_not_state_a_limitation(self) -> None:
        from scholarflow_api.baseline_map import build_baseline_map
        from scholarflow_api.paper_card import generate_deep_paper_card
        from scholarflow_api.research_sight import build_research_sight

        paper = {
            "title": "First Logit Boosting for Object Hallucination Mitigation",
            "abstract": (
                "We introduce First Logit Boosting, a training-free decoding intervention. "
                "We show that it reduces object hallucination on COCO."
            ),
            "year": "2026",
            "venue": "CVPR",
            "source": "arxiv",
            "url": "https://arxiv.org/abs/flb",
        }
        full_text = (
            "[PDF page 4]\n[Section: method]\n"
            "We introduce First Logit Boosting (FLB), which amplifies visually grounded first-token logits.\n"
            "[PDF page 8]\n[Section: experiments]\n"
            "We evaluate our method on the COCO dataset. "
            "Baselines include VCD, ICD, and LLaVA-1.5. "
            "Evaluation metrics include CHAIRs, CHAIRi, and accuracy.\n"
            "[PDF page 9]\n[Section: results]\n"
            "We show that FLB reduces CHAIRs while preserving answer accuracy."
        )
        card = generate_deep_paper_card(paper, full_text)
        sight = build_research_sight(
            {**paper, "full_text": full_text, "evidence_level": "full_text"},
            [section.to_dict() for section in card.sections],
            build_baseline_map("object hallucination mitigation", [], []),
            "object hallucination mitigation",
            card.signals,
        )

        self.assertEqual(card.evidence_level, "full_text")
        self.assertNotIn("method", card.signals.missing_signals)
        self.assertNotIn("dataset", card.signals.missing_signals)
        self.assertNotIn("metric", card.signals.missing_signals)
        self.assertNotIn("baseline", card.signals.missing_signals)
        self.assertNotIn("claim", card.signals.missing_signals)
        self.assertIn("limitation", card.signals.missing_signals)
        self.assertEqual(card.signals.dataset, "COCO")
        self.assertIn("CHAIRs", card.signals.metric)
        self.assertIn("CHAIRi", card.signals.metric)
        self.assertIn("推断性弱假设", card.weakest_assumption)
        self.assertNotIn("无法判断", card.follow_up_idea)
        self.assertNotIn("无法判断", sight.solution_elegance)
        self.assertNotIn("无法判断", sight.evaluation_integrity)
        self.assertNotIn("无法判断", sight.why_good)
        self.assertTrue(
            any(
                item.field == "evaluation_integrity"
                and item.evidence_snippet_id != "none"
                for item in sight.critique_evidence
            )
        )

    def test_explicit_benchmark_construction_remains_a_benchmark(self) -> None:
        from scholarflow_api.paper_card import extract_paper_signals

        signals = extract_paper_signals(
            title="CounterHall: A Benchmark for Counterfactual Object Hallucination",
            abstract=(
                "We introduce CounterHall, a benchmark with paired counterfactual images and a new evaluation "
                "protocol. We evaluate LLaVA and InstructBLIP on the benchmark."
            ),
            paper_text="",
            venue="ACL",
        )

        self.assertEqual(signals.contribution_type, "benchmark")
        self.assertIn("CounterHall", signals.contribution_evidence)

    def test_analysis_title_cues_override_incidental_method_language(self) -> None:
        from scholarflow_api.paper_card import extract_paper_signals

        circuits = extract_paper_signals(
            title="Dual-Pathway Circuits for Multimodal Hallucination",
            abstract=(
                "We analyze two causal pathways that produce hallucinated objects. "
                "We use MagDiff to visualize their effects."
            ),
            paper_text="",
            venue="NeurIPS",
        )
        distractors = extract_paper_signals(
            title='What Makes "Good" Distractors for Vision-Language Evaluation?',
            abstract=(
                "We investigate how distractor construction changes evaluation conclusions. "
                "We first introduce the detailed experimental setup."
            ),
            paper_text="",
            venue="ACL",
        )

        self.assertEqual(circuits.contribution_type, "analysis")
        self.assertEqual(distractors.contribution_type, "analysis")
        self.assertNotIn("experimental setup", distractors.method)

    def test_named_owned_method_outranks_generic_method_usage(self) -> None:
        from scholarflow_api.baseline_map import infer_method_family
        from scholarflow_api.paper_card import extract_paper_signals

        signals = extract_paper_signals(
            title="DAMRO: Decoding-Aware Multimodal Reliability Optimization",
            abstract=(
                "We propose DAMRO, an attention-guided intervention for object hallucination. "
                "We use Contrastive Decoding in one comparison."
            ),
            paper_text=(
                "[PDF page 4]\n[Section: method]\n"
                "We use Contrastive Decoding as a comparison. "
                "We propose DAMRO to suppress attention outliers during generation."
            ),
            venue="ECCV",
        )

        self.assertIn("DAMRO", signals.method)
        self.assertNotIn("use Contrastive Decoding", signals.method)
        self.assertEqual(
            infer_method_family(
                {
                    "title": "DAMRO: Dive into the Attention Mechanism of LVLM to Reduce Object Hallucination",
                    "abstract": "",
                    "paper_signals": signals.to_dict(),
                },
            ),
            "attention-intervention",
        )

    def test_baseline_map_uses_owned_method_evidence_and_reports_full_text_coverage(self) -> None:
        selected = [
            {
                "title": "F-CLIPScore for Faithful Multimodal Evaluation",
                "abstract": (
                    "We introduce F-CLIPScore, an evaluation metric for faithful multimodal generation. "
                    "The experiments include diffusion models as evaluated systems."
                ),
                "year": "2026",
                "venue": "CVPR",
                "source": "arxiv",
                "url": "https://arxiv.org/abs/fclip",
                "full_text": (
                    "[PDF page 4]\n[Section: method]\n"
                    "We introduce F-CLIPScore as an evaluation metric based on region-text consistency."
                ),
                "full_text_provenance": {"status": "extracted", "source": "arxiv_pdf"},
                "paper_signals": {
                    "contribution_type": "benchmark",
                    "method": "We introduce F-CLIPScore as an evaluation metric.",
                },
            },
            {
                "title": "Mitigating Multilingual Hallucination with Logit Calibration",
                "abstract": (
                    "We propose multilingual logit calibration for hallucination mitigation. "
                    "State-space models are discussed as related architectures."
                ),
                "year": "2026",
                "venue": "ACL",
                "source": "arxiv",
                "url": "https://arxiv.org/abs/calibration",
                "full_text": (
                    "[PDF page 3]\n[Section: method]\n"
                    "We propose a decoding-time logit calibration method.\n"
                    "[PDF page 10]\n[Section: related_work]\n"
                    "State-space models provide an alternative sequence backbone."
                ),
                "full_text_provenance": {"status": "extracted", "source": "arxiv_pdf"},
                "paper_signals": {
                    "contribution_type": "method",
                    "method": "We propose a decoding-time logit calibration method.",
                },
            },
            {
                "title": "MambaVLM: State-Space Vision-Language Modeling",
                "abstract": "We propose a Mamba state-space architecture for vision-language modeling.",
                "year": "2025",
                "venue": "ICLR",
                "source": "arxiv",
                "url": "https://arxiv.org/abs/mambavlm",
                "paper_signals": {
                    "contribution_type": "method",
                    "method": "We propose a Mamba state-space architecture.",
                },
            },
        ]

        baseline_map = build_baseline_map("multimodal hallucination evaluation", [], selected)
        references = [
            *baseline_map.recent_strong_baselines,
            *baseline_map.classic_baselines,
            *baseline_map.alternative_paradigms,
        ]
        by_title = {reference.title: reference for reference in references}

        self.assertEqual(
            by_title["F-CLIPScore for Faithful Multimodal Evaluation"].method_family,
            "evaluation-metric",
        )
        self.assertEqual(
            by_title["Mitigating Multilingual Hallucination with Logit Calibration"].method_family,
            "decoding-intervention",
        )
        self.assertEqual(
            by_title["MambaVLM: State-Space Vision-Language Modeling"].method_family,
            "state-space",
        )
        self.assertEqual(baseline_map.classic_baselines, [])
        self.assertIn("full_text=2", baseline_map.evidence_summary)
        self.assertNotIn("`alternative_paradigm` 路线", " ".join(baseline_map.open_questions))

    def test_baseline_verification_separates_pdf_code_citation_and_reproduction_state(self) -> None:
        selected = [
            {
                "title": "Traceable Grounding Intervention",
                "abstract": "We propose a grounded decoding intervention and evaluate it on POPE.",
                "year": "2026",
                "venue": "CVPR",
                "source": "arxiv",
                "url": "https://arxiv.org/abs/traceable",
                "code": "Code: https://github.com/example/traceable-grounding",
                "full_text": (
                    "[PDF page 3]\n[Section: method]\n"
                    "We propose a grounded decoding intervention.\n"
                    "[PDF page 7]\n[Section: experiments]\n"
                    "Experiments use POPE, report accuracy, and compare with LLaVA-1.5."
                ),
                "full_text_provenance": {"status": "extracted", "source": "arxiv_pdf"},
                "paper_signals": {
                    "contribution_type": "method",
                    "method": "方法证据：We propose a grounded decoding intervention.",
                    "dataset": "POPE",
                    "metric": "accuracy",
                    "baseline": "Baseline evidence: LLaVA-1.5",
                },
            },
        ]

        baseline_map = build_baseline_map("grounded hallucination mitigation", [], selected)
        reference = baseline_map.recent_strong_baselines[0]
        verification = reference.verification

        self.assertEqual(verification.evidence_level, "full_text")
        self.assertEqual(verification.selection_basis, "full_text_method_evidence")
        self.assertEqual(verification.citation_status, "not_checked")
        self.assertEqual(verification.code_status, "link_present")
        self.assertEqual(verification.code_url, "https://github.com/example/traceable-grounding")
        self.assertEqual(verification.code_source, "metadata.code")
        self.assertEqual(verification.reproduction_status, "ready")
        self.assertTrue(all(value == "ready" for value in verification.checks.values()))
        self.assertEqual(verification.missing_evidence, [])
        self.assertIn("code_link=1/1", baseline_map.evidence_summary)
        self.assertIn("citation_graph_checked=0/1", baseline_map.evidence_summary)
        self.assertIn("ready=1", baseline_map.evidence_summary)

    def test_baseline_reproduction_stays_partial_without_code_and_blocked_without_pdf(self) -> None:
        selected = [
            {
                "title": "Full Text but No Repository",
                "abstract": "We propose a method evaluated on POPE with accuracy against LLaVA.",
                "year": "2026",
                "venue": "ACL",
                "source": "arxiv",
                "url": "https://arxiv.org/abs/no-code",
                "code": "unknown",
                "full_text": "[PDF page 4]\n[Section: experiments]\nWe evaluate on POPE with accuracy against LLaVA.",
                "full_text_provenance": {"status": "extracted", "source": "arxiv_pdf"},
                "paper_signals": {
                    "contribution_type": "method",
                    "method": "方法证据：We propose a method.",
                    "dataset": "POPE",
                    "metric": "accuracy",
                    "baseline": "Baseline evidence: LLaVA",
                },
            },
            {
                "title": "Abstract Candidate Only",
                "abstract": "We propose an evaluation method.",
                "year": "2026",
                "venue": "arXiv",
                "source": "arxiv",
                "url": "https://arxiv.org/abs/abstract-only",
                "code": "available",
                "paper_signals": {
                    "contribution_type": "method",
                    "method": "方法证据：We propose an evaluation method.",
                    "dataset": "当前证据不足：未发现明确 dataset/benchmark 名称",
                    "metric": "当前证据不足：未发现明确 metric/evaluation 指标",
                    "baseline": "当前证据不足：未发现 baseline",
                },
            },
        ]

        baseline_map = build_baseline_map("hallucination evaluation", [], selected)
        by_title = {
            reference.title: reference
            for reference in [
                *baseline_map.recent_strong_baselines,
                *baseline_map.classic_baselines,
                *baseline_map.alternative_paradigms,
            ]
        }

        full_text = by_title["Full Text but No Repository"].verification
        abstract_only = by_title["Abstract Candidate Only"].verification
        self.assertEqual(full_text.reproduction_status, "partial")
        self.assertEqual(full_text.checks["code"], "missing")
        self.assertIn("代码仓库链接", " ".join(full_text.missing_evidence))
        self.assertEqual(abstract_only.evidence_level, "abstract_only")
        self.assertEqual(abstract_only.code_status, "claimed_unverified")
        self.assertEqual(abstract_only.reproduction_status, "blocked")
        self.assertEqual(abstract_only.checks["full_text"], "missing")

    def test_baseline_code_link_can_be_traced_to_pdf_text(self) -> None:
        paper = {
            "title": "PDF Linked Method",
            "abstract": "We propose a grounded method.",
            "year": "2026",
            "venue": "CVPR",
            "source": "arxiv",
            "url": "https://arxiv.org/abs/pdf-linked",
            "code": "unknown",
            "full_text": (
                "[PDF page 1]\n[Section: front_matter]\n"
                "Code is available at https://github.com/example/pdf-linked-method.\n"
                "[PDF page 4]\n[Section: method]\nWe propose a grounded method."
            ),
            "full_text_provenance": {"status": "extracted", "source": "arxiv_pdf"},
            "paper_signals": {
                "contribution_type": "method",
                "method": "方法证据：We propose a grounded method.",
                "dataset": "POPE",
                "metric": "accuracy",
                "baseline": "Baseline evidence: LLaVA",
            },
        }

        verification = build_baseline_map("grounded method", [], [paper]).recent_strong_baselines[0].verification

        self.assertEqual(verification.code_status, "link_present")
        self.assertEqual(verification.code_source, "pdf.full_text")
        self.assertEqual(verification.code_url, "https://github.com/example/pdf-linked-method")
        self.assertEqual(verification.reproduction_status, "ready")

    def test_direction_reading_promotes_only_verified_extracted_text(self) -> None:
        paper = {
            "id": "paper_full_text_contract",
            "project_id": "project_full_text_contract",
            "title": "Grounded Evidence Evaluation for Visual Question Answering",
            "authors": "A. Researcher",
            "abstract": "We evaluate VQA evidence faithfulness and visual grounding.",
            "year": "2026",
            "type": "Benchmark",
            "venue": "CVPR",
            "source": "arxiv",
            "url": "https://arxiv.org/abs/2601.00003",
            "pdf_url": "https://arxiv.org/pdf/2601.00003.pdf",
            "relation": "Strong match for VQA evidence faithfulness.",
            "priority": "High",
            "code": "unknown",
            "relevance_score": 1.7,
            "relevance_quality": "strong",
            "matched_terms": ["VQA", "evidence faithfulness"],
            "review_required": False,
            "created_at": "2026-07-10T00:00:00+00:00",
        }
        extracted_text = (
            "Method: counterfactual grounding intervention. "
            "Dataset: POPE and A-OKVQA. Metric: accuracy and grounding faithfulness. "
            "Baseline: LLaVA and BLIP-2. Experiments include ablations and failure cases. "
        ) * 15
        extracted = full_text.FullTextResult(
            status="extracted",
            pdf_url=paper["pdf_url"],
            source="arxiv_pdf",
            page_count=11,
            character_count=len(extracted_text),
            text=extracted_text,
        )

        with patch(
            "scholarflow_api.direction_review.resolve_open_full_texts",
            return_value=[extracted],
        ) as resolve:
            readings = build_direction_readings(
                [paper],
                "visual question answering evidence faithfulness",
                build_baseline_map("visual question answering evidence faithfulness", [], []),
            )

        resolve.assert_called_once_with([paper])
        self.assertEqual(len(readings), 1)
        serialized = readings[0].to_dict()
        self.assertEqual(serialized["evidence_level"], "full_text")
        self.assertEqual(readings[0].source_text, extracted_text)
        self.assertNotIn("source_text", serialized)
        self.assertEqual(serialized["full_text"]["status"], "extracted")
        self.assertEqual(serialized["full_text"]["page_count"], 11)
        self.assertEqual(serialized["full_text"]["character_count"], len(extracted_text))
        self.assertNotIn("text", serialized["full_text"])
        self.assertNotIn("证据边界（abstract_only）", serialized["sections"][0]["content"])

    def test_direction_reading_keeps_download_failure_below_full_text(self) -> None:
        paper = {
            "id": "paper_failed_pdf_contract",
            "project_id": "project_full_text_contract",
            "title": "Grounded Evidence Evaluation for Visual Question Answering",
            "authors": "A. Researcher",
            "abstract": "We evaluate VQA evidence faithfulness and visual grounding.",
            "year": "2026",
            "type": "Benchmark",
            "venue": "CVPR",
            "source": "arxiv",
            "url": "https://arxiv.org/abs/2601.00004",
            "pdf_url": "https://arxiv.org/pdf/2601.00004.pdf",
            "relation": "Strong match for VQA evidence faithfulness.",
            "priority": "High",
            "code": "unknown",
            "relevance_score": 1.6,
            "relevance_quality": "strong",
            "matched_terms": ["VQA", "evidence faithfulness"],
            "review_required": False,
            "created_at": "2026-07-10T00:00:00+00:00",
        }
        failed = full_text.FullTextResult(
            status="download_failed",
            pdf_url=paper["pdf_url"],
            source="arxiv_pdf",
            error="network timeout",
        )

        with patch(
            "scholarflow_api.direction_review.resolve_open_full_texts",
            return_value=[failed],
        ):
            readings = build_direction_readings(
                [paper],
                "visual question answering evidence faithfulness",
                build_baseline_map("visual question answering evidence faithfulness", [], []),
            )

        serialized = readings[0].to_dict()
        self.assertEqual(serialized["evidence_level"], "abstract_only")
        self.assertEqual(serialized["full_text"]["status"], "download_failed")
        self.assertIn("network timeout", serialized["full_text"]["error"])
        section_contents = [section["content"] for section in serialized["sections"]]
        self.assertEqual(len(section_contents), 12)
        self.assertEqual(len(set(section_contents)), 12)
        self.assertTrue(all("证据边界（abstract_only）" not in content for content in section_contents))

    def test_paper_card_endpoint_auto_fetches_pdf_and_persists_truthful_failure_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                try:
                    from scholarflow_api import main as main_module
                except ModuleNotFoundError as error:
                    if error.name == "fastapi":
                        self.skipTest("FastAPI is not installed in the current Python environment.")
                    raise
                from scholarflow_api.database import init_db
                from scholarflow_api.schemas import LiteratureSearchRequest, PaperCardCreateRequest, ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Full-text Endpoint Contract", keyword="VQA evidence faithfulness"),
                )
                candidate = literature.PaperCandidate(
                    title="Grounded Evidence Evaluation for Visual Question Answering",
                    year="2026",
                    authors="A. Researcher",
                    abstract=(
                        "This visual question answering benchmark evaluates evidence faithfulness, "
                        "visual grounding, and object hallucination."
                    ),
                    type="Benchmark",
                    venue="CVPR",
                    source="arxiv",
                    url="https://arxiv.org/abs/2601.00003",
                    pdf_url="https://arxiv.org/pdf/2601.00003.pdf",
                    relation="Strong VQA evidence-faithfulness match.",
                    priority="High",
                    relevance_score=1.7,
                    relevance_quality="strong",
                    matched_terms=["VQA", "evidence faithfulness"],
                )
                search_result = literature.LiteratureSearchResult(
                    query=project.keyword,
                    expanded_queries=[project.keyword],
                    papers=[candidate],
                    errors=[],
                    relevance_coverage={
                        "candidate_count": 1,
                        "returned_count": 1,
                        "strong_match_count": 1,
                        "medium_match_count": 0,
                        "weak_match_count": 0,
                        "off_topic_count": 0,
                        "filtered_count": 0,
                    },
                )
                with patch.object(main_module, "search_literature", return_value=search_result):
                    search_response = main_module.search_project_literature(
                        project.id,
                        LiteratureSearchRequest(query=project.keyword, sources=["arxiv"]),
                    )

                persisted_paper = search_response.papers[0]
                self.assertEqual(persisted_paper.pdf_url, candidate.pdf_url)
                extracted_text = (
                    "Method: counterfactual visual grounding. Dataset: POPE and A-OKVQA. "
                    "Metric: grounding accuracy. Baseline: LLaVA. Experiments include ablation and failures. "
                ) * 15
                extracted = full_text.FullTextResult(
                    status="extracted",
                    pdf_url=candidate.pdf_url,
                    source="arxiv_pdf",
                    page_count=10,
                    character_count=len(extracted_text),
                    text=extracted_text,
                )
                failed = full_text.FullTextResult(
                    status="download_failed",
                    pdf_url=candidate.pdf_url,
                    source="arxiv_pdf",
                    error="network timeout",
                )

                with patch.object(
                    main_module,
                    "resolve_open_full_text",
                    side_effect=[extracted, failed],
                ) as resolve:
                    success_response = main_module.create_project_paper_card(
                        project.id,
                        PaperCardCreateRequest(paper_id=persisted_paper.id),
                    )
                    failed_response = main_module.create_project_paper_card(
                        project.id,
                        PaperCardCreateRequest(paper_id=persisted_paper.id),
                    )
                upload_payload = build_minimal_text_pdf()
                upload_response = main_module.extract_project_paper_full_text(
                    project.id,
                    persisted_paper.id,
                    upload_payload,
                )
                from scholarflow_api.api_helpers import fetch_project_paper_card_dicts
                from scholarflow_api.database import get_connection

                with get_connection() as connection:
                    active_cards = fetch_project_paper_card_dicts(connection, project.id)
                artifact_summaries = main_module.list_project_artifact_summaries(project.id)
                listed_cards = main_module.list_project_paper_cards(project.id)

        self.assertEqual(resolve.call_count, 2)
        for call in resolve.call_args_list:
            self.assertEqual(call.args[0]["pdf_url"], candidate.pdf_url)
        self.assertEqual(success_response.card.evidence_level, "full_text")
        self.assertEqual(success_response.card.full_text.status, "extracted")
        self.assertEqual(success_response.card.full_text.page_count, 10)
        success_artifact = json.loads(success_response.artifact.content_json)
        self.assertEqual(success_artifact["full_text"]["status"], "extracted")
        self.assertNotIn("text", success_artifact["full_text"])

        self.assertEqual(failed_response.card.evidence_level, "abstract_only")
        self.assertEqual(failed_response.card.full_text.status, "download_failed")
        self.assertIn("network timeout", failed_response.card.full_text.error)
        failed_artifact = json.loads(failed_response.artifact.content_json)
        self.assertEqual(failed_artifact["full_text"]["status"], "download_failed")
        self.assertNotEqual(failed_artifact["evidence_level"], "full_text")
        self.assertEqual(upload_response.paper_id, persisted_paper.id)
        self.assertEqual(upload_response.evidence_level, "full_text")
        self.assertEqual(upload_response.evidence_quality, "full_text")
        self.assertEqual(upload_response.source, "user_uploaded_pdf")
        self.assertEqual(upload_response.page_count, 1)
        self.assertGreaterEqual(upload_response.char_count, full_text.PDF_MIN_TEXT_CHARS)
        self.assertTrue(upload_response.updated_at)
        self.assertEqual(upload_response.full_text.status, "extracted")
        self.assertEqual(upload_response.full_text.source, "user_uploaded_pdf")
        self.assertIn("Method experiment dataset POPE", upload_response.text)
        self.assertIsNotNone(upload_response.card)
        self.assertIsNotNone(upload_response.artifact)
        self.assertEqual(upload_response.card.evidence_level, "full_text")
        self.assertEqual(upload_response.card.full_text.source, "user_uploaded_pdf")
        upload_artifact = json.loads(upload_response.artifact.content_json)
        self.assertEqual(upload_artifact["full_text"]["source"], "user_uploaded_pdf")
        self.assertEqual(upload_artifact["paper"]["id"], persisted_paper.id)
        bound_cards = [card for card in active_cards if card.get("paper_id") == persisted_paper.id]
        self.assertEqual(len(bound_cards), 1)
        self.assertEqual(bound_cards[0]["evidence_level"], "full_text")
        self.assertEqual(bound_cards[0]["full_text"]["source"], "user_uploaded_pdf")
        self.assertEqual(artifact_summaries[0].id, upload_response.artifact.id)
        self.assertEqual(len([card for card in listed_cards if card.paper_id == persisted_paper.id]), 1)
        self.assertEqual(listed_cards[0].paper_id, persisted_paper.id)
        self.assertEqual(listed_cards[0].evidence_level, "full_text")
        self.assertEqual(listed_cards[0].full_text.source, "user_uploaded_pdf")


if __name__ == "__main__":
    unittest.main()
