from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from scholarflow_api.rag_answer import answer_project_rag as real_answer_project_rag
from scholarflow_api.real_paper_evaluation import RealPaperPredictionSet
from scholarflow_api.real_paper_prediction_runner import (
    FORBIDDEN_GOLD_FIELDS,
    RealPaperResourceManifest,
    load_runtime_cases,
    run_real_paper_predictions,
)


def build_text_pdf(path: Path, *, method: str, dataset: str, result: str) -> str:
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
        evidence = (
            f"{method} reports {result} on {dataset}. "
            f"The evaluation for {dataset} uses the same split and metric. "
        )
        body = evidence + (
            f"Page {page_number} reproducibility context for {method} on {dataset} "
            "covers baselines ablations limitations and comparison details. "
            * 14
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
    return hashlib.sha256(payload).hexdigest()


def case_payload(
    *,
    case_id: str,
    project_id: str,
    paper_id: str,
    title: str,
    source: str,
    version: str,
    source_hash: str,
    question: str,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "project_id": project_id,
        "domain": "offline-contract",
        "paper_id": paper_id,
        "title": title,
        "source_url": source,
        "paper_version": version,
        "source_hash": source_hash,
        "source_page_count": 2,
        "question": question,
        "answerable": True,
        "gold_claim": "GOLD-POISON must never enter the RAG runtime",
        "gold_answer": "GOLD-ANSWER-POISON",
        "acceptable_citations": [{"citation_id": "GOLD-CITATION-POISON"}],
        "expected_refusal": False,
        "contradiction_annotations": ["GOLD-CONTRADICTION-POISON"],
        "evaluator_notes": "GOLD-EVALUATOR-NOTE-POISON",
        "adjudication_result": "GOLD-ADJUDICATION-POISON",
    }


def dataset_payload(cases: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "real_paper_dataset.v2",
        "dataset_id": "runner-contract-cases",
        "evaluation_tier": "real_paper_unreviewed",
        "description": "Runner-only contract fixture with poison gold labels.",
        "cases": cases,
    }


def resource_payload(
    *,
    paper_id: str,
    title: str,
    source_url: str,
    version: str,
    local_path: Path,
    sha256: str,
    arxiv_id: str,
    page_count: int = 2,
) -> dict[str, object]:
    return {
        "paper_id": paper_id,
        "title": title,
        "doi": "",
        "arxiv_id": arxiv_id,
        "openalex_id": "",
        "version": version,
        "source_url": source_url,
        "local_path": str(local_path),
        "cache_identifier": f"contract-cache/{paper_id}/{version}",
        "sha256": sha256,
        "page_count": page_count,
    }


class RealPaperPredictionRunnerContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temporary.name)

        self.paper_a_path = self.root / "paper-a.pdf"
        self.paper_b_path = self.root / "paper-b.pdf"
        self.paper_a_hash = build_text_pdf(
            self.paper_a_path,
            method="Method Alpha",
            dataset="Dataset A",
            result="an error rate of 12 percent",
        )
        self.paper_b_hash = build_text_pdf(
            self.paper_b_path,
            method="Method Beta",
            dataset="Dataset B",
            result="an accuracy of 81 percent",
        )
        self.case_a = case_payload(
            case_id="case-a",
            project_id="project-a",
            paper_id="arxiv-2601.00001",
            title="Method Alpha Evaluation",
            source="https://arxiv.org/abs/2601.00001",
            version="2601.00001v2",
            source_hash=self.paper_a_hash,
            question="What error rate does Method Alpha report on Dataset A?",
        )
        self.case_b = case_payload(
            case_id="case-b",
            project_id="project-b",
            paper_id="arxiv-2601.00002",
            title="Method Beta Evaluation",
            source="https://arxiv.org/abs/2601.00002",
            version="2601.00002v1",
            source_hash=self.paper_b_hash,
            question="What accuracy does Method Beta report on Dataset B?",
        )
        self.resource_a = resource_payload(
            paper_id="arxiv-2601.00001",
            title="Method Alpha Evaluation",
            source_url="https://arxiv.org/abs/2601.00001",
            version="2601.00001v2",
            local_path=self.paper_a_path,
            sha256=self.paper_a_hash,
            arxiv_id="2601.00001",
        )
        self.resource_b = resource_payload(
            paper_id="arxiv-2601.00002",
            title="Method Beta Evaluation",
            source_url="https://arxiv.org/abs/2601.00002",
            version="2601.00002v1",
            local_path=self.paper_b_path,
            sha256=self.paper_b_hash,
            arxiv_id="2601.00002",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_inputs(
        self,
        *,
        cases: list[dict[str, object]] | None = None,
        resources: list[dict[str, object]] | None = None,
        suffix: str = "run",
    ) -> tuple[Path, Path, Path]:
        cases_path = self.root / f"cases-{suffix}.json"
        resources_path = self.root / f"resources-{suffix}.json"
        output_path = self.root / f"predictions-{suffix}.json"
        cases_path.write_text(
            json.dumps(dataset_payload(cases or [self.case_a]), ensure_ascii=False),
            encoding="utf-8",
        )
        resources_path.write_text(
            json.dumps(
                {
                    "schema_version": "real_paper_resources.v1",
                    "manifest_id": f"resources-{suffix}",
                    "cache_root": "",
                    "resources": resources or [self.resource_a],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return cases_path, resources_path, output_path

    def run_inputs(
        self,
        *,
        cases: list[dict[str, object]] | None = None,
        resources: list[dict[str, object]] | None = None,
        suffix: str = "run",
    ) -> RealPaperPredictionSet:
        cases_path, resources_path, output_path = self.write_inputs(
            cases=cases,
            resources=resources,
            suffix=suffix,
        )
        return run_real_paper_predictions(
            cases_path=cases_path,
            resources_path=resources_path,
            output_path=output_path,
            work_dir=self.root / f"work-{suffix}",
        )

    def test_prediction_schema_and_real_rag_service_output(self) -> None:
        with patch(
            "scholarflow_api.services.workflow_runtime.answer_project_rag",
            wraps=real_answer_project_rag,
        ) as rag_service:
            predictions = self.run_inputs()

        rag_service.assert_called_once()
        parsed = RealPaperPredictionSet.model_validate(predictions.model_dump())
        schema = RealPaperPredictionSet.model_json_schema()
        self.assertIn("offline_system_run", schema["properties"]["prediction_source"]["enum"])
        self.assertIn("PredictionRuntimeMetadata", schema["$defs"])
        self.assertIn("PredictionSourceIdentity", schema["$defs"])
        self.assertEqual(parsed.prediction_source, "offline_system_run")
        prediction = parsed.cases[0]
        self.assertIn(prediction.execution_status, {"complete", "partial"})
        self.assertFalse(prediction.refused)
        self.assertTrue(prediction.answer)
        self.assertTrue(prediction.retrieved_citations)
        citation = prediction.retrieved_citations[0]
        self.assertEqual(citation.project_id, "project-a")
        self.assertEqual(citation.paper_id, "arxiv-2601.00001")
        self.assertEqual(citation.evidence_level, "full_text")
        self.assertTrue(citation.evidence_verified)
        self.assertIsNotNone(citation.page)
        self.assertEqual(citation.section, "results")
        self.assertEqual(citation.locator.kind, "chunk")
        self.assertIn("sha256:", citation.locator.value)
        self.assertEqual(prediction.source_identity.sha256, self.paper_a_hash)
        self.assertEqual(prediction.source_identity.page_count, 2)
        self.assertEqual(
            prediction.runtime_metadata.rag_service,
            "workflow_runtime.create_project_rag_answer",
        )
        self.assertFalse(prediction.runtime_metadata.external_data_transfer)

    def test_gold_fields_never_enter_runtime_query_context_or_database(self) -> None:
        cases_path, resources_path, output_path = self.write_inputs(suffix="leakage")
        runtime_cases = load_runtime_cases(cases_path)
        serialized_runtime = json.dumps(
            [item.model_dump() for item in runtime_cases.cases],
            ensure_ascii=False,
            sort_keys=True,
        )
        for field in FORBIDDEN_GOLD_FIELDS:
            self.assertNotIn(field, serialized_runtime)
        self.assertNotIn("GOLD-POISON", serialized_runtime)

        def guarded_answer(connection, **kwargs):
            boundary = json.dumps(kwargs, ensure_ascii=False, default=str)
            persisted = " ".join(
                str(value)
                for table in ("projects", "papers", "paper_chunks")
                for row in connection.execute(f"SELECT * FROM {table}").fetchall()
                for value in row
            )
            combined = boundary + persisted
            self.assertNotIn("GOLD-", combined)
            for field in FORBIDDEN_GOLD_FIELDS:
                self.assertNotIn(field, boundary)
            return real_answer_project_rag(connection, **kwargs)

        with patch(
            "scholarflow_api.services.workflow_runtime.answer_project_rag",
            side_effect=guarded_answer,
        ) as rag_service:
            run_real_paper_predictions(
                cases_path=cases_path,
                resources_path=resources_path,
                output_path=output_path,
                work_dir=self.root / "work-leakage",
            )
        rag_service.assert_called_once()

    def test_cases_use_isolated_databases_and_preserve_project_binding(self) -> None:
        predictions = self.run_inputs(
            cases=[self.case_a, self.case_b],
            resources=[self.resource_a, self.resource_b],
            suffix="isolation",
        )
        self.assertEqual(len(predictions.cases), 2)
        isolation_ids = {
            prediction.runtime_metadata.database_isolation_id
            for prediction in predictions.cases
        }
        self.assertEqual(len(isolation_ids), 2)
        for prediction in predictions.cases:
            self.assertTrue(
                all(
                    citation.project_id == prediction.project_id
                    for citation in prediction.retrieved_citations
                )
            )

    def test_hash_and_version_mismatches_are_blocked_before_rag(self) -> None:
        wrong_hash = {**self.resource_a, "sha256": "0" * 64}
        with patch(
            "scholarflow_api.services.workflow_runtime.create_project_rag_answer"
        ) as rag_service:
            hash_result = self.run_inputs(resources=[wrong_hash], suffix="hash")
        rag_service.assert_not_called()
        self.assertEqual(hash_result.cases[0].execution_status, "blocked")
        self.assertIn("SHA-256", hash_result.cases[0].error)

        wrong_version = {**self.resource_a, "version": "2601.00001v1"}
        with patch(
            "scholarflow_api.services.workflow_runtime.create_project_rag_answer"
        ) as rag_service:
            version_result = self.run_inputs(resources=[wrong_version], suffix="version")
        rag_service.assert_not_called()
        self.assertEqual(version_result.cases[0].execution_status, "blocked")
        self.assertIn("version", version_result.cases[0].error.lower())

    def test_missing_full_text_is_blocked_and_batch_continues(self) -> None:
        missing = {
            **self.resource_b,
            "local_path": str(self.root / "missing-paper.pdf"),
        }
        predictions = self.run_inputs(
            cases=[self.case_a, self.case_b],
            resources=[self.resource_a, missing],
            suffix="partial-batch",
        )
        by_case = {item.case_id: item for item in predictions.cases}
        self.assertIn(by_case["case-a"].execution_status, {"complete", "partial"})
        self.assertEqual(by_case["case-b"].execution_status, "blocked")
        self.assertTrue(by_case["case-b"].refused)
        self.assertEqual(by_case["case-b"].claims, [])
        self.assertIn("missing", by_case["case-b"].error.lower())

    def test_repeated_runs_are_deterministic(self) -> None:
        first = self.run_inputs(suffix="deterministic-a")
        second = self.run_inputs(suffix="deterministic-b")
        self.assertEqual(
            first.model_dump(mode="json"),
            second.model_dump(mode="json"),
        )

    def test_unrelated_manifest_never_falls_back_to_schema_fixture(self) -> None:
        unrelated = {**self.resource_b, "paper_id": "unrelated-paper"}
        predictions = self.run_inputs(resources=[unrelated], suffix="no-fallback")
        prediction = predictions.cases[0]
        self.assertEqual(predictions.prediction_source, "offline_system_run")
        self.assertEqual(prediction.execution_status, "blocked")
        self.assertEqual(prediction.retrieved_citations, [])
        self.assertEqual(prediction.used_citations, [])
        self.assertNotEqual(predictions.prediction_source, "offline_test_fixture")

    def test_manifest_schema_rejects_resources_without_stable_identity(self) -> None:
        invalid = {**self.resource_a, "arxiv_id": ""}
        with self.assertRaises(ValueError):
            RealPaperResourceManifest.model_validate(
                {
                    "schema_version": "real_paper_resources.v1",
                    "manifest_id": "invalid",
                    "resources": [invalid],
                }
            )


if __name__ == "__main__":
    unittest.main()
