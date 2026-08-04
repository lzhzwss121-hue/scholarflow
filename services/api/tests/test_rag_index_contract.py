from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scholarflow_api import full_text, literature
from scholarflow_api.rag_index import build_paper_chunks


def structured_full_text() -> str:
    method = (
        "We propose a counterfactual visual grounding method that binds every generated claim "
        "to localized image evidence and records the causal intervention. "
    ) * 12
    experiments = (
        "Experiments evaluate the method on POPE and ObjectScope with grounding accuracy, "
        "hallucination rate, ablation studies, and explicit failure cases. "
    ) * 12
    return (
        "[PDF page 3]\n"
        "[Section: method]\n"
        f"{method}\n\n"
        "[PDF page 8]\n"
        "[Section: experiments]\n"
        f"{experiments}"
    )


def paper_candidate() -> literature.PaperCandidate:
    return literature.PaperCandidate(
        title="Counterfactual Grounding for Object Hallucination",
        year="2026",
        authors="A. Researcher",
        abstract=(
            "We evaluate object hallucination with counterfactual visual grounding evidence "
            "and report a reproducible benchmark."
        ),
        type="Benchmark",
        venue="CVPR",
        source="arxiv",
        url="https://arxiv.org/abs/2601.00011",
        pdf_url="https://arxiv.org/pdf/2601.00011.pdf",
        relation="Strong object-hallucination and grounding match.",
        priority="High",
        relevance_score=1.8,
        relevance_quality="strong",
        matched_terms=["object hallucination", "visual grounding"],
    )


