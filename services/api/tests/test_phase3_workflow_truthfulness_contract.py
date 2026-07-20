from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from scholarflow_api import main as main_module
from scholarflow_api.database import get_connection, init_db
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
    def test_direction_review_run_persists_real_stages_and_structured_notices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Async Direction Review", keyword="evidence faithfulness"),
                )
                with patch.object(main_module.threading, "Thread"):
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

                with patch.object(main_module, "execute_project_direction_review", side_effect=fake_execute):
                    main_module.run_direction_review_background(started.run_id, project.id)

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

    def test_active_direction_review_run_is_reused_instead_of_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Deduplicate Direction Run", keyword="trustworthy VLM"),
                )
                request = DirectionReviewRequest(direction=project.keyword, round=1)
                with patch.object(main_module.threading, "Thread") as thread_class:
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

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(count, 1)
        self.assertEqual(thread_class.call_count, 1)
        self.assertEqual(conflict.exception.status_code, 409)

    def test_background_failure_is_persisted_as_error_not_warning_or_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Failed Direction Run", keyword="causal grounding"),
                )
                with patch.object(main_module.threading, "Thread"):
                    started = main_module.start_project_direction_review_run(
                        project.id,
                        DirectionReviewRequest(direction=project.keyword, round=1),
                    )
                with patch.object(
                    main_module,
                    "execute_project_direction_review",
                    side_effect=RuntimeError("retrieval worker crashed"),
                ):
                    main_module.run_direction_review_background(started.run_id, project.id)
                status = main_module.get_project_direction_review_run(project.id, started.run_id)

        self.assertEqual(status.status, "failed")
        self.assertEqual(status.stage, "failed")
        self.assertEqual(status.progress, 100)
        self.assertIsNone(status.result)
        self.assertTrue(any(notice.severity == "error" for notice in status.notices))
        self.assertIn("retrieval worker crashed", status.message)

    def test_server_restart_marks_process_local_run_failed_instead_of_running_forever(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                init_db()
                project = main_module.create_project(
                    ProjectCreate(title="Interrupted Direction Run", keyword="multimodal reliability"),
                )
                with patch.object(main_module.threading, "Thread"):
                    started = main_module.start_project_direction_review_run(
                        project.id,
                        DirectionReviewRequest(direction=project.keyword, round=1),
                    )
                init_db()
                recovered = main_module.get_project_direction_review_run(project.id, started.run_id)

        self.assertEqual(recovered.status, "failed")
        self.assertEqual(recovered.stage, "failed")
        self.assertTrue(
            any(notice.code == "direction_review_process_interrupted" for notice in recovered.notices),
        )


if __name__ == "__main__":
    unittest.main()
