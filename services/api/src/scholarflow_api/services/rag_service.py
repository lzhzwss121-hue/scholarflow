from __future__ import annotations

import json

from scholarflow_api.api_helpers import (
    ensure_active_session,
    ensure_project_exists,
    fetch_paper_dict,
    fetch_project_dict,
    insert_artifact_row,
)
from scholarflow_api.database import get_connection, new_id, utc_now
from scholarflow_api.full_text import provided_full_text, resolve_open_full_text
from scholarflow_api.paper_card import paper_slug
from scholarflow_api.rag_answer import answer_project_rag, render_rag_answer_markdown
from scholarflow_api.rag_evaluation import (
    assess_rag_answer,
    insert_rag_evaluation,
    list_rag_evaluations,
)
from scholarflow_api.rag_index import (
    delete_paper_chunks,
    fetch_paper_chunks,
    index_paper_full_text,
    paper_index_status,
    project_index_status,
)
from scholarflow_api.rag_retrieval import (
    EmbeddingError,
    embed_project_chunks,
    get_embedding_provider,
    retrieve_project_chunks,
)
from scholarflow_api.repositories.rag_repository import count_project_evaluations
from scholarflow_api.repositories.tool_event_repository import insert_tool_event
from scholarflow_api.schemas import (
    PaperChunk,
    PaperChunkIndexRequest,
    PaperChunkIndexStatus,
    ProjectRagIndexStatus,
    RagAnswerRequest,
    RagAnswerResponse,
    RagEmbeddingRequest,
    RagEmbeddingStatus,
    RagEvaluationListResponse,
    RagEvaluationRecord,
    RagSearchRequest,
    RagSearchResponse,
)


def get_project_rag_index_status(project_id: str) -> ProjectRagIndexStatus:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        status = project_index_status(connection, project_id)
    return ProjectRagIndexStatus.model_validate(status)


def embed_project_rag_index(
    project_id: str,
    payload: RagEmbeddingRequest,
) -> RagEmbeddingStatus:
    ensure_project_exists(project_id)
    try:
        provider = get_embedding_provider()
    except EmbeddingError as error:
        with get_connection() as connection:
            chunk_count = int(project_index_status(connection, project_id)["total_chunks"])
        return RagEmbeddingStatus(
            scope="project",
            project_id=project_id,
            status="failed",
            requested_chunks=chunk_count,
            failed_chunks=chunk_count,
            warnings=[str(error)],
        )
    with get_connection() as connection:
        run = embed_project_chunks(
            connection,
            project_id=project_id,
            force=payload.force,
            provider=provider,
        )
    return RagEmbeddingStatus(
        scope="project",
        project_id=project_id,
        **run.to_dict(),
    )


def search_project_rag(
    project_id: str,
    payload: RagSearchRequest,
) -> RagSearchResponse:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        result = retrieve_project_chunks(
            connection,
            project_id=project_id,
            query=payload.query,
            top_k=payload.top_k,
            paper_ids=payload.paper_ids,
            evidence_levels=payload.evidence_levels,
            sections=payload.sections,
            min_score=payload.min_score,
            max_chunks_per_paper=payload.max_chunks_per_paper,
            refresh_embeddings=payload.refresh_embeddings,
        )
    return RagSearchResponse.model_validate(result)


def create_project_rag_answer(
    project_id: str,
    payload: RagAnswerRequest,
) -> RagAnswerResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, now)
        insert_tool_event(
            connection,
            session_id,
            "rag.retrieve",
            "running",
            f"正在从项目原文索引检索最多 {payload.top_k} 个证据 chunk。",
            now,
        )
        answer = answer_project_rag(
            connection,
            project_id=project_id,
            question=payload.query,
            language=payload.language,
            top_k=payload.top_k,
            paper_ids=payload.paper_ids,
            evidence_levels=payload.evidence_levels,
            sections=payload.sections,
            min_score=payload.min_score,
            max_chunks_per_paper=payload.max_chunks_per_paper,
            refresh_embeddings=payload.refresh_embeddings,
        )
        evaluation = assess_rag_answer(
            answer,
            evaluation_id=new_id("rag_eval"),
            evaluated_at=now,
        )
        answer["quality_assessment"] = evaluation
        artifact_payload = {
            "schema_version": "rag_answer.v3",
            **answer,
        }
        artifact = insert_artifact_row(
            connection=connection,
            project_id=project_id,
            title=f"rag_answer_{paper_slug(payload.query)}.md",
            kind="markdown",
            content_markdown=render_rag_answer_markdown(answer),
            content_json=json.dumps(artifact_payload, ensure_ascii=False, indent=2),
            diff=(
                "+ Retrieved traceable paper chunks\n"
                "+ Recorded claim verification status and method\n"
                "+ Saved citation-grounded RAG answer"
            ),
            now=now,
        )
        answer["artifact"] = artifact
        insert_rag_evaluation(
            connection,
            project_id=project_id,
            answer_artifact_id=str(artifact["id"]),
            answer=answer,
            assessment=evaluation,
            created_at=now,
        )
        insert_tool_event(
            connection,
            session_id,
            "rag.retrieve",
            "done" if answer["citations"] else "partial",
            (
                f"返回 {len(answer['citations'])} 个可追溯引用；"
                f"状态 {answer['status']}。"
            ),
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "rag.answer",
            "done" if answer["claims"] else "partial",
            (
                f"记录 {len(answer['claims'])} 条带结构化验证状态的主张；"
                f"模式 {answer['answer_kind']}。"
            ),
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "rag.evaluate",
            "done",
            (
                "已完成自动证据质量检查；"
                f"状态 {evaluation['quality_status']}，"
                f"分数 {evaluation['score'] if evaluation['score'] is not None else 'not_scored'}。"
            ),
            now,
        )
    return RagAnswerResponse.model_validate(answer)


