from __future__ import annotations

from scholarflow_api.api_helpers import artifact_ref
from scholarflow_api.schemas import ArtifactRef, WorkflowStepState


def make_artifact_refs(artifacts: list[dict]) -> list[ArtifactRef]:
    return [ArtifactRef.model_validate(artifact_ref(artifact)) for artifact in artifacts]


def workflow_step_state(
    step_id: str,
    status: str,
    label: str,
    summary: str,
    updated_at: str,
    *,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    artifacts: list[dict] | None = None,
) -> WorkflowStepState:
    return WorkflowStepState(
        step_id=step_id,
        status=status,  # type: ignore[arg-type]
        label=label,
        summary=summary,
        warnings=warnings or [],
        errors=errors or [],
        artifact_refs=make_artifact_refs(artifacts or []),
        updated_at=updated_at,
    )


def direction_step_status(review_status: str, round_read_count: int) -> str:
    if review_status == "blocked":
        return "blocked"
    if review_status == "partial" or round_read_count < 5:
        return "partial"
    return "complete"


def memory_step_status(hit_count: int, warnings: list[str]) -> str:
    if hit_count <= 0:
        return "partial" if warnings else "blocked"
    return "partial" if warnings else "complete"


def experiment_step_status(status: str) -> str:
    if status == "blocked":
        return "blocked"
    if status == "partial":
        return "partial"
    return "complete"


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
