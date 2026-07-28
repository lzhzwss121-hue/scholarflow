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
    from scholarflow_api import main

    return main.run_direction_review_job(job, execution)


def handle_agent_run(job: DurableJob, execution: Any) -> dict[str, Any] | None:
    from scholarflow_api import main

    return main.run_agent_job(job, execution)


def persist_terminal_failure(job: DurableJob, error: object) -> None:
    from scholarflow_api import main

    main.persist_durable_job_failure(job, error)


def persist_terminal_cancellation(job: DurableJob) -> None:
    from scholarflow_api import main

    main.persist_durable_job_cancellation(job)
