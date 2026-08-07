from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from scholarflow_api.full_text import parse_pdf_bytes as real_parse_pdf_bytes
from scholarflow_api.rag_index import (
    build_paper_chunks,
    index_paper_full_text as real_index_paper_full_text,
)
from scholarflow_api.real_paper_dataset import RealPaperDataset
from scholarflow_api.real_paper_evaluation import (
    RealPaperPredictionSet,
    evaluate_real_paper_predictions,
)
from scholarflow_api.real_paper_prediction_runner import (
    load_runtime_cases,
    run_real_paper_predictions,
)
from scholarflow_api.services.rag_service import (
    create_project_rag_answer as real_create_project_rag_answer,
)


def _build_fixed_pdf(path: Path) -> tuple[bytes, str]:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    for page_number in (1, 2):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        finding = (
            "Method Alpha reports an error rate of 12 percent on Dataset A. "
            "The comparison uses the official Dataset A test split. "
        )
        body = finding + (
            "Method Alpha Dataset A error rate reproducibility baselines ablations "
            "limitations and comparison details are reported for audit. "
            * 16
        )
        escaped = body.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        heading = "Results" if page_number == 1 else "Limitations"
        stream.set_data(
            f"BT /F1 10 Tf 14 TL 20 740 Td ({heading}) Tj T* ({escaped}) Tj ET".encode(
                "latin-1"
            )
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    payload = buffer.getvalue()
    path.write_bytes(payload)
    return payload, hashlib.sha256(payload).hexdigest()


class RealPaperEndToEndContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temporary.name)
        self.pdf_path = self.root / "fixed-paper.pdf"
        self.pdf_bytes, self.source_hash = _build_fixed_pdf(self.pdf_path)
        self.paper_id = "arxiv-2602.12345"
        self.paper_version = "2602.12345v1"
        self.project_id = "real-paper-e2e-project"
        self.source_url = "https://arxiv.org/abs/2602.12345v1"

        extracted = real_parse_pdf_bytes(
            self.pdf_bytes,
            pdf_url=self.source_url,
            source="user_uploaded_pdf",
        )
        chunks = build_paper_chunks(
            project_id=self.project_id,
            paper_id=self.paper_id,
            text=extracted.text,
            source="pdf.full_text",
            source_origin="user_uploaded_pdf",
            evidence_level="full_text",
            evidence_verified=True,
            doi="",
            arxiv_id="2602.12345",
            openalex_id="",
            title="Fixed Offline Method Alpha Paper",
            parser_version="pypdf.v1",
            canonical_work_id="arxiv:2602.12345",
            now="2026-08-07T00:00:00Z",
        )
        self.gold_chunk = next(
            chunk
            for chunk in chunks
            if chunk.page_start == 1 and "12 percent" in chunk.chunk_text
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _answerable_case(self) -> dict[str, object]:
        semantic = {
            "kind": "table",
            "value": "Table 1, Method Alpha row",
            "page": 1,
            "section": "Results",
            "paragraph": "",
            "table": "Table 1",
            "figure": "",
            "equation": "",
            "supplementary": False,
        }
        return {
            "case_id": "e2e-answerable",
            "project_id": self.project_id,
            "paper_id": self.paper_id,
            "title": "Fixed Offline Method Alpha Paper",
            "paper_version": self.paper_version,
            "source_url": self.source_url,
            "source_hash": self.source_hash,
            "source_page_count": 2,
            "domain": "offline-contract",
            "question": "What error rate does Method Alpha report on Dataset A?",
            "answerability": "answerable",
            "gold_claim": "Method Alpha reports an error rate of 12 percent on Dataset A.",
            "evidence_type": "table",
            "evidence_level": "full_text",
            "evidence_excerpt": "Method Alpha reports an error rate of 12 percent on Dataset A.",
            "evidence_locator": semantic,
            "page": 1,
            "normalized_section": "results",
            "evidence_excerpt_hash": "",
            "semantic_locator": semantic,
            "acceptable_source_anchors": [
                {
                    "paper_id": self.paper_id,
                    "paper_version": self.paper_version,
                    "source_hash": self.source_hash,
                    "page": 1,
                    "normalized_section": "results",
                    "chunk_hash": self.gold_chunk.chunk_hash,
                    "evidence_excerpt_hash": "",
                    "status": "verified",
                }
            ],
            "acceptable_citations": [
                {
                    "citation_id": "human-gold-id-not-produced-at-runtime",
                    "paper_id": self.paper_id,
                    "paper_version": self.paper_version,
                    "source_hash": self.source_hash,
                    "page": 1,
                    "section": "Results",
                    "locator": semantic,
                }
            ],
            "direct_support_found": True,
            "contradiction_notes": [],
            "contradiction_claims": [],
            "version_notes": "Fixed synthetic PDF contract resource.",
            "annotator_a_result": None,
            "annotator_b_result": None,
            "disagreement_fields": [],
            "adjudicator_result": None,
            "adjudication_date": None,
            "review_status": "draft",
            "label_origin": "human_draft",
            "split": "test",
            "case_types": ["answerable", "table", "dataset_metric"],
        }

    def _refusal_case(self) -> dict[str, object]:
        case = self._answerable_case()
        paragraph = {
            "kind": "paragraph",
            "value": "No Dataset Z evidence",
            "page": 1,
            "section": "Results",
            "paragraph": "absence check",
            "table": "",
            "figure": "",
            "equation": "",
            "supplementary": False,
        }
        case.update(
            {
                "case_id": "e2e-refusal",
                "question": "What quantum chemistry result is reported for Dataset Z?",
                "answerability": "refusal",
                "gold_claim": "",
                "evidence_type": "main_text",
                "evidence_excerpt": "",
                "evidence_locator": paragraph,
                "semantic_locator": paragraph,
                "acceptable_source_anchors": [],
                "acceptable_citations": [],
                "direct_support_found": False,
                "case_types": ["refusal", "no_reliable_hit"],
            }
        )
        return case

    def _write_inputs(
        self,
        cases: list[dict[str, object]],
        *,
        include_resource: bool = True,
    ) -> tuple[Path, Path, Path]:
        cases_path = self.root / "cases.json"
        resources_path = self.root / "resources.json"
        output_path = self.root / "predictions.json"
        cases_path.write_text(
            json.dumps(
                {
                    "schema_version": "real_paper_dataset.v2",
                    "dataset_id": "real-paper-e2e-contract",
                    "evaluation_tier": "real_paper_unreviewed",
                    "description": "Synthetic fixed-PDF end-to-end contract.",
                    "target_case_count": 50,
                    "cases": cases,
                }
            ),
            encoding="utf-8",
        )
        resources = []
        if include_resource:
            resources.append(
                {
                    "paper_id": self.paper_id,
                    "title": "Fixed Offline Method Alpha Paper",
                    "doi": "",
                    "arxiv_id": "2602.12345",
                    "openalex_id": "",
                    "version": self.paper_version,
                    "source_url": self.source_url,
                    "local_path": str(self.pdf_path),
                    "cache_identifier": "fixed/e2e-paper.pdf",
                    "sha256": self.source_hash,
                    "page_count": 2,
                }
            )
        resources_path.write_text(
            json.dumps(
                {
                    "schema_version": "real_paper_resources.v1",
                    "manifest_id": "real-paper-e2e-resources",
                    "resources": resources,
                }
            ),
            encoding="utf-8",
        )
        return cases_path, resources_path, output_path

    def _run(self, cases: list[dict[str, object]]) -> tuple[RealPaperDataset, RealPaperPredictionSet]:
        cases_path, resources_path, output_path = self._write_inputs(cases)
        dataset = RealPaperDataset.model_validate_json(cases_path.read_text(encoding="utf-8"))
        predictions = run_real_paper_predictions(
            cases_path=cases_path,
            resources_path=resources_path,
            output_path=output_path,
            work_dir=self.root / "work",
            top_k=1,
        )
        return dataset, predictions

    def test_pdf_rag_prediction_evaluation_uses_machine_anchor_not_citation_id(self) -> None:
        cases_path, resources_path, output_path = self._write_inputs(
            [self._answerable_case()]
        )
        with (
            patch(
                "scholarflow_api.real_paper_prediction_runner.parse_pdf_bytes",
                wraps=real_parse_pdf_bytes,
            ) as parser,
            patch(
                "scholarflow_api.real_paper_prediction_runner.index_paper_full_text",
                wraps=real_index_paper_full_text,
            ) as indexer,
            patch(
                "scholarflow_api.services.rag_service.create_project_rag_answer",
                wraps=real_create_project_rag_answer,
            ) as rag_service,
        ):
            predictions = run_real_paper_predictions(
                cases_path=cases_path,
                resources_path=resources_path,
                output_path=output_path,
                work_dir=self.root / "work-e2e",
                top_k=1,
            )
        parser.assert_called_once()
        indexer.assert_called_once()
        rag_service.assert_called_once()

        prediction = predictions.cases[0]
        self.assertTrue(prediction.retrieved_citations)
        self.assertNotEqual(
            prediction.retrieved_citations[0].citation_id,
            "human-gold-id-not-produced-at-runtime",
        )
        self.assertIsNone(prediction.retrieved_citations[0].semantic_locator)

        dataset = RealPaperDataset.model_validate_json(
            cases_path.read_text(encoding="utf-8")
        )
        report = evaluate_real_paper_predictions(
            dataset,
            predictions,
            allow_unreviewed=True,
        )
        self.assertEqual(report["metrics"]["recall_at_5"], 1.0)
        self.assertEqual(report["metrics"]["source_identity_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["page_locator_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["machine_anchor_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["citation_precision"], 1.0)
        self.assertIsNone(report["metrics"]["semantic_locator_accuracy"])
        self.assertIsNone(report["metrics"]["table_locator_accuracy"])

    def test_wrong_paper_source_hash_and_page_are_rejected_independently(self) -> None:
        dataset, predictions = self._run([self._answerable_case()])
        for field, value, metric in (
            ("paper_id", "wrong-paper", "source_identity_accuracy"),
            ("source_hash", "f" * 64, "source_identity_accuracy"),
            ("page", 2, "page_locator_accuracy"),
        ):
            payload = predictions.model_dump(mode="json")
            for key in ("retrieved_citations", "used_citations"):
                for citation in payload["cases"][0][key]:
                    if field == "paper_id":
                        citation["paper_id"] = value
                    citation["machine_locator"][field] = value
                    if field == "page":
                        citation["page"] = value
            report = evaluate_real_paper_predictions(
                dataset,
                RealPaperPredictionSet.model_validate(payload),
                allow_unreviewed=True,
            )
            self.assertEqual(report["metrics"][metric], 0.0)
            self.assertEqual(report["metrics"]["citation_precision"], 0.0)

    def test_semantic_table_accuracy_requires_explicit_structured_locator(self) -> None:
        dataset, predictions = self._run([self._answerable_case()])
        payload = predictions.model_dump(mode="json")
        semantic = dataset.cases[0].semantic_locator.model_dump(mode="json")
        for key in ("retrieved_citations", "used_citations"):
            for citation in payload["cases"][0][key]:
                citation["semantic_locator"] = semantic
                citation["locator"] = semantic
        report = evaluate_real_paper_predictions(
            dataset,
            RealPaperPredictionSet.model_validate(payload),
            allow_unreviewed=True,
        )
        self.assertEqual(report["metrics"]["machine_anchor_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["semantic_locator_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["table_locator_accuracy"], 1.0)

    def test_gold_projection_refusal_and_batch_failure_contracts(self) -> None:
        answerable = self._answerable_case()
        answerable["acceptable_source_anchors"][0]["chunk_hash"] = "GOLD-ANCHOR-POISON"
        cases_path, _, _ = self._write_inputs([answerable])
        runtime = load_runtime_cases(cases_path)
        serialized = json.dumps(runtime.model_dump(mode="json"))
        self.assertNotIn("GOLD-ANCHOR-POISON", serialized)
        self.assertNotIn("acceptable_source_anchors", serialized)

        refusal_cases, refusal_resources, refusal_output = self._write_inputs(
            [self._refusal_case()]
        )
        refusal_predictions = run_real_paper_predictions(
            cases_path=refusal_cases,
            resources_path=refusal_resources,
            output_path=refusal_output,
            work_dir=self.root / "work-refusal",
            top_k=1,
            min_score=1.0,
        )
        refusal = refusal_predictions.cases[0]
        self.assertTrue(refusal.refused)
        self.assertEqual(refusal.used_citations, [])
        self.assertEqual(refusal.claims, [])

        missing = self._answerable_case()
        missing.update(
            {
                "case_id": "e2e-missing-resource",
                "project_id": "missing-project",
                "paper_id": "arxiv-9999.00001",
                "title": "Missing Fixed Paper",
                "paper_version": "9999.00001v1",
                "source_url": "https://arxiv.org/abs/9999.00001v1",
                "source_hash": "9" * 64,
                "acceptable_source_anchors": [],
                "acceptable_citations": [],
                "answerability": "refusal",
                "gold_claim": "",
                "direct_support_found": False,
                "case_types": ["refusal", "no_reliable_hit"],
            }
        )
        cases_path, resources_path, output_path = self._write_inputs(
            [self._answerable_case(), missing]
        )
        batch = run_real_paper_predictions(
            cases_path=cases_path,
            resources_path=resources_path,
            output_path=output_path,
            work_dir=self.root / "work-batch",
        )
        batch_by_id = {prediction.case_id: prediction for prediction in batch.cases}
        self.assertIn(
            batch_by_id["e2e-answerable"].execution_status,
            {"complete", "partial"},
        )
        self.assertEqual(
            batch_by_id["e2e-missing-resource"].execution_status,
            "blocked",
        )


if __name__ == "__main__":
    unittest.main()
