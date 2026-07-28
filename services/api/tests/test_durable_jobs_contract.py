from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scholarflow_api.api_helpers import insert_artifact_row
from scholarflow_api.database import get_connection, init_db
from scholarflow_api.jobs.models import JobCancelled
from scholarflow_api.jobs.repository import (
    cancel_job,
    enqueue_job,
    get_job,
    lease_next_job,
    mark_job_cancelled,
    recover_orphaned_runs,
    worker_health,
)
from scholarflow_api.jobs.worker import DurableWorker, JobExecution


NOW = "2026-07-28T00:00:00+00:00"


class DurableJobsContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.db_path = Path(self.tmpdir.name) / "jobs.sqlite3"
        self.environment = patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(self.db_path)},
        )
        self.environment.start()
        init_db()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO projects (id, title, created_at, updated_at)
                VALUES ('jobs-project', 'Durable jobs', ?, ?)
                """,
                (NOW, NOW),
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    id, project_id, title, created_at, updated_at
                ) VALUES ('jobs-session', 'jobs-project', 'Jobs', ?, ?)
                """,
                (NOW, NOW),
            )

    def tearDown(self) -> None:
        self.environment.stop()
        self.tmpdir.cleanup()

    def enqueue(
        self,
        suffix: str,
        *,
        job_type: str = "test",
        max_attempts: int = 3,
    ):
        return enqueue_job(
            job_id=f"job-{suffix}",
            project_id="jobs-project",
            session_id="jobs-session",
            job_type=job_type,
            payload={"suffix": suffix},
            dedupe_key=f"{job_type}:{suffix}",
            max_attempts=max_attempts,
        )

    def test_worker_claims_checkpoints_and_completes_job(self) -> None:
        self.enqueue("complete")
        observed = []

        def handler(job, execution):
            observed.append((job.id, job.attempts))
            execution.checkpoint("tool-one", 45, {"tool": "one"})
            return {"answer": "done"}

        worker = DurableWorker(
            "worker-complete",
            handler_resolver=lambda _job_type: handler,
        )
        self.assertTrue(worker.run_once())
        completed = get_job("job-complete")
        health = worker_health(worker_id="worker-complete")

        self.assertEqual(observed, [("job-complete", 1)])
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.progress, 100)
        self.assertEqual(completed.result, {"answer": "done"})
        self.assertTrue(health["workers"][0]["healthy"])

    def test_two_workers_cannot_claim_the_same_job(self) -> None:
        self.enqueue("single-lease")
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    lease_next_job,
                    worker_id,
                    lease_seconds=30,
                    now=now,
                )
                for worker_id in ("worker-a", "worker-b")
            ]
            claimed = [future.result(timeout=5) for future in futures]

        claimed_jobs = [job for job in claimed if job is not None]
        self.assertEqual(len(claimed_jobs), 1)
        self.assertEqual(claimed_jobs[0].id, "job-single-lease")
        self.assertIn(claimed_jobs[0].lease_owner, {"worker-a", "worker-b"})

    def test_live_worker_renews_lease_during_long_handler(self) -> None:
        self.enqueue("heartbeat-lease")
        handler_started = threading.Event()
        release_handler = threading.Event()

        def long_handler(_job, _execution):
            handler_started.set()
            if not release_handler.wait(timeout=3):
                raise TimeoutError("test did not release handler")
            return {"done": True}

        worker = DurableWorker(
            "worker-heartbeat",
            lease_seconds=1,
            handler_resolver=lambda _job_type: long_handler,
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            running = executor.submit(worker.run_once)
            self.assertTrue(handler_started.wait(timeout=2))
            time.sleep(1.2)
            duplicate = lease_next_job(
                "worker-duplicate",
                lease_seconds=1,
            )
            release_handler.set()
            self.assertTrue(running.result(timeout=3))

        self.assertIsNone(duplicate)
        self.assertEqual(get_job("job-heartbeat-lease").status, "completed")

    def test_expired_lease_is_recovered_by_another_worker(self) -> None:
        self.enqueue("recover")
        first_time = datetime(2026, 7, 28, tzinfo=timezone.utc)
        first = lease_next_job(
            "worker-crashed",
            lease_seconds=1,
            now=first_time,
        )
        recovered = lease_next_job(
            "worker-recovery",
            lease_seconds=30,
            now=first_time + timedelta(seconds=2),
        )

        self.assertEqual(first.id, recovered.id)
        self.assertEqual(recovered.lease_owner, "worker-recovery")
        self.assertEqual(recovered.attempts, 2)

    def test_running_job_cancellation_is_honored_at_boundary(self) -> None:
        self.enqueue("cancel")
        leased = lease_next_job("worker-cancel")
        requested = cancel_job(leased.id)
        execution = JobExecution(leased.id, "worker-cancel")

        self.assertTrue(requested.cancellation_requested)
        self.assertEqual(requested.status, "running")
        with self.assertRaises(JobCancelled):
            execution.raise_if_cancelled()
        cancelled = mark_job_cancelled(leased.id, "worker-cancel")
        self.assertEqual(cancelled.status, "cancelled")

    def test_max_attempts_stops_retrying(self) -> None:
        self.enqueue("retry-limit", max_attempts=2)

        def failing_handler(_job, _execution):
            raise RuntimeError("repeatable failure")

        worker = DurableWorker(
            "worker-retry",
            retry_backoff_seconds=0,
            handler_resolver=lambda _job_type: failing_handler,
        )
        self.assertTrue(worker.run_once())
        first_failure = get_job("job-retry-limit")
        self.assertEqual(first_failure.status, "retry_wait")
        self.assertTrue(worker.run_once())
        exhausted = get_job("job-retry-limit")

        self.assertEqual(exhausted.status, "failed")
        self.assertEqual(exhausted.attempts, 2)
        self.assertIn("repeatable failure", exhausted.error)
        self.assertFalse(worker.run_once())

    def test_artifact_write_is_idempotent_across_retry(self) -> None:
        self.enqueue("artifact", max_attempts=2)
        artifact_ids = []
        calls = 0

        def artifact_handler(_job, _execution):
            nonlocal calls
            calls += 1
            with get_connection() as connection:
                artifact = insert_artifact_row(
                    connection=connection,
                    project_id="jobs-project",
                    title="durable-result.md",
                    kind="markdown",
                    content_markdown=f"attempt {calls}",
                    content_json="{}",
                    diff="+ durable result",
                    now=NOW,
                )
                artifact_ids.append(artifact["id"])
            if calls == 1:
                raise RuntimeError("crash after artifact commit")
            return {"artifact_id": artifact_ids[-1]}

        worker = DurableWorker(
            "worker-artifact",
            retry_backoff_seconds=0,
            handler_resolver=lambda _job_type: artifact_handler,
        )
        self.assertTrue(worker.run_once())
        self.assertTrue(worker.run_once())
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, content_markdown FROM artifacts
                WHERE title = 'durable-result.md'
                """
            ).fetchall()

        self.assertEqual(len(rows), 1)
        self.assertEqual(artifact_ids[0], artifact_ids[1])
        self.assertEqual(rows[0]["content_markdown"], "attempt 2")

    def test_api_restart_recovers_legacy_running_run_into_queue(self) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    id, project_id, session_id, task, status,
                    plan_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'running', '{}', ?, ?)
                """,
                (
                    "legacy-running-agent",
                    "jobs-project",
                    "jobs-session",
                    "resume me",
                    NOW,
                    NOW,
                ),
            )

        recovered = recover_orphaned_runs()
        job = get_job("legacy-running-agent")

        self.assertEqual(recovered["agent_run"], 1)
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.job_type, "agent_run")
        self.assertEqual(recover_orphaned_runs()["agent_run"], 0)


if __name__ == "__main__":
    unittest.main()
