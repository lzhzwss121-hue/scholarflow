from fastapi import APIRouter

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
    RagSearchRequest,
    RagSearchResponse,
)
from scholarflow_api.services import rag_service


router = APIRouter()


@router.get("/projects/{project_id}/rag-index", response_model=ProjectRagIndexStatus)
def get_project_rag_index_status(project_id: str) -> ProjectRagIndexStatus:
    return rag_service.get_project_rag_index_status(project_id)


@router.post(
    "/projects/{project_id}/rag-index/embeddings",
    response_model=RagEmbeddingStatus,
)
def embed_project_rag_index(
    project_id: str,
    payload: RagEmbeddingRequest,
) -> RagEmbeddingStatus:
    return rag_service.embed_project_rag_index(project_id, payload)


@router.post(
    "/projects/{project_id}/rag-search",
    response_model=RagSearchResponse,
)
def search_project_rag(
    project_id: str,
    payload: RagSearchRequest,
) -> RagSearchResponse:
    return rag_service.search_project_rag(project_id, payload)


@router.post(
    "/projects/{project_id}/rag-answer",
    response_model=RagAnswerResponse,
    status_code=201,
)
def create_project_rag_answer(
    project_id: str,
    payload: RagAnswerRequest,
) -> RagAnswerResponse:
    return rag_service.create_project_rag_answer(project_id, payload)


@router.get(
    "/projects/{project_id}/rag-evaluations",
    response_model=RagEvaluationListResponse,
)
def get_project_rag_evaluations(
    project_id: str,
    limit: int = 20,
) -> RagEvaluationListResponse:
    return rag_service.get_project_rag_evaluations(project_id, limit)


@router.get(
    "/projects/{project_id}/papers/{paper_id}/rag-index",
    response_model=PaperChunkIndexStatus,
)
def get_paper_rag_index_status(
    project_id: str,
    paper_id: str,
) -> PaperChunkIndexStatus:
    return rag_service.get_paper_rag_index_status(project_id, paper_id)


@router.post(
    "/projects/{project_id}/papers/{paper_id}/rag-index/embeddings",
    response_model=RagEmbeddingStatus,
)
def embed_project_paper_rag_index(
    project_id: str,
    paper_id: str,
    payload: RagEmbeddingRequest,
) -> RagEmbeddingStatus:
    return rag_service.embed_project_paper_rag_index(project_id, paper_id, payload)


@router.get(
    "/projects/{project_id}/papers/{paper_id}/chunks",
    response_model=list[PaperChunk],
)
def list_project_paper_chunks(project_id: str, paper_id: str) -> list[PaperChunk]:
    return rag_service.list_project_paper_chunks(project_id, paper_id)


@router.post(
    "/projects/{project_id}/papers/{paper_id}/rag-index",
    response_model=PaperChunkIndexStatus,
)
def rebuild_project_paper_rag_index(
    project_id: str,
    paper_id: str,
    payload: PaperChunkIndexRequest,
) -> PaperChunkIndexStatus:
    return rag_service.rebuild_project_paper_rag_index(project_id, paper_id, payload)


@router.delete(
    "/projects/{project_id}/papers/{paper_id}/rag-index",
    response_model=PaperChunkIndexStatus,
)
def delete_project_paper_rag_index(
    project_id: str,
    paper_id: str,
) -> PaperChunkIndexStatus:
    return rag_service.delete_project_paper_rag_index(project_id, paper_id)
