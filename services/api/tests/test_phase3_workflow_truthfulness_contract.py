from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from scholarflow_api import main as main_module
from scholarflow_api.api_helpers import build_warning_summary_metrics
from scholarflow_api.database import get_connection, init_db
from scholarflow_api.jobs.repository import get_job, recover_orphaned_runs
from scholarflow_api.jobs.worker import DurableWorker
from scholarflow_api.schemas import DirectionReviewRequest, DirectionReviewResponse, ProjectCreate


def partial_review(direction: str) -> DirectionReviewResponse:
    return DirectionReviewResponse(
        direction=direction,
        round=1,
        review_status="partial",
        target_paper_count=10,
        round_read_count=2,
        relevant_read_count=2,
        low_relevance_count=4,
        off_topic_count=3,
        relevance_coverage={
            "candidate_count": 9,
            "strong_match_count": 1,
            "medium_match_count": 1,
            "weak_match_count": 4,
            "off_topic_count": 3,
        },
        total_read_count=2,
        recommended_paper_ids=[],
        direction_summary="当前只有两篇强/中相关证据，不能视为完整方向综述。",
        artifact_refs=[],
        errors=["openalex: degraded status=503"],
        workflow_steps=[],
    )


class Phase3WorkflowTruthfulnessContractTest(unittest.TestCase):
    def test_existing_direction_run_table_is_migrated_with_started_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE direction_review_runs (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        round_index INTEGER NOT NULL DEFAULT 1,
                        status TEXT NOT NULL DEFAULT 'queued',
                        stage TEXT NOT NULL DEFAULT 'queued',
                        progress INTEGER NOT NULL DEFAULT 0,
                        message TEXT NOT NULL DEFAULT '',
                        notices_json TEXT NOT NULL DEFAULT '[]',
                        result_json TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        completed_at TEXT
                    )
                    """,
                )
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                with get_connection() as connection:
                    columns = {
                        row["name"]
                        for row in connection.execute(
                            "PRAGMA table_info(direction_review_runs)",
                        ).fetchall()
                    }

        self.assertIn("started_at", columns)

    def test_warning_metrics_keep_raw_unique_and_grouped_counts_separate(self) -> None:
        metrics = build_warning_summary_metrics(
            [
                "openalex: degraded status=503",
                "openalex: degraded status=503",
                "PDF full text unavailable",
            ],
        )

        self.assertEqual(metrics["warning_count_raw"], 3)
        self.assertEqual(metrics["warning_count_unique"], 2)
        self.assertEqual(metrics["warning_count"], 2)
        groups = {group["code"]: group for group in metrics["warning_groups"]}
        self.assertEqual(groups["http_503"]["count"], 2)
        self.assertEqual(groups["pdf_unavailable"]["count"], 1)

    def test_direction_review_run_persists_real_stages_and_structured_notices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Async Direction Review", keyword="evidence faithfulness"),
                )
                started = main_module.start_project_direction_review_run(
                    project.id,
                    DirectionReviewRequest(direction=project.keyword, round=1),
                )

                observed: list[tuple[str, int, str]] = []

                def fake_execute(project_id, payload, progress_callback):
                    self.assertEqual(project_id, project.id)
                    self.assertEqual(payload.direction, project.keyword)
                    for stage, progress, message in [
                        ("retrieving", 20, "retrieving candidates"),
                        ("reading", 45, "reading selected papers"),
                        ("curating", 68, "curating evidence"),
                        ("persisting", 96, "persisting artifacts"),
                    ]:
                        progress_callback(stage, progress, message)
                        snapshot = main_module.get_project_direction_review_run(project.id, started.run_id)
                        observed.append((snapshot.stage, snapshot.progress, snapshot.message))
                    return partial_review(payload.direction)

                with patch("scholarflow_api.services.workflow_runtime.execute_project_direction_review", side_effect=fake_execute):
                    DurableWorker("direction-test-worker").run_once()

                status = main_module.get_project_direction_review_run(project.id, started.run_id)
                latest = main_module.get_latest_project_direction_review_run(project.id)

        self.assertEqual(started.status, "queued")
        self.assertEqual(
            observed,
            [
                ("retrieving", 20, "retrieving candidates"),
                ("reading", 45, "reading selected papers"),
                ("curating", 68, "curating evidence"),
                ("persisting", 96, "persisting artifacts"),
            ],
        )
        self.assertEqual(status.status, "partial")
        self.assertEqual(status.stage, "completed")
        self.assertEqual(status.progress, 100)
        self.assertIsNotNone(status.result)
        self.assertEqual(status.result.review_status, "partial")
        self.assertEqual(latest.run_id, started.run_id)
        self.assertTrue(any(notice.severity == "info" for notice in status.notices))
        self.assertTrue(any(notice.code == "direction_review_partial" for notice in status.notices))
        self.assertTrue(any(notice.severity == "warning" for notice in status.notices))
        self.assertEqual(started.queued_at, started.created_at)
        self.assertEqual(started.started_at, "")
        self.assertEqual(started.current_tool, "")
        self.assertTrue(status.started_at)
        self.assertTrue(status.completed_at)
        self.assertEqual(status.current_tool, "")
        self.assertEqual(status.last_heartbeat, status.updated_at)

    def test_active_direction_review_run_is_reused_instead_of_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Deduplicate Direction Run", keyword="trustworthy VLM"),
                )
                request = DirectionReviewRequest(direction=project.keyword, round=1)
                first = main_module.start_project_direction_review_run(project.id, request)
                second = main_module.start_project_direction_review_run(project.id, request)
                with self.assertRaises(HTTPException) as conflict:
                    main_module.start_project_direction_review_run(
                        project.id,
                        DirectionReviewRequest(direction="different direction", round=2),
                    )
                with get_connection() as connection:
                    count = connection.execute(
                        "SELECT COUNT(*) AS count FROM direction_review_runs WHERE project_id = ?",
                        (project.id,),
                    ).fetchone()["count"]
                    job_count = connection.execute(
                        "SELECT COUNT(*) AS count FROM jobs WHERE project_id = ?",
                        (project.id,),
                    ).fetchone()["count"]

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(count, 1)
        self.assertEqual(job_count, 1)
        self.assertEqual(conflict.exception.status_code, 409)

    def test_background_failure_is_persisted_as_error_not_warning_or_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Failed Direction Run", keyword="causal grounding"),
                )
                started = main_module.start_project_direction_review_run(
                    project.id,
                    DirectionReviewRequest(direction=project.keyword, round=1),
                )
                with patch(
                    "scholarflow_api.services.workflow_runtime.execute_project_direction_review",
                    side_effect=RuntimeError("retrieval worker crashed"),
                ):
                    worker = DurableWorker(
                        "direction-failure-worker",
                        retry_backoff_seconds=0,
                    )
                    for _ in range(3):
                        worker.run_once()
                status = main_module.get_project_direction_review_run(project.id, started.run_id)

        self.assertEqual(status.status, "failed")
        self.assertEqual(status.stage, "failed")
        self.assertEqual(status.progress, 100)
        self.assertIsNone(status.result)
        self.assertTrue(any(notice.severity == "error" for notice in status.notices))
        self.assertIn("retrieval worker crashed", status.message)

    def test_queued_direction_review_can_be_cancelled_durably(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                project = main_module.create_project(
                    ProjectCreate(
                        title="Cancelled Direction Run",
                        keyword="durable cancellation",
                    ),
                )
                started = main_module.start_project_direction_review_run(
                    project.id,
                    DirectionReviewRequest(direction=project.keyword, round=1),
                )
                cancelled = main_module.cancel_project_direction_review_run(
                    project.id,
                    started.run_id,
                )
                job = get_job(started.run_id)

        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(cancelled.stage, "cancelled")
        self.assertEqual(job.status, "cancelled")

    def test_server_restart_keeps_durable_run_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Interrupted Direction Run", keyword="multimodal reliability"),
                )
                started = main_module.start_project_direction_review_run(
                    project.id,
                    DirectionReviewRequest(direction=project.keyword, round=1),
                )
                init_db()
                recovered_counts = recover_orphaned_runs()
                recovered = main_module.get_project_direction_review_run(project.id, started.run_id)
                job = get_job(started.run_id)

        self.assertEqual(recovered.status, "queued")
        self.assertEqual(recovered.stage, "queued")
        self.assertEqual(job.status, "queued")
        self.assertEqual(recovered_counts["direction_review"], 0)


if __name__ == "__main__":
    unittest.main()
