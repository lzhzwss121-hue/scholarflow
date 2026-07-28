from __future__ import annotations

from fastapi import APIRouter, HTTPException

from scholarflow_api.api_helpers import ensure_project_exists
from scholarflow_api.database import get_connection
from scholarflow_api.repositories.artifacts import (
    create_artifact as create_artifact_row,
    get_artifact as get_artifact_row,
    list_artifact_summaries,
)
from scholarflow_api.schemas import (
    Artifact,
    ArtifactCreate,
    ArtifactSummary,
    ArtifactSummaryPage,
)


router = APIRouter(tags=["artifacts"])


@router.get(
    "/projects/{project_id}/artifacts",
    response_model=ArtifactSummaryPage,
    deprecated=True,
)
@router.get(
    "/projects/{project_id}/artifacts/summary",
    response_model=ArtifactSummaryPage,
)
def list_project_artifact_summaries(
    project_id: str,
    limit: int = 50,
    offset: int = 0,
) -> ArtifactSummaryPage:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    ensure_project_exists(project_id)
    with get_connection() as connection:
        items, total = list_artifact_summaries(
            connection,
            project_id,
            limit=limit,
            offset=offset,
        )
    next_offset = offset + len(items) if offset + len(items) < total else None
    return ArtifactSummaryPage(
        items=[ArtifactSummary.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        next_offset=next_offset,
    )


@router.post("/artifacts", response_model=Artifact, status_code=201)
def save_artifact(payload: ArtifactCreate) -> Artifact:
    ensure_project_exists(payload.project_id)
    with get_connection() as connection:
        artifact = create_artifact_row(connection, payload)
    return Artifact.model_validate(artifact)


@router.get("/artifacts/{artifact_id}", response_model=Artifact)
def get_artifact(artifact_id: str) -> Artifact:
    with get_connection() as connection:
        artifact = get_artifact_row(connection, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return Artifact.model_validate(artifact)
