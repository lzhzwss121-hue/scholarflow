from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}
ACTIVE_JOB_STATUSES = {"queued", "retry_wait", "running"}


class LeaseLost(RuntimeError):
    """Raised when a worker no longer owns the job it is updating."""


class JobCancelled(RuntimeError):
    """Raised at a durable tool boundary after cancellation was requested."""


@dataclass(frozen=True)
class DurableJob:
    id: str
    project_id: str
    session_id: str | None
    job_type: str
    payload: dict[str, Any]
    status: str
    stage: str
    progress: int
    attempts: int
    max_attempts: int
    lease_owner: str | None
    lease_until: str | None
    heartbeat_at: str | None
    cancellation_requested: bool
    checkpoint: dict[str, Any]
    result: dict[str, Any] | None
    error: str
    next_attempt_at: str | None
    dedupe_key: str
    created_at: str
    updated_at: str
    completed_at: str | None

    @classmethod
    def from_row(cls, row: Any) -> "DurableJob":
        data = dict(row)
        return cls(
            id=str(data["id"]),
            project_id=str(data["project_id"]),
            session_id=str(data["session_id"]) if data.get("session_id") else None,
            job_type=str(data["job_type"]),
            payload=parse_json_object(data.get("payload_json")),
            status=str(data["status"]),
            stage=str(data["stage"]),
            progress=int(data.get("progress") or 0),
            attempts=int(data.get("attempts") or 0),
            max_attempts=int(data.get("max_attempts") or 0),
            lease_owner=str(data["lease_owner"]) if data.get("lease_owner") else None,
            lease_until=str(data["lease_until"]) if data.get("lease_until") else None,
            heartbeat_at=str(data["heartbeat_at"]) if data.get("heartbeat_at") else None,
            cancellation_requested=bool(data.get("cancellation_requested")),
            checkpoint=parse_json_object(data.get("checkpoint_json")),
            result=(
                parse_json_object(data.get("result_json"))
                if str(data.get("result_json") or "").strip()
                else None
            ),
            error=str(data.get("error") or ""),
            next_attempt_at=(
                str(data["next_attempt_at"]) if data.get("next_attempt_at") else None
            ),
            dedupe_key=str(data["dedupe_key"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            completed_at=(
                str(data["completed_at"]) if data.get("completed_at") else None
            ),
        )


def parse_json_object(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
