from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from scholarflow_api.database import get_connection, new_id, utc_now
from scholarflow_api.jobs.models import DurableJob, LeaseLost


DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_LEASE_SECONDS = 120
DEFAULT_RETRY_BACKOFF_SECONDS = 2
WORKER_HEARTBEAT_STALE_SECONDS = 15


def enqueue_job(
    *,
    project_id: str,
    session_id: str | None,
    job_type: str,
    payload: dict[str, Any],
    dedupe_key: str,
    job_id: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    connection: Any | None = None,
) -> DurableJob:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if connection is None:
        with get_connection() as owned_connection:
            return enqueue_job(
                project_id=project_id,
                session_id=session_id,
                job_type=job_type,
                payload=payload,
                dedupe_key=dedupe_key,
                job_id=job_id,
                max_attempts=max_attempts,
                connection=owned_connection,
            )

    existing = connection.execute(
        "SELECT * FROM jobs WHERE dedupe_key = ?",
        (dedupe_key,),
    ).fetchone()
    if existing is not None:
        return DurableJob.from_row(existing)

    now = utc_now()
    resolved_job_id = job_id or new_id("job")
    connection.execute(
        """
        INSERT INTO jobs (
            id, project_id, session_id, job_type, payload_json, status, stage,
            progress, attempts, max_attempts, cancellation_requested,
            checkpoint_json, result_json, error, dedupe_key, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'queued', 'queued', 0, 0, ?, 0, '{}', '', '', ?, ?, ?)
        """,
        (
            resolved_job_id,
            project_id,
            session_id,
            job_type,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            max_attempts,
            dedupe_key,
            now,
            now,
        ),
    )
    row = connection.execute(
        "SELECT * FROM jobs WHERE id = ?",
        (resolved_job_id,),
    ).fetchone()
    return DurableJob.from_row(row)


def get_job(job_id: str) -> DurableJob | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    return DurableJob.from_row(row) if row is not None else None


def lease_next_job(
    worker_id: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> DurableJob | None:
    claimed_at = normalized_datetime(now)
    claimed_at_text = claimed_at.isoformat()
    lease_until = (claimed_at + timedelta(seconds=lease_seconds)).isoformat()
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE jobs
            SET status = 'cancelled', stage = 'cancelled', completed_at = ?,
                updated_at = ?, lease_owner = NULL, lease_until = NULL
            WHERE cancellation_requested = 1
              AND status IN ('queued', 'retry_wait')
            """,
            (claimed_at_text, claimed_at_text),
        )
        connection.execute(
            """
            UPDATE jobs
            SET status = 'failed', stage = 'failed',
                error = CASE
                    WHEN error = '' THEN 'Lease expired after maximum attempts.'
                    ELSE error
                END,
                completed_at = ?, updated_at = ?, lease_owner = NULL, lease_until = NULL
            WHERE status = 'running'
              AND lease_until IS NOT NULL AND lease_until <= ?
              AND attempts >= max_attempts
            """,
            (claimed_at_text, claimed_at_text, claimed_at_text),
        )
        candidate = connection.execute(
            """
            SELECT * FROM jobs
            WHERE cancellation_requested = 0
              AND attempts < max_attempts
              AND (
                    status = 'queued'
                    OR (
                        status = 'retry_wait'
                        AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                    )
                    OR (
                        status = 'running'
                        AND lease_until IS NOT NULL
                        AND lease_until <= ?
                    )
              )
            ORDER BY
                CASE WHEN status = 'running' THEN 0 ELSE 1 END,
                created_at ASC
            LIMIT 1
            """,
            (claimed_at_text, claimed_at_text),
        ).fetchone()
        if candidate is None:
            return None
        job_id = str(candidate["id"])
        connection.execute(
            """
            UPDATE jobs
            SET status = 'running',
                stage = CASE WHEN stage IN ('queued', 'retry_wait') THEN 'starting' ELSE stage END,
                attempts = attempts + 1,
                lease_owner = ?,
                lease_until = ?,
                heartbeat_at = ?,
                error = '',
                next_attempt_at = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                worker_id,
                lease_until,
                claimed_at_text,
                claimed_at_text,
                job_id,
            ),
        )
        claimed = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    return DurableJob.from_row(claimed)


