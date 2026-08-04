from fastapi import APIRouter

from scholarflow_api.schemas import (
    ResearchDecisionRequest,
    ResearchDecisionResponse,
    ResearchMemoryQueryRequest,
    ResearchMemoryQueryResponse,
)
from scholarflow_api.services import research_decision_service


router = APIRouter()


@router.post(
    "/projects/{project_id}/research-decisions",
    response_model=ResearchDecisionResponse,
    status_code=201,
)
def create_project_research_decisions(
    project_id: str,
    payload: ResearchDecisionRequest,
) -> ResearchDecisionResponse:
    return research_decision_service.create_project_research_decisions(project_id, payload)


@router.post(
    "/projects/{project_id}/research-memory/query",
    response_model=ResearchMemoryQueryResponse,
    status_code=201,
)
def query_project_research_memory(
    project_id: str,
    payload: ResearchMemoryQueryRequest,
) -> ResearchMemoryQueryResponse:
    return research_decision_service.query_project_research_memory(project_id, payload)
