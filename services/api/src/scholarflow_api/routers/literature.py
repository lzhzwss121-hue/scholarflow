from fastapi import APIRouter

from scholarflow_api.schemas import LiteratureSearchRequest, LiteratureSearchResponse, Paper
from scholarflow_api.services import literature_service


router = APIRouter()


@router.get("/projects/{project_id}/papers", response_model=list[Paper])
def list_project_papers(project_id: str) -> list[Paper]:
    return literature_service.list_project_papers(project_id)


@router.post(
    "/projects/{project_id}/literature/search",
    response_model=LiteratureSearchResponse,
)
def search_project_literature(
    project_id: str,
    payload: LiteratureSearchRequest,
) -> LiteratureSearchResponse:
    return literature_service.search_project_literature(project_id, payload)