def save_checkpoint(
    job_id: str,
    worker_id: str,
    *,
    stage: str,
    progress: int,
    checkpoint: dict[str, Any] | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> DurableJob:
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET stage = ?, progress = ?, checkpoint_json = ?,
                heartbeat_at = ?, lease_until = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            """,
            (
                stage,
                max(0, min(100, int(progress))),
                json.dumps(checkpoint or {}, ensure_ascii=False, sort_keys=True),
                now_text,
                lease_until,
                now_text,
                job_id,
                worker_id,
            ),
        )
        if cursor.rowcount != 1:
            raise LeaseLost(f"Worker {worker_id} no longer owns job {job_id}.")
        row = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    return DurableJob.from_row(row)


def renew_lease(
    job_id: str,
    worker_id: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> None:
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET heartbeat_at = ?, lease_until = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            """,
            (now_text, lease_until, now_text, job_id, worker_id),
        )
        if cursor.rowcount != 1:
            raise LeaseLost(f"Worker {worker_id} no longer owns job {job_id}.")


def cancellation_requested(job_id: str, worker_id: str | None = None) -> bool:
    with get_connection() as connection:
        if worker_id is None:
            row = connection.execute(
                "SELECT cancellation_requested FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT cancellation_requested FROM jobs
                WHERE id = ? AND status = 'running' AND lease_owner = ?
                """,
                (job_id, worker_id),
            ).fetchone()
            if row is None:
                raise LeaseLost(f"Worker {worker_id} no longer owns job {job_id}.")
    return bool(row and int(row["cancellation_requested"] or 0))


def cancel_job(job_id: str) -> DurableJob | None:
    now = utc_now()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        if str(row["status"]) in {"completed", "failed", "cancelled"}:
            return DurableJob.from_row(row)
        connection.execute(
            """
            UPDATE jobs
            SET cancellation_requested = 1,
                status = CASE
                    WHEN status IN ('queued', 'retry_wait') THEN 'cancelled'
                    ELSE status
                END,
                stage = CASE
                    WHEN status IN ('queued', 'retry_wait') THEN 'cancelled'
                    ELSE stage
                END,
                completed_at = CASE
                    WHEN status IN ('queued', 'retry_wait') THEN ?
                    ELSE completed_at
                END,
                updated_at = ?
            WHERE id = ?
            """,
            (now, now, job_id),
        )
        updated = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    return DurableJob.from_row(updated)


def complete_job(
    job_id: str,
    worker_id: str,
    result: dict[str, Any] | None = None,
) -> DurableJob:
    now = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status = 'completed', stage = 'completed', progress = 100,
                result_json = ?, error = '', completed_at = ?, updated_at = ?,
                heartbeat_at = ?, lease_owner = NULL, lease_until = NULL
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            """,
            (
                json.dumps(result or {}, ensure_ascii=False, sort_keys=True),
                now,
                now,
                now,
                job_id,
                worker_id,
            ),
        )
        if cursor.rowcount != 1:
            raise LeaseLost(f"Worker {worker_id} no longer owns job {job_id}.")
        row = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    return DurableJob.from_row(row)


def mark_job_cancelled(job_id: str, worker_id: str) -> DurableJob:
    now = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status = 'cancelled', stage = 'cancelled',
                cancellation_requested = 1, completed_at = ?, updated_at = ?,
                heartbeat_at = ?, lease_owner = NULL, lease_until = NULL
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            """,
            (now, now, now, job_id, worker_id),
        )
        if cursor.rowcount != 1:
            raise LeaseLost(f"Worker {worker_id} no longer owns job {job_id}.")
        row = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    return DurableJob.from_row(row)


def fail_job(
    job_id: str,
    worker_id: str,
    error: object,
    *,
    retry_backoff_seconds: int = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> DurableJob:
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT attempts, max_attempts FROM jobs
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            """,
            (job_id, worker_id),
        ).fetchone()
        if row is None:
            raise LeaseLost(f"Worker {worker_id} no longer owns job {job_id}.")
        exhausted = int(row["attempts"]) >= int(row["max_attempts"])
        next_attempt_at = (
            None
            if exhausted
            else (
                now
                + timedelta(
                    seconds=retry_backoff_seconds
                    * max(1, 2 ** (int(row["attempts"]) - 1))
                )
            ).isoformat()
        )
        connection.execute(
            """
            UPDATE jobs
            SET status = ?, stage = ?, error = ?, next_attempt_at = ?,
                completed_at = ?, updated_at = ?, heartbeat_at = ?,
                lease_owner = NULL, lease_until = NULL
            WHERE id = ?
            """,
            (
                "failed" if exhausted else "retry_wait",
                "failed" if exhausted else "retry_wait",
                str(error)[:2000],
                next_attempt_at,
                now_text if exhausted else None,
                now_text,
                now_text,
                job_id,
            ),
        )
        updated = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    return DurableJob.from_row(updated)


