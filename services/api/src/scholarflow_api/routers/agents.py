from fastapi import APIRouter

from scholarflow_api.schemas import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentPlanRequest,
    AgentPlanResponse,
    AgentRunStatusResponse,
)
from scholarflow_api.services.agent_plan_service import (
    create_agent_plan as create_agent_plan_service,
)
from scholarflow_api.services.agent_run_service import (
    cancel_agent_run as cancel_agent_run_service,
    execute_agent_run as execute_agent_run_service,
    get_agent_run_status as get_agent_run_status_service,
)


router = APIRouter()


@router.post("/agent/plan", response_model=AgentPlanResponse, status_code=201)
def create_agent_plan(payload: AgentPlanRequest) -> AgentPlanResponse:
    return create_agent_plan_service(payload)


@router.get("/agent/runs/{run_id}", response_model=AgentRunStatusResponse)
def get_agent_run_status(run_id: str) -> AgentRunStatusResponse:
    return get_agent_run_status_service(run_id)


@router.post(
    "/agent/runs/{run_id}/cancel",
    response_model=AgentRunStatusResponse,
)
def cancel_agent_run(run_id: str) -> AgentRunStatusResponse:
    return cancel_agent_run_service(run_id)


@router.post(
    "/agent/runs/{run_id}/execute",
    response_model=AgentExecuteResponse,
)
def execute_agent_run(
    run_id: str,
    payload: AgentExecuteRequest,
) -> AgentExecuteResponse:
    return execute_agent_run_service(run_id, payload)
