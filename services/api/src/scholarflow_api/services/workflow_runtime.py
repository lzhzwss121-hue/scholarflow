from __future__ import annotations

import json

from fastapi import APIRouter, Body, HTTPException

from scholarflow_api import __version__
from scholarflow_api.api_helpers import (
    build_paper_card_source,
    ensure_active_session,
    ensure_project_exists,
    fetch_paper_dict,
    fetch_project_dict,
    fetch_project_paper_card_dicts,
    insert_artifact_row,
)
from scholarflow_api.database import get_connection, new_id, row_to_dict, utc_now
from scholarflow_api.full_text import FullTextResult, parse_pdf_bytes, provided_full_text, resolve_open_full_text
from scholarflow_api.jobs.repository import worker_health
from scholarflow_api.paper_card import (
    generate_deep_paper_card,
    paper_slug,
    render_card_json,
    render_card_markdown,
)
from scholarflow_api.rag_index import index_paper_full_text
from scholarflow_api.repositories.workflow import statement as workflow_sql
from scholarflow_api.repositories.tool_event_repository import insert_tool_event
from scholarflow_api.schemas import (
    Artifact,
    HealthResponse,
    PaperCard,
    PaperCardCreateRequest,
    PaperCardResponse,
    PaperFullTextExtractResponse,
    Project,
    ProjectCreate,
    Session,
    ToolEvent,
)
from scholarflow_api.services.agent_plan_service import is_demo_project_dict


router = APIRouter()


def project_response_dict(project: dict) -> dict:
    data = dict(project)
    data["is_demo"] = is_demo_project_dict(data)
    return data




@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="scholarflow-api",
        version=__version__,
    )


@router.get("/health/jobs")
def jobs_health(worker_id: str | None = None) -> dict:
    return worker_health(worker_id=worker_id)


@router.get("/projects", response_model=list[Project])
def list_projects() -> list[Project]:
    with get_connection() as connection:
        rows = connection.execute(
            workflow_sql("list_projects_1")
        ).fetchall()
    return [Project.model_validate(project_response_dict(dict(row))) for row in rows]


@router.post("/projects", response_model=Project, status_code=201)
def create_project(payload: ProjectCreate) -> Project:
    now = utc_now()
    project_id = new_id("project")
    session_id = new_id("session")
    with get_connection() as connection:
        connection.execute(
            workflow_sql("create_project_1"),
            (
                project_id,
                payload.title,
                payload.description,
                payload.keyword,
                payload.field,
                payload.language,
                payload.workflow,
                "api",
                session_id,
                now,
                now,
            ),
        )
        connection.execute(
            workflow_sql("create_project_2"),
            (session_id, project_id, "Research planning session", "active", now, now),
        )
        connection.executemany(
            workflow_sql("create_project_3"),
            [
                (
                    new_id("event"),
                    session_id,
                    "Now",
                    "project.create",
                    "done",
                    "已创建本地 research project，并初始化 session timeline。",
                    now,
                ),
                (
                    new_id("event"),
                    session_id,
                    "Next",
                    "artifact.save",
                    "queued",
                    "等待用户保存第一份 artifact。",
                    now,
                ),
            ],
        )
        row = connection.execute(
            workflow_sql("create_project_4"),
            (project_id,),
        ).fetchone()
    return Project.model_validate(project_response_dict(dict(row)))


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    with get_connection() as connection:
        row = connection.execute(
            workflow_sql("get_project_1"),
            (project_id,),
        ).fetchone()
    project = row_to_dict(row)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return Project.model_validate(project_response_dict(project))


@router.get("/projects/{project_id}/paper-cards", response_model=list[PaperCard])
def list_project_paper_cards(project_id: str) -> list[PaperCard]:
    """Return one evidence-best persisted card per paper_id.

    Artifacts remain append-only for auditability. This projection is the read
    contract used by the UI, so an older abstract/download-failure artifact
    cannot overwrite a verified full-text card for the same paper.
    """
    ensure_project_exists(project_id)
    with get_connection() as connection:
        rows = fetch_project_paper_card_dicts(connection, project_id)
    return [paper_card_from_row(row) for row in rows]


def paper_card_from_row(row: dict) -> PaperCard:
    sections = parse_json_list(row.get("sections_json"))
    signals = row.get("signals") if isinstance(row.get("signals"), dict) else {}
    full_text = row.get("full_text") if isinstance(row.get("full_text"), dict) else {}
    evidence_qualification = (
        row.get("evidence_qualification")
        if isinstance(row.get("evidence_qualification"), dict)
        else {}
    )
    artifact_title = str(row.get("artifact_title") or "")
    card_source = (
        "direction_review_artifact"
        if "direction_round" in artifact_title.lower()
        else ("paper_table" if row.get("paper_id") else "manual_unbound")
    )
    return PaperCard(
        id=str(row.get("id") or ""),
        project_id=str(row.get("project_id") or ""),
        paper_id=row.get("paper_id") or None,
        paper_title=str(row.get("paper_title") or ""),
        artifact_id=row.get("artifact_id") or None,
        source_artifact_title=artifact_title,
        card_source=card_source,
        evidence_level=str(row.get("evidence_level") or "metadata_only"),
        evidence_qualification=evidence_qualification,
        full_text=full_text,
        signals=signals,
        sections=sections,
        weakest_assumption=str(row.get("weakest_assumption") or ""),
        minimal_reproduction=str(row.get("minimal_reproduction") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or row.get("created_at") or ""),
    )


