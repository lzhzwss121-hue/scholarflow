from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_CURRENT_JOB_ID: ContextVar[str | None] = ContextVar(
    "scholarflow_current_job_id",
    default=None,
)


def current_job_id() -> str | None:
    return _CURRENT_JOB_ID.get()


@contextmanager
def job_artifact_scope(job_id: str) -> Iterator[None]:
    token = _CURRENT_JOB_ID.set(job_id)
    try:
        yield
    finally:
        _CURRENT_JOB_ID.reset(token)
