from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scholarflow_api.rag_answer import (
    OpenRouterRagAnswerGenerator,
    RagGenerationError,
    validate_generated_claims,
)


def citation_fixture() -> dict[str, object]:
    return {
        "rank": 1,
        "citation_id": "paper_grounding:experiments:p.9:chunk-2",
        "paper_id": "paper_grounding",
        "paper_title": "Counterfactual Grounding for Object Hallucination",
        "paper_authors": "A. Researcher",
        "paper_year": "2026",
        "paper_venue": "CVPR",
        "paper_url": "https://example.org/paper",
        "chunk_id": "chunk_grounding",
        "chunk_index": 2,
        "chunk_hash": "abc123",
        "source": "pdf.full_text",
        "source_origin": "user_uploaded_pdf",
        "evidence_level": "full_text",
        "section": "experiments",
        "page_start": 9,
        "page_end": 9,
        "text": (
            "On the POPE benchmark, counterfactual grounding reduces object hallucination "
            "rate by 12% while preserving answer accuracy."
        ),
        "lexical_score": 0.7,
        "vector_score": 0.8,
        "hybrid_score": 0.77,
    }


class RagAnswerContractTest(unittest.TestCase):
    def test_local_rag_answer_returns_traceable_extractive_evidence_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(
                os.environ,
                {
                    "SCHOLARFLOW_DB_PATH": str(db_path),
                    "SCHOLARFLOW_RAG_EMBEDDING_PROVIDER": "local",
                    "SCHOLARFLOW_RAG_GENERATION_PROVIDER": "local",
                },
            ):
                from scholarflow_api import main as main_module
                from scholarflow_api.database import get_connection, init_db, utc_now
                from scholarflow_api.rag_index import index_paper_full_text
                from scholarflow_api.schemas import ProjectCreate, RagAnswerRequest

                init_db()
                project = main_module.create_project(
                    ProjectCreate(
                        title="Grounded RAG Answer",
                        keyword="object hallucination",
                    ),
                )
                paper_id = "paper_rag_answer"
                now = utc_now()
                full_text = (
                    "[PDF page 4]\n"
                    "[Section: method]\n"
                    + (
                        "The counterfactual grounding module binds each generated object to "
                        "localized visual evidence before decoding. "
                    )
                    * 14
                    + "\n[PDF page 9]\n"
                    "[Section: experiments]\n"
                    + (
                        "Experiments on POPE report object hallucination rate, grounding accuracy, "
                        "ablations, and explicit failure cases. "
                    )
                    * 14
                )
                with get_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO papers (
                            id, project_id, title, authors, abstract, year, type,
                            venue, source, url, pdf_url, relation, priority, code,
                            relevance_score, relevance_quality, matched_terms_json,
                            review_required, created_at
                        )
                        VALUES (?, ?, ?, 'A. Researcher', ?, '2026', 'Method',
                                'CVPR', 'fixture', 'https://example.org/paper', '',
                                'Direct topic match', 'High', '', 1.8, 'strong',
                                '["object hallucination"]', 0, ?)
                        """,
                        (
                            paper_id,
                            project.id,
                            "Counterfactual Grounding for Object Hallucination",
                            "Counterfactual grounding reduces object hallucination.",
                            now,
                        ),
                    )
                    index_paper_full_text(
                        connection,
                        project_id=project.id,
                        paper_id=paper_id,
                        text=full_text,
                        source_origin="user_uploaded_pdf",
                        now=now,
                    )

                response = main_module.create_project_rag_answer(
                    project.id,
                    RagAnswerRequest(
                        query="How does counterfactual grounding address object hallucination?",
                        top_k=4,
                        evidence_levels=["full_text"],
                    ),
                )

                self.assertEqual(response.status, "partial")
                self.assertEqual(response.answer_kind, "extractive_evidence")
                self.assertEqual(response.generation_provider, "local")
                self.assertEqual(response.generation_model, "extractive-evidence-v1")
                self.assertFalse(response.external_data_transfer)
                self.assertIsNotNone(response.quality_assessment)
                self.assertEqual(
                    response.quality_assessment.quality_status,
                    "review_required",
                )
                self.assertTrue(
                    any(
                        "检索匹配强度偏低" in item
                        for item in response.quality_assessment.risk_flags
                    )
                )
                self.assertTrue(response.quality_assessment.human_review_required)
                self.assertGreaterEqual(len(response.claims), 1)
                self.assertGreaterEqual(len(response.citations), 1)
                self.assertEqual(
                    response.citation_validation.used_citation_ids,
                    [item for claim in response.claims for item in claim.citation_ids],
                )
                first_citation = response.citations[0]
                self.assertEqual(first_citation.paper_id, paper_id)
                self.assertEqual(first_citation.evidence_level, "full_text")
                self.assertIn(first_citation.citation_id, response.answer)
                self.assertTrue(
                    any(
                        citation.page_start in {4, 9}
                        and citation.section in {"method", "experiments"}
                        for citation in response.citations
                    )
                )
                self.assertIsNotNone(response.artifact)
                self.assertTrue(response.artifact.title.startswith("rag_answer_"))
                artifact_payload = json.loads(response.artifact.content_json)
                self.assertEqual(artifact_payload["schema_version"], "rag_answer.v2")
                self.assertEqual(
                    artifact_payload["citation_validation"]["used_citation_ids"],
                    response.citation_validation.used_citation_ids,
                )
                self.assertEqual(
                    artifact_payload["quality_assessment"]["evaluation_id"],
                    response.quality_assessment.evaluation_id,
                )

                evaluations = main_module.get_project_rag_evaluations(project.id)
                self.assertEqual(evaluations.total, 1)
                self.assertEqual(
                    evaluations.evaluations[0].id,
                    response.quality_assessment.evaluation_id,
                )
                self.assertEqual(
                    evaluations.evaluations[0].answer_artifact_id,
                    response.artifact.id,
                )
                other_project = main_module.create_project(
                    ProjectCreate(title="Evaluation isolation"),
                )
                self.assertEqual(
                    main_module.get_project_rag_evaluations(other_project.id).total,
                    0,
                )

                openapi_paths = main_module.app.openapi()["paths"]
                self.assertIn("/projects/{project_id}/rag-answer", openapi_paths)
                self.assertIn("/projects/{project_id}/rag-evaluations", openapi_paths)

    def test_no_reliable_hit_refuses_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(
                os.environ,
                {
                    "SCHOLARFLOW_DB_PATH": str(db_path),
                    "SCHOLARFLOW_RAG_GENERATION_PROVIDER": "openrouter",
                    "OPENROUTER_API_KEY": "test-key",
                },
            ):
                from scholarflow_api import main as main_module
                from scholarflow_api.database import init_db
                from scholarflow_api.schemas import ProjectCreate, RagAnswerRequest

                init_db()
                project = main_module.create_project(ProjectCreate(title="Empty RAG"))
                with patch.object(
                    OpenRouterRagAnswerGenerator,
                    "generate",
                ) as generate:
                    response = main_module.create_project_rag_answer(
                        project.id,
                        RagAnswerRequest(query="unsupported question"),
                    )

                self.assertEqual(response.status, "no_reliable_hit")
                self.assertEqual(response.answer_kind, "no_answer")
                self.assertEqual(response.answer, "")
                self.assertEqual(response.claims, [])
                self.assertEqual(response.citations, [])
                self.assertEqual(
                    response.quality_assessment.quality_status,
                    "safe_refusal",
                )
                self.assertIsNone(response.quality_assessment.score)
                self.assertFalse(response.quality_assessment.human_review_required)
                generate.assert_not_called()

    def test_citation_validator_rejects_unknown_and_unsupported_numeric_claims(self) -> None:
        citation = citation_fixture()
        valid_id = str(citation["citation_id"])
        result = validate_generated_claims(
            {
                "claims": [
                    {
                        "statement": (
                            "Counterfactual grounding reduces object hallucination rate by 12% on POPE."
                        ),
                        "citation_ids": [valid_id],
                    },
                    {
                        "statement": (
                            "Counterfactual grounding reduces object hallucination rate by 35% on POPE."
                        ),
                        "citation_ids": [valid_id],
                    },
                    {
                        "statement": "An unsupported benchmark conclusion.",
                        "citation_ids": ["invented:citation"],
                    },
                ]
            },
            citations=[citation],
        )

        self.assertEqual(len(result["claims"]), 1)
        self.assertEqual(result["claims"][0]["citation_ids"], [valid_id])
        self.assertEqual(result["rejected_claim_count"], 2)
        self.assertEqual(result["rejected_citation_ids"], ["invented:citation"])
        self.assertEqual(result["used_citation_ids"], [valid_id])

    def test_citation_validator_rejects_positive_claim_from_negated_evidence(self) -> None:
        citation = citation_fixture()
        citation["text"] = (
            "On the POPE benchmark, counterfactual grounding does not reduce "
            "object hallucination rate."
        )
        valid_id = str(citation["citation_id"])

        result = validate_generated_claims(
            {
                "claims": [
                    {
                        "statement": (
                            "Counterfactual grounding reduces object hallucination rate on POPE."
                        ),
                        "citation_ids": [valid_id],
                    },
                ],
            },
            citations=[citation],
        )

        self.assertEqual(result["claims"], [])
        self.assertEqual(result["rejected_claim_count"], 1)
        self.assertEqual(result["used_citation_ids"], [])

    def test_openrouter_generation_uses_strict_evidence_payload_and_verified_tls(self) -> None:
        citation = citation_fixture()
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "claims": [
                                        {
                                            "statement": (
                                                "Counterfactual grounding reduces object hallucination "
                                                "rate by 12% on POPE."
                                            ),
                                            "citation_ids": [citation["citation_id"]],
                                        }
                                    ],
                                    "unanswered_parts": ["Cross-model generalization is unknown."],
                                }
                            )
                        }
                    }
                ]
            }
        ).encode("utf-8")
        context = object()
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "test-key",
                "OPENROUTER_RAG_ANSWER_MODEL": "test/grounded-model",
                "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
            },
        ), patch(
            "scholarflow_api.rag_answer.certifi.where",
            return_value="/private/tmp/ca-certificates.pem",
        ) as certifi_where, patch(
            "scholarflow_api.rag_answer.ssl.create_default_context",
            return_value=context,
        ) as create_context, patch(
            "scholarflow_api.rag_answer.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            generator = OpenRouterRagAnswerGenerator()
            payload = generator.generate(
                question="What changes on POPE?",
                language="en",
                citations=[citation],
            )

        self.assertEqual(payload["claims"][0]["citation_ids"], [citation["citation_id"]])
        request = urlopen.call_args.args[0]
        request_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request_payload["model"], "test/grounded-model")
        user_payload = json.loads(request_payload["messages"][1]["content"])
        self.assertEqual(user_payload["question"], "What changes on POPE?")
        self.assertEqual(
            user_payload["evidence_blocks"][0]["citation_id"],
            citation["citation_id"],
        )
        self.assertNotIn("embedding", user_payload["evidence_blocks"][0])
        self.assertEqual(urlopen.call_args.kwargs["context"], context)
        certifi_where.assert_called_once_with()
        create_context.assert_called_once_with(cafile="/private/tmp/ca-certificates.pem")

    def test_openrouter_without_key_does_not_send_question_or_evidence(self) -> None:
        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": ""},
        ), patch(
            "scholarflow_api.rag_answer.urllib.request.urlopen",
        ) as urlopen:
            generator = OpenRouterRagAnswerGenerator()
            with self.assertRaisesRegex(RagGenerationError, "未向外部生成模型发送"):
                generator.generate(
                    question="private research question",
                    language="en",
                    citations=[citation_fixture()],
                )

        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
