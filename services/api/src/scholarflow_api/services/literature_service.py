from __future__ import annotations

from scholarflow_api.api_helpers import (
    artifact_ref,
    ensure_active_session,
    ensure_project_exists,
    fetch_project_dict,
    fetch_project_papers_by_ids,
    insert_artifact_row,
    insert_paper_candidates,
)
from scholarflow_api.database import get_connection, utc_now
from scholarflow_api.literature import (
    LOW_RECALL_THRESHOLD,
    render_paper_table_json,
    render_paper_table_markdown,
    search_literature,
)
from scholarflow_api.repositories.literature_repository import (
    list_project_paper_rows,
    mark_literature_retrieved,
)
from scholarflow_api.repositories.tool_event_repository import insert_tool_event
from scholarflow_api.schemas import (
    Artifact,
    ArtifactRef,
    LiteratureSearchRequest,
    LiteratureSearchResponse,
    Paper,
    WorkflowStepState,
)


def _literature_step_status(
    paper_count: int,
    errors: list[str],
    relevance_coverage: dict[str, int] | None = None,
) -> str:
    coverage = relevance_coverage or {}
    if paper_count <= 0:
        return "error" if errors else "blocked"
    if coverage.get("off_topic_count", 0) > 0 or coverage.get("weak_match_count", 0) > 0:
        return "partial"
    if coverage.get("returned_count", paper_count) < LOW_RECALL_THRESHOLD:
        return "partial"
    if any(error.startswith("low_recall:") for error in errors):
        return "partial"
    if errors:
        return "partial"
    return "complete"


def list_project_papers(project_id: str) -> list[Paper]:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        rows = list_project_paper_rows(connection, project_id)
    return [Paper.model_validate(dict(row)) for row in rows]


def search_project_literature(
    project_id: str,
    payload: LiteratureSearchRequest,
) -> LiteratureSearchResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, now)
        insert_tool_event(
            connection,
            session_id,
            "literature.query_expand",
            "running",
            f"正在基于关键词生成检索式：{payload.query}",
            now,
        )

    result = search_literature(payload.query, payload.max_results, payload.sources)
    completed_at = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, completed_at)
        paper_ids = insert_paper_candidates(connection, project_id, result.papers, completed_at)
        artifact = insert_artifact_row(
            connection=connection,
            project_id=project_id,
            title="paper_table.md",
            kind="markdown",
            content_markdown=render_paper_table_markdown(result),
            content_json=render_paper_table_json(result),
            diff="+ Retrieved papers from arXiv/OpenAlex\n+ Ranked and deduplicated paper table",
            now=completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "literature.query_expand",
            "done",
            f"生成 {len(result.expanded_queries)} 组检索式。",
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "literature.retrieve",
            "done" if result.papers else "queued",
            f"检索并排序 {len(result.papers)} 篇论文；errors={len(result.errors)}。",
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "artifact.save",
            "done",
            f"已保存结构化 paper table artifact: {artifact['title']}",
            completed_at,
        )
        mark_literature_retrieved(connection, project_id, completed_at)
        rows = fetch_project_papers_by_ids(connection, project_id, paper_ids)

    workflow_step = WorkflowStepState(
        step_id="paper-table",
        status=_literature_step_status(len(rows), result.errors, result.relevance_coverage),  # type: ignore[arg-type]
        label="Paper Table",
        summary=(
            f"{result.relevance_coverage.get('candidate_count', len(rows))} candidates / "
            f"{result.relevance_coverage.get('eligible_count', result.relevance_coverage.get('returned_count', len(rows)))} eligible / "
            f"{result.relevance_coverage.get('returned_count', len(rows))} returned / "
            f"{result.relevance_coverage.get('truncated_count', 0)} truncated / "
            f"{result.relevance_coverage.get('off_topic_count', 0)} off-topic filtered"
        ),
        warnings=result.errors,
        artifact_refs=[ArtifactRef.model_validate(artifact_ref(artifact))],
        updated_at=completed_at,
    )
    return LiteratureSearchResponse(
        query=result.query,
        expanded_queries=result.expanded_queries,
        papers=[Paper.model_validate(dict(row)) for row in rows],
        artifact=Artifact.model_validate(artifact),
        errors=result.errors,
        relevance_coverage=result.relevance_coverage,
        workflow_steps=[workflow_step],
    )