class RagIndexContractTest(unittest.TestCase):
    def test_chunker_preserves_page_section_and_stable_checksums(self) -> None:
        text = structured_full_text()
        first = build_paper_chunks(
            project_id="project_rag",
            paper_id="paper_rag",
            text=text,
            source="pdf.full_text",
            source_origin="user_uploaded_pdf",
            evidence_level="full_text",
            evidence_verified=True,
            doi="",
            arxiv_id="2601.00011",
            openalex_id="",
            title="Counterfactual Grounding for Object Hallucination",
            parser_version="pypdf.v1",
            canonical_work_id="title:counterfactual-grounding",
            now="2026-07-18T00:00:00Z",
            chunk_size=420,
            overlap=60,
        )
        second = build_paper_chunks(
            project_id="project_rag",
            paper_id="paper_rag",
            text=text,
            source="pdf.full_text",
            source_origin="user_uploaded_pdf",
            evidence_level="full_text",
            evidence_verified=True,
            doi="",
            arxiv_id="2601.00011",
            openalex_id="",
            title="Counterfactual Grounding for Object Hallucination",
            parser_version="pypdf.v1",
            canonical_work_id="title:counterfactual-grounding",
            now="2026-07-19T00:00:00Z",
            chunk_size=420,
            overlap=60,
        )

        self.assertGreaterEqual(len(first), 4)
        self.assertEqual([chunk.chunk_hash for chunk in first], [chunk.chunk_hash for chunk in second])
        self.assertEqual([chunk.chunk_index for chunk in first], list(range(len(first))))
        self.assertEqual({chunk.page_start for chunk in first}, {3, 8})
        self.assertEqual({chunk.section for chunk in first}, {"method", "experiments"})
        self.assertTrue(all(chunk.page_start == chunk.page_end for chunk in first))
        self.assertTrue(all("[PDF page" not in chunk.chunk_text for chunk in first))
        self.assertTrue(all("[Section:" not in chunk.chunk_text for chunk in first))
        self.assertTrue(all(chunk.embedding_model == "" and chunk.embedding_json == "" for chunk in first))

    def test_search_indexes_abstract_and_verified_full_text_replaces_it_without_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api import main as main_module
                from scholarflow_api.database import get_connection, init_db
                from scholarflow_api.schemas import LiteratureSearchRequest, PaperCardCreateRequest, ProjectCreate

                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="RAG Phase One", keyword="object hallucination"),
                )
                candidate = paper_candidate()
                search_result = literature.LiteratureSearchResult(
                    query=project.keyword,
                    expanded_queries=[project.keyword],
                    papers=[candidate],
                    errors=[],
                    relevance_coverage={
                        "candidate_count": 1,
                        "eligible_count": 1,
                        "returned_count": 1,
                        "truncated_count": 0,
                        "strong_match_count": 1,
                        "medium_match_count": 0,
                        "weak_match_count": 0,
                        "off_topic_count": 0,
                        "filtered_count": 0,
                    },
                )
                with patch("scholarflow_api.services.literature_service.search_literature", return_value=search_result):
                    search_response = main_module.search_project_literature(
                        project.id,
                        LiteratureSearchRequest(query=project.keyword, sources=["arxiv"]),
                    )

                paper = search_response.papers[0]
                abstract_status = main_module.get_paper_rag_index_status(project.id, paper.id)
                abstract_chunks = main_module.list_project_paper_chunks(project.id, paper.id)
                self.assertEqual(abstract_status.status, "indexed")
                self.assertEqual(abstract_status.evidence_level, "abstract_only")
                self.assertEqual(abstract_status.source, "metadata.abstract")
                self.assertEqual(len(abstract_chunks), 1)

                source_text = structured_full_text()
                extracted = full_text.FullTextResult(
                    status="extracted",
                    pdf_url=candidate.pdf_url,
                    source="arxiv_pdf",
                    page_count=10,
                    character_count=len(source_text),
                    text=source_text,
                )
                with patch("scholarflow_api.services.workflow_runtime.resolve_open_full_text", return_value=extracted):
                    main_module.create_project_paper_card(
                        project.id,
                        PaperCardCreateRequest(paper_id=paper.id),
                    )

                full_status = main_module.get_paper_rag_index_status(project.id, paper.id)
                full_chunks = main_module.list_project_paper_chunks(project.id, paper.id)
                self.assertEqual(full_status.status, "indexed")
                self.assertEqual(full_status.evidence_level, "full_text")
                self.assertEqual(full_status.source, "pdf.full_text")
                self.assertEqual(full_status.source_origin, "arxiv_pdf")
                self.assertEqual(full_status.embedding_status, "not_started")
                self.assertEqual(set(full_status.page_numbers), {3, 8})
                self.assertEqual({chunk.section for chunk in full_chunks}, {"method", "experiments"})
                self.assertTrue(all(chunk.embedding_model == "" for chunk in full_chunks))

                with patch("scholarflow_api.services.literature_service.search_literature", return_value=search_result):
                    main_module.search_project_literature(
                        project.id,
                        LiteratureSearchRequest(query=project.keyword, sources=["arxiv"]),
                    )
                preserved = main_module.get_paper_rag_index_status(project.id, paper.id)
                self.assertEqual(preserved.evidence_level, "full_text")
                self.assertEqual(preserved.chunk_count, len(full_chunks))

                manual_rebuild = main_module.rebuild_project_paper_rag_index(
                    project.id,
                    paper.id,
                    main_module.PaperChunkIndexRequest(paper_text=source_text),
                )
                self.assertEqual(manual_rebuild.status, "indexed")
                self.assertEqual(manual_rebuild.evidence_level, "full_text")
                self.assertEqual(manual_rebuild.source, "pdf.full_text")
                self.assertEqual(manual_rebuild.source_origin, "arxiv_pdf")
                self.assertIn("未经过 PDF", manual_rebuild.message)
                self.assertIn("已有高等级索引未被删除", manual_rebuild.message)

                failed_rebuild = main_module.rebuild_project_paper_rag_index(
                    project.id,
                    paper.id,
                    main_module.PaperChunkIndexRequest(paper_text="too short"),
                )
                self.assertEqual(failed_rebuild.status, "indexed")
                self.assertEqual(failed_rebuild.evidence_level, "full_text")
                self.assertEqual(failed_rebuild.source, "pdf.full_text")
                self.assertIn("已有高等级索引未被删除", failed_rebuild.message)

                project_status = main_module.get_project_rag_index_status(project.id)
                self.assertEqual(project_status.total_papers, 1)
                self.assertEqual(project_status.indexed_papers, 1)
                self.assertEqual(project_status.total_chunks, len(full_chunks))
                self.assertEqual(project_status.full_text_chunks, len(full_chunks))
                self.assertEqual(project_status.abstract_chunks, 0)
                self.assertEqual(project_status.embedding_status, "not_started")

                openapi_paths = main_module.app.openapi()["paths"]
                self.assertIn("/projects/{project_id}/rag-index", openapi_paths)
                self.assertIn("/projects/{project_id}/papers/{paper_id}/rag-index", openapi_paths)
                self.assertIn("/projects/{project_id}/papers/{paper_id}/chunks", openapi_paths)
                self.assertIn(
                    "delete",
                    openapi_paths["/projects/{project_id}/papers/{paper_id}/rag-index"],
                )

                with get_connection() as connection:
                    columns = {
                        row["name"]
                        for row in connection.execute("PRAGMA table_info(paper_chunks)").fetchall()
                    }
                self.assertTrue(
                    {
                        "paper_id",
                        "section",
                        "page_start",
                        "page_end",
                        "chunk_hash",
                        "embedding_model",
                        "embedding_json",
                    }.issubset(columns),
                )

                cleared = main_module.delete_project_paper_rag_index(project.id, paper.id)
                self.assertEqual(cleared.status, "not_indexed")
                self.assertEqual(cleared.chunk_count, 0)
                self.assertIn("论文、Paper Card 与 Memory 保持不变", cleared.message)


if __name__ == "__main__":
    unittest.main()
