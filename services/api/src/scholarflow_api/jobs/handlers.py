from __future__ import annotations

from typing import Any, Callable

from scholarflow_api.jobs.models import DurableJob


JobHandler = Callable[[DurableJob, Any], dict[str, Any] | None]


def resolve_handler(job_type: str) -> JobHandler:
    handlers: dict[str, JobHandler] = {
        "direction_review": handle_direction_review,
        "agent_run": handle_agent_run,
    }
    try:
        return handlers[job_type]
    except KeyError as error:
        raise ValueError(f"Unsupported durable job type: {job_type}") from error


def handle_direction_review(job: DurableJob, execution: Any) -> dict[str, Any] | None:
    from scholarflow_api.services.direction_review_service import run_direction_review_job

    return run_direction_review_job(job, execution)


def handle_agent_run(job: DurableJob, execution: Any) -> dict[str, Any] | None:
    from scholarflow_api.services.agent_run_service import run_agent_job

    return run_agent_job(job, execution)


def persist_terminal_failure(job: DurableJob, error: object) -> None:
    if job.job_type == "direction_review":
        from scholarflow_api.services.direction_review_service import (
            persist_direction_review_failure,
        )

        persist_direction_review_failure(job.id, job.project_id, error)
        return
    if job.job_type == "agent_run":
        from scholarflow_api.services.agent_run_service import (
            persist_agent_job_failure,
        )

        persist_agent_job_failure(job, error)


def persist_terminal_cancellation(job: DurableJob) -> None:
    if job.job_type == "direction_review":
        from scholarflow_api.services.direction_review_service import (
            persist_direction_review_job_cancellation,
        )

        persist_direction_review_job_cancellation(job)
        return
    if job.job_type == "agent_run":
        from scholarflow_api.services.agent_run_service import (
            persist_agent_job_cancellation,
        )

        persist_agent_job_cancellation(job)