def record_worker_heartbeat(
    worker_id: str,
    *,
    status: str = "running",
    pid: int | None = None,
) -> None:
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO worker_heartbeats (
                worker_id, pid, status, started_at, heartbeat_at, stopped_at
            )
            VALUES (?, ?, ?, ?, ?, NULL)
            ON CONFLICT(worker_id) DO UPDATE SET
                pid = excluded.pid,
                status = excluded.status,
                heartbeat_at = excluded.heartbeat_at,
                stopped_at = CASE
                    WHEN excluded.status = 'stopped' THEN excluded.heartbeat_at
                    ELSE NULL
                END
            """,
            (worker_id, pid or os.getpid(), status, now, now),
        )


def worker_health(
    *,
    worker_id: str | None = None,
    stale_seconds: int = WORKER_HEARTBEAT_STALE_SECONDS,
) -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)).isoformat()
    with get_connection() as connection:
        if worker_id:
            rows = connection.execute(
                """
                SELECT * FROM worker_heartbeats
                WHERE worker_id = ? ORDER BY heartbeat_at DESC
                """,
                (worker_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM worker_heartbeats ORDER BY heartbeat_at DESC"
            ).fetchall()
        queued = connection.execute(
            """
            SELECT COUNT(*) FROM jobs
            WHERE status IN ('queued', 'retry_wait', 'running')
            """
        ).fetchone()[0]
    workers = [
        {
            **dict(row),
            "healthy": (
                str(row["status"]) == "running"
                and str(row["heartbeat_at"]) >= cutoff
            ),
        }
        for row in rows
    ]
    return {
        "status": "ok" if any(worker["healthy"] for worker in workers) else "degraded",
        "workers": workers,
        "active_jobs": int(queued),
        "stale_after_seconds": stale_seconds,
    }


def recover_orphaned_runs() -> dict[str, int]:
    recovered = {"direction_review": 0, "agent_run": 0}
    with get_connection() as connection:
        direction_rows = connection.execute(
            """
            SELECT * FROM direction_review_runs
            WHERE status IN ('queued', 'running')
              AND NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.id = direction_review_runs.id)
            """
        ).fetchall()
        for row in direction_rows:
            enqueue_job(
                job_id=str(row["id"]),
                project_id=str(row["project_id"]),
                session_id=str(row["session_id"]),
                job_type="direction_review",
                payload={
                    "run_id": str(row["id"]),
                    "project_id": str(row["project_id"]),
                    "direction": str(row["direction"]),
                    "round": int(row["round_index"]),
                },
                dedupe_key=f"direction_review:{row['id']}",
                connection=connection,
            )
            connection.execute(
                """
                UPDATE direction_review_runs
                SET status = 'queued', stage = 'queued',
                    message = '任务已在 API 重启后恢复到耐久队列。', updated_at = ?
                WHERE id = ?
                """,
                (utc_now(), row["id"]),
            )
            recovered["direction_review"] += 1

        agent_rows = connection.execute(
            """
            SELECT * FROM agent_runs
            WHERE status = 'running'
              AND NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.id = agent_runs.id)
            """
        ).fetchall()
        for row in agent_rows:
            enqueue_job(
                job_id=str(row["id"]),
                project_id=str(row["project_id"]),
                session_id=str(row["session_id"]),
                job_type="agent_run",
                payload={"run_id": str(row["id"])},
                dedupe_key=f"agent_run:{row['id']}",
                connection=connection,
            )
            recovered["agent_run"] += 1
    return recovered


def normalized_datetime(value: datetime | None) -> datetime:
    resolved = value or datetime.now(timezone.utc)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc)