def parse_json_list(value: object) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    try:
        parsed = json.loads(str(value or "[]"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


@router.post("/projects/{project_id}/paper-cards", response_model=PaperCardResponse, status_code=201)
def create_project_paper_card(project_id: str, payload: PaperCardCreateRequest) -> PaperCardResponse:
    with get_connection() as connection:
        paper = build_paper_card_source(connection, project_id, payload)
    full_text = provided_full_text(payload.paper_text) if payload.paper_text else resolve_open_full_text(paper)
    return persist_project_paper_card(project_id, payload, full_text)


def persist_project_paper_card(
    project_id: str,
    payload: PaperCardCreateRequest,
    full_text: FullTextResult,
) -> PaperCardResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, now)
        paper = build_paper_card_source(connection, project_id, payload)
        qualification = full_text.evidence_qualification(
            has_abstract=bool(str(paper.get("abstract") or "").strip()),
        )
        card_text = (
            payload.paper_text
            if qualification.level == "supplemental_text"
            else full_text.text
            if qualification.level == "full_text" and qualification.verified
            else ""
        )
        card = generate_deep_paper_card(
            paper,
            card_text,
            evidence_qualification=qualification,
        )
        provenance = full_text.to_provenance(qualification)
        artifact = insert_artifact_row(
            connection=connection,
            project_id=project_id,
            title=f"paper_card_{paper_slug(card.paper_title)}.md",
            kind="markdown",
            content_markdown=render_card_markdown(card, paper, provenance),
            content_json=render_card_json(card, paper, provenance, updated_at=now),
            diff="+ Generated 12-section Deep Paper Card\n+ Saved structured JSON for downstream gap analysis",
            now=now,
        )
        card_id = new_id("paper_card")
        connection.execute(
            workflow_sql("persist_project_paper_card_1"),
            (
                card_id,
                project_id,
                payload.paper_id,
                artifact["id"],
                json.dumps([section.to_dict() for section in card.sections], ensure_ascii=False, indent=2),
                card.weakest_assumption,
                card.minimal_reproduction,
                now,
            ),
        )
        if (
            payload.paper_id
            and qualification.level == "full_text"
            and qualification.verified
        ):
            index_paper_full_text(
                connection,
                project_id=project_id,
                paper_id=payload.paper_id,
                text=full_text.text,
                source_origin=full_text.source,
                now=now,
                evidence_verified=qualification.verified,
            )
        insert_tool_event(
            connection,
            session_id,
            "paper_card.generate",
            "done",
            f"已生成 12 段 Deep Paper Card: {card.paper_title}",
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "artifact.save",
            "done",
            f"已保存 paper card artifact: {artifact['title']}",
            now,
        )
        connection.execute(
            workflow_sql("persist_project_paper_card_2"),
            ("paper-card", now, project_id),
        )

    return PaperCardResponse(
        card=PaperCard(
            id=card_id,
            project_id=project_id,
            paper_id=payload.paper_id,
            paper_title=card.paper_title,
            artifact_id=artifact["id"],
            source_artifact_title=artifact["title"],
            card_source="paper_table" if payload.paper_id else "manual_unbound",
            evidence_level=card.evidence_level,
            evidence_qualification=card.evidence_qualification,
            full_text=provenance,
            signals=card.signals.to_dict(),
            sections=[section.to_dict() for section in card.sections],
            weakest_assumption=card.weakest_assumption,
            minimal_reproduction=card.minimal_reproduction,
            created_at=now,
            updated_at=now,
        ),
        artifact=Artifact.model_validate(artifact),
    )


@router.post(
    "/projects/{project_id}/papers/{paper_id}/full-text",
    response_model=PaperFullTextExtractResponse,
)
def extract_project_paper_full_text(
    project_id: str,
    paper_id: str,
    payload: bytes = Body(..., media_type="application/pdf"),
) -> PaperFullTextExtractResponse:
    """Parse a user-supplied PDF without pretending a failed parse is full-text evidence."""
    with get_connection() as connection:
        paper = fetch_paper_dict(connection, project_id, paper_id)
    result = parse_pdf_bytes(payload, source="user_uploaded_pdf")
    qualification = result.evidence_qualification(
        has_abstract=bool(str(paper.get("abstract") or "").strip()),
    )
    generated = (
        persist_project_paper_card(
            project_id,
            PaperCardCreateRequest(paper_id=paper_id),
            result,
        )
        if qualification.level == "full_text" and qualification.verified
        else None
    )
    updated_at = generated.card.updated_at if generated else utc_now()
    return PaperFullTextExtractResponse(
        paper_id=paper_id,
        text=(
            result.text
            if qualification.level == "full_text" and qualification.verified
            else ""
        ),
        evidence_level=qualification.level,
        evidence_quality=qualification.level,
        evidence_qualification=qualification,
        source=result.source,
        page_count=result.page_count,
        char_count=result.character_count,
        updated_at=updated_at,
        full_text=result.to_provenance(qualification),
        card=generated.card if generated else None,
        artifact=generated.artifact if generated else None,
    )


@router.get("/projects/{project_id}/sessions", response_model=list[Session])
def list_project_sessions(project_id: str) -> list[Session]:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            workflow_sql("list_project_sessions_1"),
            (project_id,),
        ).fetchall()
    return [Session.model_validate(dict(row)) for row in rows]


@router.get("/sessions/{session_id}/timeline", response_model=list[ToolEvent])
def get_session_timeline(session_id: str) -> list[ToolEvent]:
    with get_connection() as connection:
        session = connection.execute(
            workflow_sql("get_session_timeline_1"),
            (session_id,),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        rows = connection.execute(
            workflow_sql("get_session_timeline_2"),
            (session_id,),
        ).fetchall()
    return [ToolEvent.model_validate(dict(row)) for row in rows]


@router.get("/projects/{project_id}/timeline", response_model=list[ToolEvent])
def get_project_timeline(project_id: str) -> list[ToolEvent]:
    project = get_project(project_id)
    if not project.active_session_id:
        return []
    return get_session_timeline(project.active_session_id)