def get_project_rag_evaluations(
    project_id: str,
    limit: int = 20,
) -> RagEvaluationListResponse:
    ensure_project_exists(project_id)
    safe_limit = max(1, min(100, limit))
    with get_connection() as connection:
        rows = list_rag_evaluations(
            connection,
            project_id=project_id,
            limit=safe_limit,
        )
        total = count_project_evaluations(connection, project_id)
    return RagEvaluationListResponse(
        project_id=project_id,
        total=total,
        evaluations=[
            RagEvaluationRecord.model_validate(item)
            for item in rows
        ],
    )


def get_paper_rag_index_status(project_id: str, paper_id: str) -> PaperChunkIndexStatus:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
        status = paper_index_status(connection, project_id, paper_id)
    return PaperChunkIndexStatus.model_validate(status)
def embed_project_paper_rag_index(
    project_id: str,
    paper_id: str,
    payload: RagEmbeddingRequest,
) -> RagEmbeddingStatus:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
    try:
        provider = get_embedding_provider()
    except EmbeddingError as error:
        with get_connection() as connection:
            chunk_count = int(paper_index_status(connection, project_id, paper_id)["chunk_count"])
        return RagEmbeddingStatus(
            scope="paper",
            project_id=project_id,
            paper_id=paper_id,
            status="failed",
            requested_chunks=chunk_count,
            failed_chunks=chunk_count,
            warnings=[str(error)],
        )
    with get_connection() as connection:
        run = embed_project_chunks(
            connection,
            project_id=project_id,
            paper_id=paper_id,
            force=payload.force,
            provider=provider,
        )
    return RagEmbeddingStatus(
        scope="paper",
        project_id=project_id,
        paper_id=paper_id,
        **run.to_dict(),
    )


def list_project_paper_chunks(project_id: str, paper_id: str) -> list[PaperChunk]:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
        chunks = fetch_paper_chunks(connection, project_id, paper_id)
    return [PaperChunk.model_validate(chunk) for chunk in chunks]


def rebuild_project_paper_rag_index(
    project_id: str,
    paper_id: str,
    payload: PaperChunkIndexRequest,
) -> PaperChunkIndexStatus:
    with get_connection() as connection:
        paper = fetch_paper_dict(connection, project_id, paper_id)
    result = provided_full_text(payload.paper_text) if payload.paper_text else resolve_open_full_text(paper)
    if not result.is_extracted:
        qualification = result.evidence_qualification(
            has_abstract=bool(str(paper.get("abstract") or "").strip()),
        )
        with get_connection() as connection:
            status = paper_index_status(
                connection,
                project_id,
                paper_id,
                message=(
                    f"全文索引未重建：{result.error or qualification.reason} "
                    "已有高等级索引未被删除。"
                ),
            )
        if status["status"] == "not_indexed":
            status["status"] = "failed"
        return PaperChunkIndexStatus.model_validate(status)

    now = utc_now()
    with get_connection() as connection:
        index_paper_full_text(
            connection,
            project_id=project_id,
            paper_id=paper_id,
            text=result.text,
            source_origin=result.source,
            now=now,
            evidence_verified=True,
        )
        status = paper_index_status(
            connection,
            project_id,
            paper_id,
            message="已从真实全文重建可追溯 chunk；embedding 尚未执行。",
        )
    return PaperChunkIndexStatus.model_validate(status)
def delete_project_paper_rag_index(project_id: str, paper_id: str) -> PaperChunkIndexStatus:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
        deleted_count = delete_paper_chunks(connection, project_id, paper_id)
        status = paper_index_status(
            connection,
            project_id,
            paper_id,
            message=f"已清除 {deleted_count} 个本地原文 chunk；论文、Paper Card 与 Memory 保持不变。",
        )
    return PaperChunkIndexStatus.model_validate(status)
