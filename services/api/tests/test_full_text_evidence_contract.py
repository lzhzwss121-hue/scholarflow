from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scholarflow_api import full_text, literature
from scholarflow_api.baseline_map import build_baseline_map
from scholarflow_api.direction_review import build_direction_readings


class FullTextEvidenceContractTest(unittest.TestCase):
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
                uploaded = full_text.FullTextResult(
                    status="extracted",
                    source="user_uploaded_pdf",
                    page_count=12,
                    character_count=len(extracted_text),
                    text=extracted_text,
                )
                with patch.object(main_module, "parse_pdf_bytes", return_value=uploaded) as parse_upload:
                    upload_response = main_module.extract_project_paper_full_text(
                        project.id,
                        persisted_paper.id,
                        b"%PDF-1.7 upload fixture",
                    )

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
        parse_upload.assert_called_once_with(b"%PDF-1.7 upload fixture", source="user_uploaded_pdf")
        self.assertEqual(upload_response.paper_id, persisted_paper.id)
        self.assertEqual(upload_response.full_text.status, "extracted")
        self.assertEqual(upload_response.full_text.source, "user_uploaded_pdf")
        self.assertEqual(upload_response.text, extracted_text)
        self.assertIsNotNone(upload_response.card)
        self.assertIsNotNone(upload_response.artifact)
        self.assertEqual(upload_response.card.evidence_level, "full_text")
        self.assertEqual(upload_response.card.full_text.source, "user_uploaded_pdf")
        upload_artifact = json.loads(upload_response.artifact.content_json)
        self.assertEqual(upload_artifact["full_text"]["source"], "user_uploaded_pdf")


if __name__ == "__main__":
    unittest.main()
