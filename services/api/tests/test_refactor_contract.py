from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


EXPECTED_ROUTE_METHODS = {
    "/agent/plan": ["POST"],
    "/agent/runs/{run_id}": ["GET"],
    "/agent/runs/{run_id}/cancel": ["POST"],
    "/agent/runs/{run_id}/execute": ["POST"],
    "/artifacts": ["POST"],
    "/artifacts/{artifact_id}": ["GET"],
    "/health": ["GET"],
    "/health/jobs": ["GET"],
    "/projects": ["GET", "POST"],
    "/projects/{project_id}": ["GET"],
    "/projects/{project_id}/artifacts": ["GET"],
    "/projects/{project_id}/artifacts/summary": ["GET"],
    "/projects/{project_id}/direction-review-runs": ["POST"],
    "/projects/{project_id}/direction-review-runs/latest": ["GET"],
    "/projects/{project_id}/direction-review-runs/{run_id}": ["GET"],
    "/projects/{project_id}/direction-review-runs/{run_id}/cancel": ["POST"],
    "/projects/{project_id}/direction-reviews": ["POST"],
    "/projects/{project_id}/literature/search": ["POST"],
    "/projects/{project_id}/paper-cards": ["GET", "POST"],
    "/projects/{project_id}/papers": ["GET"],
    "/projects/{project_id}/papers/{paper_id}/chunks": ["GET"],
    "/projects/{project_id}/papers/{paper_id}/full-text": ["POST"],
    "/projects/{project_id}/papers/{paper_id}/rag-index": ["DELETE", "GET", "POST"],
    "/projects/{project_id}/papers/{paper_id}/rag-index/embeddings": ["POST"],
    "/projects/{project_id}/rag-answer": ["POST"],
    "/projects/{project_id}/rag-evaluations": ["GET"],
    "/projects/{project_id}/rag-index": ["GET"],
    "/projects/{project_id}/rag-index/embeddings": ["POST"],
    "/projects/{project_id}/rag-search": ["POST"],
    "/projects/{project_id}/research-decisions": ["POST"],
    "/projects/{project_id}/research-memory/query": ["POST"],
    "/projects/{project_id}/sessions": ["GET"],
    "/projects/{project_id}/timeline": ["GET"],
    "/sessions/{session_id}/timeline": ["GET"],
}


class RefactorContractTest(unittest.TestCase):
    def test_openapi_route_snapshot_is_stable(self) -> None:
        from scholarflow_api.main import app

        schema = app.openapi()
        route_methods = {
            path: sorted(
                method.upper()
                for method in definition
                if method in {"get", "post", "put", "patch", "delete"}
            )
            for path, definition in sorted(schema["paths"].items())
        }
        self.assertEqual(route_methods, EXPECTED_ROUTE_METHODS)

    def test_artifact_summary_is_paginated_and_detail_is_complete(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            db_path = Path(tmpdir) / "refactor-artifacts.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                from scholarflow_api.database import init_db
                from scholarflow_api.main import (
                    create_project,
                    get_artifact,
                    list_project_artifact_summaries,
                    save_artifact,
                )
                from scholarflow_api.schemas import ArtifactCreate, ProjectCreate

                init_db()
                project = create_project(ProjectCreate(title="Artifact transport contract"))
                body = "evidence-body-" * 1000
                created = [
                    save_artifact(
                        ArtifactCreate(
                            project_id=project.id,
                            title=f"artifact-{index}.md",
                            content_markdown=body + str(index),
                            content_json=json.dumps(
                                {"schema_version": "contract.v1", "index": index}
                            ),
                        )
                    )
                    for index in range(3)
                ]

                first_page = list_project_artifact_summaries(
                    project.id,
                    limit=2,
                    offset=0,
                )
                second_page = list_project_artifact_summaries(
                    project.id,
                    limit=2,
                    offset=2,
                )
                detail = get_artifact(created[-1].id)

        self.assertEqual(first_page.total, 3)
        self.assertEqual(first_page.limit, 2)
        self.assertEqual(first_page.offset, 0)
        self.assertEqual(first_page.next_offset, 2)
        self.assertEqual(len(first_page.items), 2)
        self.assertEqual(len(second_page.items), 1)
        self.assertIsNone(second_page.next_offset)
        self.assertFalse(hasattr(first_page.items[0], "content_markdown"))
        self.assertFalse(hasattr(first_page.items[0], "content_json"))
        self.assertEqual(detail.content_markdown, body + "2")
        self.assertEqual(
            json.loads(detail.content_json),
            {"schema_version": "contract.v1", "index": 2},
        )

    def test_route_endpoints_live_outside_main_module(self) -> None:
        from scholarflow_api.main import app

        def walk_routes(router):
            for route in router.routes:
                original_router = getattr(route, "original_router", None)
                if original_router is not None:
                    yield from walk_routes(original_router)
                else:
                    yield route

        endpoint_modules = {
            route.endpoint.__module__
            for route in walk_routes(app)
            if getattr(route, "path", "").startswith("/projects")
            or getattr(route, "path", "").startswith("/artifacts")
        }
        self.assertTrue(endpoint_modules)
        self.assertNotIn("scholarflow_api.main", endpoint_modules)

    def test_generated_types_match_current_openapi(self) -> None:
        from scholarflow_api.openapi_types import render_typescript_api_types
        from scholarflow_api.main import app

        generated_path = (
            Path(__file__).resolve().parents[3]
            / "packages"
            / "schemas"
            / "src"
            / "api.generated.ts"
        )
        self.assertEqual(
            generated_path.read_text(encoding="utf-8"),
            render_typescript_api_types(app.openapi()),
        )
        compatibility_index = generated_path.with_name("index.ts").read_text(
            encoding="utf-8"
        )
        for alias in (
            'ApiSchema<"Project">',
            'ApiSchema<"Artifact">',
            'ApiSchema<"ArtifactSummaryPage">',
            'ApiSchema<"LiteratureSearchRequest">',
            'ApiSchema<"RagAnswerRequest">',
            'ApiSchema<"AgentPlanRequest">',
        ):
            self.assertIn(alias, compatibility_index)


if __name__ == "__main__":
    unittest.main()
