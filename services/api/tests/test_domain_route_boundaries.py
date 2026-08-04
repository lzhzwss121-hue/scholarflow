from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError


class DomainRouteBoundaryContractTest(unittest.TestCase):
    def test_validation_and_not_found_errors_keep_contracts(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            db_path = Path(tmpdir) / "domain-route-errors.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                from scholarflow_api import main as main_module
                from scholarflow_api.schemas import LiteratureSearchRequest

                init_db()
                with self.assertRaises(HTTPException) as missing:
                    main_module.list_project_papers("missing-project")
                with self.assertRaises(ValidationError) as invalid:
                    LiteratureSearchRequest.model_validate(
                        {"query": "", "max_results": 0, "sources": ["invalid"]}
                    )

        self.assertEqual(missing.exception.status_code, 404)
        self.assertEqual(missing.exception.detail, "Project not found")
        self.assertTrue(invalid.exception.errors())

    def test_paper_and_direction_run_access_are_project_scoped(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            db_path = Path(tmpdir) / "domain-route-isolation.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import get_connection, init_db, utc_now
                from scholarflow_api import main as main_module
                from scholarflow_api.schemas import DirectionReviewRequest, ProjectCreate

                init_db()
                first = main_module.create_project(ProjectCreate(title="First project"))
                second = main_module.create_project(ProjectCreate(title="Second project"))
                now = utc_now()
                with get_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO papers (
                            id, project_id, title, authors, abstract, year, type,
                            venue, source, url, pdf_url, relation, priority, code,
                            relevance_score, relevance_quality, matched_terms_json,
                            review_required, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "paper-first-only",
                            first.id,
                            "Project-scoped paper",
                            "Fixture Author",
                            "Project isolation fixture.",
                            "2025",
                            "paper",
                            "Fixture Venue",
                            "fixture",
                            "",
                            "",
                            "",
                            "High",
                            "",
                            1.0,
                            "strong",
                            "[]",
                            0,
                            now,
                        ),
                    )

                with self.assertRaises(HTTPException) as paper_error:
                    main_module.list_project_paper_chunks(second.id, "paper-first-only")

                request = DirectionReviewRequest(direction="bounded evidence", round=1)
                started = main_module.start_project_direction_review_run(first.id, request)
                reused = main_module.start_project_direction_review_run(first.id, request)
                with self.assertRaises(HTTPException) as run_error:
                    main_module.get_project_direction_review_run(second.id, started.run_id)
                with self.assertRaises(HTTPException) as conflict:
                    main_module.start_project_direction_review_run(
                        first.id,
                        DirectionReviewRequest(direction="different direction", round=2),
                    )

        self.assertEqual(paper_error.exception.status_code, 404)
        self.assertEqual(run_error.exception.status_code, 404)
        self.assertEqual(reused.run_id, started.run_id)
        self.assertEqual(conflict.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
