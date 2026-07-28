from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scholarflow_api import literature
from scholarflow_api.rag_retrieval import (
    EmbeddingError,
    LocalHashEmbeddingProvider,
    OpenRouterEmbeddingProvider,
    cosine_similarity,
    matched_retrieval_anchors,
    retrieval_anchor_terms,
    split_query_intent,
)


class CollisionEmbeddingProvider:
    """Simulate a hash collision so lexical gating, not vector luck, decides."""

    name = "local"
    model = "local/collision-test"
    dimensions = 8
    external_data_transfer = False

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] for _text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def candidate(
    *,
    title: str,
    abstract: str,
    url: str,
    matched_terms: list[str],
) -> literature.PaperCandidate:
    return literature.PaperCandidate(
        title=title,
        year="2026",
        authors="A. Researcher",
        abstract=abstract,
        type="Method",
        venue="CVPR",
        source="arxiv",
        url=url,
        pdf_url=f"{url.replace('/abs/', '/pdf/')}.pdf",
        relation="Strong match for the requested topic.",
        priority="High",
        relevance_score=1.8,
        relevance_quality="strong",
        matched_terms=matched_terms,
    )


class RagRetrievalContractTest(unittest.TestCase):
    def test_chinese_answer_instructions_do_not_pollute_retrieval_anchors(self) -> None:
        question = (
            "当前项目中请只返回可定位证据，分别说明 POPE、CHAIR 的数据集、"
            "指标、失败模式和 baseline，不要总结。"
        )

        intent = split_query_intent(question)
        anchors = retrieval_anchor_terms(question)

        self.assertEqual(
            intent["requested_facets"],
            ["dataset", "metric", "failure_mode", "baseline"],
        )
        self.assertIn("只返回证据", intent["answer_constraints"])
        self.assertIn("必须可定位", intent["answer_constraints"])
        self.assertIn("不要总结", intent["answer_constraints"])
        self.assertNotIn("当前项目中", intent["scientific_query"])
        self.assertNotIn("请只返回", intent["scientific_query"])
        self.assertTrue({"pope", "chair", "dataset", "metric", "failure mode", "baseline"}.issubset(anchors))
        self.assertTrue(
            {"请只", "只返", "返回", "回可", "可定", "定位", "证据"}.isdisjoint(anchors),
        )

    def test_bilingual_concept_aliases_match_in_both_directions(self) -> None:
        english_anchors = retrieval_anchor_terms(
            "How does visual grounding reduce object hallucination?"
        )
        english_to_chinese = matched_retrieval_anchors(
            english_anchors,
            "该方法使用反事实视觉定位来减少对象幻觉，并记录失败模式。",
        )
        self.assertTrue(
            {"visual", "grounding", "object", "hallucination"}.issubset(
                set(english_to_chinese)
            )
        )

        chinese_anchors = retrieval_anchor_terms(
            "对象幻觉如何被视觉定位缓解？"
        )
        chinese_to_english = matched_retrieval_anchors(
            chinese_anchors,
            (
                "Counterfactual visual grounding reduces object hallucination "
                "and exposes a measurable failure mode."
            ),
        )
        self.assertTrue(
            {"visual", "grounding", "object", "hallucination"}.issubset(
                set(chinese_to_english)
            )
        )

    def test_local_hash_embedding_is_deterministic_normalized_and_topic_sensitive(self) -> None:
        provider = LocalHashEmbeddingProvider(dimensions=256)
        relevant = provider.embed_query("对象幻觉 object hallucination visual grounding")
        repeated = provider.embed_query("对象幻觉 object hallucination visual grounding")
        related = provider.embed_query("counterfactual visual grounding reduces object hallucination")
        unrelated = provider.embed_query("marine archaeology isotope dating")

        self.assertEqual(relevant, repeated)
        self.assertEqual(len(relevant), 256)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in relevant)), 1.0)
        self.assertGreater(
            cosine_similarity(relevant, related),
            cosine_similarity(relevant, unrelated),
        )

    def test_project_search_lazily_embeds_chunks_and_returns_traceable_hybrid_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            environment = {
                "SCHOLARFLOW_DB_PATH": str(db_path),
                "SCHOLARFLOW_RAG_EMBEDDING_PROVIDER": "local",
                "SCHOLARFLOW_RAG_LOCAL_DIMENSIONS": "256",
            }
            with patch.dict(os.environ, environment):
                from scholarflow_api import main as main_module
                from scholarflow_api.database import init_db
                from scholarflow_api.schemas import (
                    LiteratureSearchRequest,
                    PaperChunkIndexRequest,
                    ProjectCreate,
                    RagEmbeddingRequest,
                    RagSearchRequest,
                )

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="RAG Retrieval", keyword="object hallucination"),
                )
                papers = [
                    candidate(
                        title="Counterfactual Grounding for Object Hallucination",
                        abstract=(
                            "We reduce object hallucination using counterfactual visual grounding "
                            "and evaluate localized evidence faithfulness."
                        ),
                        url="https://arxiv.org/abs/2601.00021",
                        matched_terms=["object hallucination", "visual grounding"],
                    ),
                    candidate(
                        title="Efficient Protein Structure Alignment",
                        abstract=(
                            "We align protein structures with a molecular graph optimization method "
                            "for biological sequence analysis."
                        ),
                        url="https://arxiv.org/abs/2601.00022",
                        matched_terms=["alignment"],
                    ),
                ]
                search_result = literature.LiteratureSearchResult(
                    query=project.keyword,
                    expanded_queries=[project.keyword],
                    papers=papers,
                    errors=[],
                    relevance_coverage={
                        "candidate_count": 2,
                        "eligible_count": 2,
                        "returned_count": 2,
                        "truncated_count": 0,
                        "strong_match_count": 2,
                        "medium_match_count": 0,
                        "weak_match_count": 0,
                        "off_topic_count": 0,
                        "filtered_count": 0,
                    },
                )
                with patch("scholarflow_api.services.workflow_runtime.search_literature", return_value=search_result):
                    literature_response = main_module.search_project_literature(
                        project.id,
                        LiteratureSearchRequest(query=project.keyword),
                    )

                before = main_module.get_project_rag_index_status(project.id)
                self.assertEqual(before.embedding_status, "not_started")
                response = main_module.search_project_rag(
                    project.id,
                    RagSearchRequest(
                        query="object hallucination counterfactual visual grounding",
                        top_k=4,
                    ),
                )

                self.assertEqual(response.status, "complete")
                self.assertEqual(response.retrieval_mode, "hybrid")
                self.assertEqual(response.provider, "local_lexical_hash")
                self.assertEqual(response.embedding_model, "local/lexical-hash-v1")
                self.assertEqual(response.embedding_dimensions, 256)
                self.assertFalse(response.external_data_transfer)
                self.assertGreaterEqual(response.returned_hits, 1)
                self.assertTrue(response.query_anchor_terms)
                self.assertEqual(response.lexical_backend, "sqlite_fts5_bm25")
                self.assertEqual(response.embedding_channel, "lexical_hash")
                self.assertIn("lexical hash 不是语义 embedding", response.score_explanation)
                grounding_paper = next(
                    paper
                    for paper in literature_response.papers
                    if paper.title == "Counterfactual Grounding for Object Hallucination"
                )
                self.assertEqual(response.hits[0].paper_id, grounding_paper.id)
                self.assertEqual(response.hits[0].source, "metadata.abstract")
                self.assertEqual(response.hits[0].evidence_level, "abstract_only")
                self.assertIn(response.hits[0].paper_id, response.hits[0].citation_id)
                self.assertIn("chunk-0", response.hits[0].citation_id)
                self.assertGreater(response.hits[0].hybrid_score, response.min_score)
                self.assertIn(
                    response.hits[0].match_strength,
                    {"strong", "moderate", "borderline"},
                )
                self.assertIn("关键词分", response.hits[0].match_explanation)
                self.assertTrue(response.hits[0].matched_query_terms)

                after = main_module.get_project_rag_index_status(project.id)
                self.assertEqual(after.embedding_status, "partial")
                self.assertLess(after.embedded_chunks, after.total_chunks)
                self.assertEqual(after.embedding_model, "local/lexical-hash-v1")
                self.assertEqual(after.embedding_dimensions, 256)

                completed_embedding = main_module.embed_project_rag_index(
                    project.id,
                    RagEmbeddingRequest(force=False),
                )
                self.assertEqual(completed_embedding.status, "ready")
                self.assertGreaterEqual(completed_embedding.embedded_chunks, 1)
                self.assertEqual(
                    completed_embedding.embedded_chunks + completed_embedding.skipped_chunks,
                    after.total_chunks,
                )

                paper_run = main_module.embed_project_paper_rag_index(
                    project.id,
                    grounding_paper.id,
                    RagEmbeddingRequest(force=True),
                )
                self.assertEqual(paper_run.status, "ready")
                self.assertEqual(paper_run.requested_chunks, 1)
                self.assertEqual(paper_run.embedded_chunks, 1)

                full_text = (
                    "[PDF page 4]\n"
                    "[Section: method]\n"
                    + (
                        "The counterfactual grounding module binds generated objects to localized "
                        "visual evidence before decoding and records the intervention trace. "
                    )
                    * 18
                    + "\n[PDF page 9]\n"
                    "[Section: experiments]\n"
                    + (
                        "Experiments report object hallucination rate and grounding accuracy on "
                        "POPE with ablations and explicit failure cases. "
                    )
                    * 18
                )
                rebuilt = main_module.rebuild_project_paper_rag_index(
                    project.id,
                    grounding_paper.id,
                    PaperChunkIndexRequest(paper_text=full_text),
                )
                self.assertEqual(rebuilt.evidence_level, "abstract_only")
                self.assertEqual(rebuilt.source, "metadata.abstract")
                self.assertEqual(rebuilt.embedding_status, "ready")
                self.assertIn("未经过 PDF", rebuilt.message)
                full_text_hit = main_module.search_project_rag(
                    project.id,
                    RagSearchRequest(
                        query="counterfactual grounding module intervention trace",
                        paper_ids=[grounding_paper.id],
                        evidence_levels=["full_text"],
                        sections=["method"],
                    ),
                )
                self.assertEqual(full_text_hit.status, "no_reliable_hit")
                self.assertEqual(full_text_hit.hits, [])

                no_hit = main_module.search_project_rag(
                    project.id,
                    RagSearchRequest(
                        query="volcanic archaeology isotope dendrochronology",
                        min_score=0.3,
                    ),
                )
                self.assertEqual(no_hit.status, "no_reliable_hit")
                self.assertEqual(no_hit.hits, [])
                self.assertTrue(any("最小相关性阈值" in warning for warning in no_hit.warnings))

                with patch(
                    "scholarflow_api.rag_retrieval.get_embedding_provider",
                    return_value=CollisionEmbeddingProvider(),
                ):
                    collision_no_hit = main_module.search_project_rag(
                        project.id,
                        RagSearchRequest(
                            query="medical image segmentation Dice score",
                            min_score=0.18,
                        ),
                    )
                self.assertEqual(collision_no_hit.status, "no_reliable_hit")
                self.assertEqual(collision_no_hit.hits, [])
                self.assertGreaterEqual(
                    collision_no_hit.rejected_by_relevance_gate,
                    1,
                )
                self.assertTrue(
                    any("query anchor" in warning for warning in collision_no_hit.warnings)
                )

                openapi_paths = main_module.app.openapi()["paths"]
                self.assertIn("/projects/{project_id}/rag-search", openapi_paths)
                self.assertIn("/projects/{project_id}/rag-index/embeddings", openapi_paths)
                self.assertIn(
                    "/projects/{project_id}/papers/{paper_id}/rag-index/embeddings",
                    openapi_paths,
                )

    def test_search_is_project_isolated_and_can_fall_back_to_lexical_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(
                os.environ,
                {
                    "SCHOLARFLOW_DB_PATH": str(db_path),
                    "SCHOLARFLOW_RAG_EMBEDDING_PROVIDER": "disabled",
                },
            ):
                from scholarflow_api import main as main_module
                from scholarflow_api.database import get_connection, init_db, utc_now
                from scholarflow_api.rag_index import index_paper_abstract
                from scholarflow_api.schemas import ProjectCreate, RagEmbeddingRequest, RagSearchRequest

                init_db()
                first = main_module.create_project(ProjectCreate(title="First project"))
                second = main_module.create_project(ProjectCreate(title="Second project"))
                now = utc_now()
                with get_connection() as connection:
                    for project_id, paper_id, title, abstract in [
                        (
                            first.id,
                            "paper_first_rag",
                            "Grounded Hallucination Evaluation",
                            "Object hallucination evaluation uses visual grounding evidence.",
                        ),
                        (
                            second.id,
                            "paper_second_rag",
                            "Protein Folding",
                            "Protein folding predicts molecular structures.",
                        ),
                    ]:
                        connection.execute(
                            """
                            INSERT INTO papers (
                                id, project_id, title, authors, abstract, year, type,
                                venue, source, url, pdf_url, relation, priority, code,
                                relevance_score, relevance_quality, matched_terms_json,
                                review_required, created_at
                            )
                            VALUES (?, ?, ?, '', ?, '2026', 'Method', 'Test', 'fixture',
                                    '', '', '', 'High', '', 1.0, 'strong', '[]', 0, ?)
                            """,
                            (paper_id, project_id, title, abstract, now),
                        )
                        index_paper_abstract(
                            connection,
                            project_id=project_id,
                            paper_id=paper_id,
                            abstract=abstract,
                            source_origin="fixture",
                            now=now,
                        )

                response = main_module.search_project_rag(
                    first.id,
                    RagSearchRequest(
                        query="object hallucination visual grounding",
                        refresh_embeddings=True,
                    ),
                )
                self.assertEqual(response.status, "partial")
                self.assertEqual(response.retrieval_mode, "lexical_only")
                self.assertEqual(response.candidate_chunks, 1)
                self.assertEqual(response.hits[0].paper_id, "paper_first_rag")
                self.assertTrue(any("禁用" in warning for warning in response.warnings))
                embedding_attempt = main_module.embed_project_rag_index(
                    first.id,
                    RagEmbeddingRequest(),
                )
                self.assertEqual(embedding_attempt.status, "failed")
                self.assertEqual(embedding_attempt.requested_chunks, 1)
                self.assertEqual(embedding_attempt.failed_chunks, 1)

    def test_openrouter_embedding_request_is_batched_auditable_and_tls_verified(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(
            {
                "model": "qwen/qwen3-embedding-8b",
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                    {"index": 1, "embedding": [0.2, 0.3, 0.4]},
                ],
            }
        ).encode("utf-8")
        context = object()
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "test-key",
                "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
                "OPENROUTER_RAG_MODEL": "qwen/qwen3-embedding-8b",
                "SCHOLARFLOW_RAG_EMBEDDING_BATCH_SIZE": "16",
            },
        ), patch(
            "scholarflow_api.rag_retrieval.certifi.where",
            return_value="/private/tmp/ca-certificates.pem",
        ) as certifi_where, patch(
            "scholarflow_api.rag_retrieval.ssl.create_default_context",
            return_value=context,
        ) as create_context, patch(
            "scholarflow_api.rag_retrieval.open_url",
            return_value=response,
        ) as urlopen:
            provider = OpenRouterEmbeddingProvider()
            vectors = provider.embed_documents(["first chunk", "second chunk"])

        self.assertEqual(vectors, [[0.1, 0.2, 0.3], [0.2, 0.3, 0.4]])
        self.assertEqual(provider.dimensions, 3)
        request = urlopen.call_args.args[0]
        request_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/embeddings")
        self.assertEqual(request_payload["model"], "qwen/qwen3-embedding-8b")
        self.assertEqual(request_payload["input_type"], "search_document")
        self.assertEqual(request_payload["input"], ["first chunk", "second chunk"])
        self.assertEqual(urlopen.call_args.kwargs["context"], context)
        certifi_where.assert_called_once_with()
        create_context.assert_called_once_with(cafile="/private/tmp/ca-certificates.pem")

    def test_openrouter_without_key_does_not_send_paper_text(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "",
                "OPENROUTER_RAG_MODEL": "qwen/qwen3-embedding-8b",
            },
        ), patch(
            "scholarflow_api.rag_retrieval.open_url",
        ) as urlopen:
            provider = OpenRouterEmbeddingProvider()
            with self.assertRaisesRegex(EmbeddingError, "未向外部服务发送"):
                provider.embed_documents(["private unpublished paper text"])

        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
