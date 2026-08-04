from collections.abc import Callable
from typing import ParamSpec, TypeVar

from fastapi import APIRouter, HTTPException

from scholarflow_api.schemas import (
    DirectionReviewRequest,
    DirectionReviewResponse,
    DirectionReviewRunStatusResponse,
)
from scholarflow_api.services import direction_review_service
from scholarflow_api.services.errors import ServiceError


router = APIRouter()
P = ParamSpec("P")
R = TypeVar("R")


def _call_service(operation: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    try:
        return operation(*args, **kwargs)
    except ServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.post(
    "/projects/{project_id}/direction-reviews",
    response_model=DirectionReviewResponse,
    status_code=201,
)
def create_project_direction_review(
    project_id: str,
    payload: DirectionReviewRequest,
) -> DirectionReviewResponse:
    """Compatibility endpoint for CLI and existing API clients.

    The web product uses the persisted async run endpoints below so it can show
    server-authored progress instead of a timer-based approximation.
    """

    return _call_service(
        direction_review_service.create_project_direction_review,
        project_id,
        payload,
    )


@router.post(
    "/projects/{project_id}/direction-review-runs",
    response_model=DirectionReviewRunStatusResponse,
    status_code=202,
)
def start_project_direction_review_run(
    project_id: str,
    payload: DirectionReviewRequest,
) -> DirectionReviewRunStatusResponse:
    return _call_service(
        direction_review_service.start_project_direction_review_run,
        project_id,
        payload,
    )


@router.get(
    "/projects/{project_id}/direction-review-runs/latest",
    response_model=DirectionReviewRunStatusResponse | None,
)
def get_latest_project_direction_review_run(
    project_id: str,
) -> DirectionReviewRunStatusResponse | None:
    return _call_service(
        direction_review_service.get_latest_project_direction_review_run,
        project_id,
    )


@router.get(
    "/projects/{project_id}/direction-review-runs/{run_id}",
    response_model=DirectionReviewRunStatusResponse,
)
def get_project_direction_review_run(
    project_id: str,
    run_id: str,
) -> DirectionReviewRunStatusResponse:
    return _call_service(
        direction_review_service.get_project_direction_review_run,
        project_id,
        run_id,
    )


@router.post(
    "/projects/{project_id}/direction-review-runs/{run_id}/cancel",
    response_model=DirectionReviewRunStatusResponse,
)
def cancel_project_direction_review_run(
    project_id: str,
    run_id: str,
) -> DirectionReviewRunStatusResponse:
    return _call_service(
        direction_review_service.cancel_project_direction_review_run,
        project_id,
        run_id,
    )
