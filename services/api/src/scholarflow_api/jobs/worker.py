from __future__ import annotations

import argparse
import os
import signal
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from scholarflow_api.database import init_db
from scholarflow_api.jobs.context import job_artifact_scope
from scholarflow_api.jobs.handlers import (
    JobHandler,
    persist_terminal_cancellation,
    persist_terminal_failure,
    resolve_handler,
)
from scholarflow_api.jobs.models import DurableJob, JobCancelled, LeaseLost
from scholarflow_api.jobs.repository import (
    DEFAULT_LEASE_SECONDS,
    cancellation_requested,
    complete_job,
    fail_job,
    lease_next_job,
    mark_job_cancelled,
    record_worker_heartbeat,
    recover_orphaned_runs,
    renew_lease,
    save_checkpoint,
)


@dataclass
class JobExecution:
    job_id: str
    worker_id: str
    lease_seconds: int = DEFAULT_LEASE_SECONDS

    def checkpoint(
        self,
        stage: str,
        progress: int,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        self.raise_if_cancelled()
        save_checkpoint(
            self.job_id,
            self.worker_id,
            stage=stage,
            progress=progress,
            checkpoint=checkpoint,
            lease_seconds=self.lease_seconds,
        )

    def raise_if_cancelled(self) -> None:
        if cancellation_requested(self.job_id, self.worker_id):
            raise JobCancelled(f"Job {self.job_id} was cancelled.")


class DurableWorker:
    def __init__(
        self,
        worker_id: str,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        retry_backoff_seconds: int = 2,
        handler_resolver: Any = resolve_handler,
    ) -> None:
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.retry_backoff_seconds = retry_backoff_seconds
        self.handler_resolver = handler_resolver

    def run_once(self) -> bool:
        record_worker_heartbeat(self.worker_id)
        job = lease_next_job(
            self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if job is None:
            return False
        execution = JobExecution(
            job_id=job.id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        heartbeat = LeaseHeartbeat(
            job.id,
            self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        heartbeat.start()
        try:
            execution.raise_if_cancelled()
            handler: JobHandler = self.handler_resolver(job.job_type)
            with job_artifact_scope(job.id):
                result = handler(job, execution)
            execution.raise_if_cancelled()
            complete_job(job.id, self.worker_id, result or {})
        except JobCancelled:
            cancelled = mark_job_cancelled(job.id, self.worker_id)
            persist_terminal_cancellation(cancelled)
        except LeaseLost:
            # A newer worker owns the fencing lease. The stale worker must not
            # write any terminal state over the current owner.
            pass
        except Exception as error:  # noqa: BLE001 - durable state records handler errors.
            try:
                failed = fail_job(
                    job.id,
                    self.worker_id,
                    error,
                    retry_backoff_seconds=self.retry_backoff_seconds,
                )
                if failed.status == "failed":
                    persist_terminal_failure(failed, error)
            except LeaseLost:
                pass
        finally:
            heartbeat.stop()
            record_worker_heartbeat(self.worker_id)
        return True


class LeaseHeartbeat:
    """Renews ownership only; task execution remains in the worker process."""

    def __init__(self, job_id: str, worker_id: str, *, lease_seconds: int) -> None:
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.interval_seconds = max(0.1, min(5.0, lease_seconds / 3))
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"scholarflow-lease-{job_id}",
            daemon=False,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self.interval_seconds * 2))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                renew_lease(
                    self.job_id,
                    self.worker_id,
                    lease_seconds=self.lease_seconds,
                )
                record_worker_heartbeat(self.worker_id)
            except Exception:
                return


def default_worker_id() -> str:
    configured = os.getenv("SCHOLARFLOW_WORKER_ID")
    if configured:
        return configured
    return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ScholarFlow durable local worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job.")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    recover_orphaned_runs()
    worker_id = default_worker_id()
    worker = DurableWorker(worker_id, lease_seconds=args.lease_seconds)
    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    record_worker_heartbeat(worker_id)
    try:
        if args.once:
            worker.run_once()
            return
        while not stopping:
            processed = worker.run_once()
            if not processed:
                time.sleep(max(0.05, args.poll_interval))
    finally:
        record_worker_heartbeat(worker_id, status="stopped")


if __name__ == "__main__":
    main()
