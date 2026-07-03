from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import hashlib
import json
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from scholarflow_api import __version__
from scholarflow_api.agent_core import (
    ToolContext,
    ToolRegistry,
    ToolResult,
    build_mock_papers,
    get_model_provider,
    render_execution_markdown,
    render_plan_markdown,
)
from scholarflow_api.api_helpers import (
    artifact_ref,
    build_paper_card_source,
    collect_agent_summary_metrics,
    completed_plan_snapshot,
    ensure_active_session,
    ensure_project_exists,
    fail_agent_run_step,
    fetch_artifact_dict,
    fetch_paper_dict,
    fetch_project_dict,
    fetch_project_paper_card_dicts,
    fetch_project_paper_dicts,
    fetch_project_papers_by_ids,
    fetch_read_paper_titles,
    infer_agent_direction,
    infer_agent_paper_count,
    infer_tool_summary_metrics,
    insert_artifact_row,
    insert_paper_candidates,
    insert_tool_event,
    mark_plan_step_by_id,
    next_agent_direction_round,
    output_summary,
    to_direction_memory_response,
    to_paper_memory_hit,
)
from scholarflow_api.baseline_map import build_baseline_map, render_baseline_map_markdown
from scholarflow_api.database import artifact_summary_from_row, get_connection, init_db, new_id, row_to_dict, utc_now
from scholarflow_api.direction_review import (
    build_direction_readings,
    build_direction_review_bundle,
    render_direction_review_json,
    render_direction_review_markdown,
    retrieve_direction_candidate_pool,
)
from scholarflow_api.literature import render_paper_table_json, render_paper_table_markdown, search_literature
from scholarflow_api.paper_card import (
    generate_deep_paper_card,
    paper_slug,
    render_card_json,
    render_card_markdown,
)
from scholarflow_api.research_decisions import (
    generate_research_decisions,
    render_decision_json,
    render_experiment_markdown,
    render_gap_board_markdown,
    render_validation_markdown,
)
from scholarflow_api.research_memory import (
    query_research_memory,
    render_research_memory_answer_markdown,
    upsert_direction_memory_snapshot,
    upsert_direction_reading_memories,
)
from scholarflow_api.schemas import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentPlanRequest,
    AgentPlanResponse,
    Artifact,
    ArtifactCreate,
    ArtifactRef,
    ArtifactSummary,
    BaselineMap,
    DirectionReviewRequest,
    DirectionReviewResponse,
    HealthResponse,
    LiteratureSearchRequest,
    LiteratureSearchResponse,
    Paper,
    PaperCard,
    PaperCardCreateRequest,
    PaperCardResponse,
    Project,
    ProjectCreate,
    ResearchSight,
    ResearchDecisionRequest,
    ResearchDecisionResponse,
    DirectionMemory,
    PaperMemoryHit,
    ResearchMemoryQueryRequest,
    ResearchMemoryQueryResponse,
    Session,
    ToolEvent,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="ScholarFlow API",
    version=__version__,
    description="Backend API and persistence layer for the ScholarFlow research workflow agent.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="scholarflow-api",
        version=__version__,
    )


@app.get("/projects", response_model=list[Project])
def list_projects() -> list[Project]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM projects
            ORDER BY CASE WHEN id = 'local-bootstrap' THEN 0 ELSE 1 END,
                     updated_at DESC,
                     created_at DESC
            """
        ).fetchall()
    return [Project.model_validate(dict(row)) for row in rows]


@app.post("/projects", response_model=Project, status_code=201)
def create_project(payload: ProjectCreate) -> Project:
    now = utc_now()
    project_id = new_id("project")
    session_id = new_id("session")
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id, title, description, keyword, field, language, workflow, stage,
                active_session_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
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
            """
            INSERT INTO sessions (id, project_id, title, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, project_id, "Research planning session", "active", now, now),
        )
        connection.executemany(
            """
            INSERT INTO tool_events (id, session_id, time_label, tool, status, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
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
            "SELECT * FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    return Project.model_validate(dict(row))


@app.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    project = row_to_dict(row)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return Project.model_validate(project)


@app.get("/projects/{project_id}/papers", response_model=list[Paper])
def list_project_papers(project_id: str) -> list[Paper]:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM papers
            WHERE project_id = ?
            ORDER BY
                CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
                relevance_score DESC,
                year DESC
            """,
            (project_id,),
        ).fetchall()
    return [Paper.model_validate(dict(row)) for row in rows]


@app.post("/projects/{project_id}/literature/search", response_model=LiteratureSearchResponse)
def search_project_literature(project_id: str, payload: LiteratureSearchRequest) -> LiteratureSearchResponse:
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
        connection.execute(
            "DELETE FROM papers WHERE project_id = ?",
            (project_id,),
        )
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
        connection.execute(
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            ("literature-retrieval", completed_at, project_id),
        )
        rows = fetch_project_papers_by_ids(connection, project_id, paper_ids)

    return LiteratureSearchResponse(
        query=result.query,
        expanded_queries=result.expanded_queries,
        papers=[Paper.model_validate(dict(row)) for row in rows],
        artifact=Artifact.model_validate(artifact),
        errors=result.errors,
    )


@app.post("/projects/{project_id}/paper-cards", response_model=PaperCardResponse, status_code=201)
def create_project_paper_card(project_id: str, payload: PaperCardCreateRequest) -> PaperCardResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, now)
        paper = build_paper_card_source(connection, project_id, payload)
        card = generate_deep_paper_card(paper, payload.paper_text)
        artifact = insert_artifact_row(
            connection=connection,
            project_id=project_id,
            title=f"paper_card_{paper_slug(card.paper_title)}.md",
            kind="markdown",
            content_markdown=render_card_markdown(card, paper),
            content_json=render_card_json(card, paper),
            diff="+ Generated 12-section Deep Paper Card\n+ Saved structured JSON for downstream gap analysis",
            now=now,
        )
        card_id = new_id("paper_card")
        connection.execute(
            """
            INSERT INTO paper_cards (
                id, project_id, paper_id, artifact_id, sections_json, weakest_assumption,
                minimal_reproduction, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
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
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            ("paper-card", now, project_id),
        )

    return PaperCardResponse(
        card=PaperCard(
            id=card_id,
            project_id=project_id,
            paper_id=payload.paper_id,
            artifact_id=artifact["id"],
            signals=card.signals.to_dict(),
            sections=[section.to_dict() for section in card.sections],
            weakest_assumption=card.weakest_assumption,
            minimal_reproduction=card.minimal_reproduction,
            created_at=now,
        ),
        artifact=Artifact.model_validate(artifact),
    )


@app.post("/projects/{project_id}/direction-reviews", response_model=DirectionReviewResponse, status_code=201)
def create_project_direction_review(project_id: str, payload: DirectionReviewRequest) -> DirectionReviewResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, now)
        previous_titles = fetch_read_paper_titles(connection, project_id) if payload.round > 1 else []
        insert_tool_event(
            connection,
            session_id,
            "direction.scope",
            "running",
            f"正在界定研究方向并准备第 {payload.round} 轮 10 篇论文阅读：{payload.direction}",
            now,
        )

    scope, candidate_pool, candidates, errors = retrieve_direction_candidate_pool(payload.direction, payload.round, previous_titles)
    completed_at = utc_now()
    artifacts: list[dict] = []
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, completed_at)
        paper_ids = insert_paper_candidates(connection, project_id, candidates, completed_at)
        paper_dicts = [fetch_paper_dict(connection, project_id, paper_id) for paper_id in paper_ids]
        baseline_map = build_baseline_map(
            payload.direction,
            [candidate.to_dict() for candidate in candidate_pool],
            paper_dicts,
        )
        readings = build_direction_readings(paper_dicts, payload.direction, baseline_map)
        bundle = build_direction_review_bundle(
            payload.direction,
            payload.round,
            scope,
            baseline_map,
            readings,
            previous_read_count=len(previous_titles),
            errors=errors,
        )
        baseline_artifact = insert_artifact_row(
            connection=connection,
            project_id=project_id,
            title=f"baseline_map_round_{payload.round}_{paper_slug(payload.direction)}.md",
            kind="markdown",
            content_markdown=render_baseline_map_markdown(baseline_map),
            content_json=json.dumps(baseline_map.to_dict(), ensure_ascii=False, indent=2),
            diff="+ Generated BaselineMap\n+ Added classic, recent, and alternative-paradigm references",
            now=completed_at,
        )
        artifacts.append(baseline_artifact)
        review_artifact = insert_artifact_row(
            connection=connection,
            project_id=project_id,
            title=f"direction_review_round_{payload.round}.md",
            kind="markdown",
            content_markdown=render_direction_review_markdown(bundle),
            content_json=render_direction_review_json(bundle),
            diff="+ Generated ten-paper direction review\n+ Added summary and top-3 personal reading recommendations",
            now=completed_at,
        )
        artifacts.append(review_artifact)

        for reading in readings:
            card_artifact = insert_artifact_row(
                connection=connection,
                project_id=project_id,
                title=f"direction_round_{payload.round}_paper_card_{paper_slug(reading.card.paper_title)}.md",
                kind="markdown",
                content_markdown=render_card_markdown(reading.card, reading.paper),
                content_json=json.dumps(reading.to_dict(), ensure_ascii=False, indent=2),
                diff="+ Generated direction-review paper card\n+ Added abstract translation for interactive UI",
                now=completed_at,
            )
            artifacts.append(card_artifact)
            connection.execute(
                """
                INSERT INTO paper_cards (
                    id, project_id, paper_id, artifact_id, sections_json, weakest_assumption,
                    minimal_reproduction, research_sight_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("paper_card"),
                    project_id,
                    reading.paper.get("id"),
                    card_artifact["id"],
                    json.dumps([section.to_dict() for section in reading.card.sections], ensure_ascii=False, indent=2),
                    reading.card.weakest_assumption,
                    reading.card.minimal_reproduction,
                    json.dumps(reading.research_sight.to_dict(), ensure_ascii=False, indent=2),
                    completed_at,
                ),
            )

        upsert_direction_reading_memories(
            connection,
            project_id,
            payload.direction,
            payload.round,
            readings,
            completed_at,
        )
        direction_memory = upsert_direction_memory_snapshot(
            connection,
            project_id,
            payload.direction,
            completed_at,
            baseline_map=baseline_map.to_dict(),
        )
        memory_artifact = insert_artifact_row(
            connection=connection,
            project_id=project_id,
            title=f"direction_memory_{paper_slug(payload.direction)}.md",
            kind="markdown",
            content_markdown="\n\n".join(
                [
                    f"# Direction Memory: {direction_memory.direction}",
                    direction_memory.summary,
                    f"Total papers: {direction_memory.total_papers}",
                    f"Rounds: {direction_memory.round_count}",
                ],
            ),
            content_json=json.dumps(direction_memory.to_dict(), ensure_ascii=False, indent=2),
            diff="+ Updated paper memory bank\n+ Updated cumulative direction memory snapshot",
            now=completed_at,
        )
        artifacts.append(memory_artifact)

        insert_tool_event(
            connection,
            session_id,
            "direction.scope",
            "done",
            f"已界定方向范围：{scope.year_range}，子方向 {len(scope.subtopics)} 个。",
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "direction.retrieve",
            "done" if readings else "queued",
            (
                f"partial：第 {payload.round} 轮仅筛选 {len(readings)}/10 篇论文，不能视为完整方向级 10 篇精读。"
                if len(readings) < 5
                else f"第 {payload.round} 轮检索并筛选 {len(readings)} 篇近三年高相关论文。"
            ),
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "direction.read",
            "done" if readings else "queued",
            (
                f"partial：已生成 {len(readings)} 张论文精读卡片，低于 5 篇可信阈值。"
                if len(readings) < 5
                else f"已生成 {len(readings)} 张 12 条规则论文精读卡片。"
            ),
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "baseline.curate",
            "done",
            f"已生成 BaselineMap：经典 {len(baseline_map.classic_baselines)} 篇，近三年强参照 {len(baseline_map.recent_strong_baselines)} 篇，异质范式 {len(baseline_map.alternative_paradigms)} 篇。",
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "direction.summarize",
            "done",
            (
                f"partial：已生成临时方向总结；本轮仅 {len(readings)}/10 篇，推荐需谨慎使用。"
                if bundle.review_status == "partial"
                else f"已生成方向总结，并推荐 {len(bundle.recommended_paper_ids)} 篇用户亲自精读论文。"
            ),
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "memory.write",
            "done",
            f"已写入 Paper Memory Bank：累计 {direction_memory.total_papers} 篇，轮次 {direction_memory.round_count}。",
            completed_at,
        )
        connection.execute(
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            ("direction-review", completed_at, project_id),
        )

    return DirectionReviewResponse(
        direction=bundle.direction,
        round=bundle.round,
        review_status=bundle.review_status,
        target_paper_count=bundle.target_paper_count,
        round_read_count=len(bundle.readings),
        total_read_count=bundle.total_read_count,
        recommended_paper_ids=bundle.recommended_paper_ids,
        direction_summary=bundle.direction_summary,
        artifact_refs=[ArtifactRef.model_validate(artifact) for artifact in artifacts],
        errors=bundle.errors,
    )


@app.post("/projects/{project_id}/research-decisions", response_model=ResearchDecisionResponse, status_code=201)
def create_project_research_decisions(project_id: str, payload: ResearchDecisionRequest) -> ResearchDecisionResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, now)
        papers = fetch_project_paper_dicts(connection, project_id)
        paper_cards = fetch_project_paper_card_dicts(connection, project_id)
        bundle = generate_research_decisions(project, papers, paper_cards, payload.goal)
        bundle_json = render_decision_json(bundle)
        artifacts = [
            insert_artifact_row(
                connection=connection,
                project_id=project_id,
                title="gap_board.md",
                kind="markdown",
                content_markdown=render_gap_board_markdown(bundle),
                content_json=bundle_json,
                diff="+ Generated gap board\n+ Classified true/engineering/pseudo gaps",
                now=now,
            ),
            insert_artifact_row(
                connection=connection,
                project_id=project_id,
                title="idea_validation_report.md",
                kind="markdown",
                content_markdown=render_validation_markdown(bundle),
                content_json=bundle_json,
                diff="+ Added novelty risk\n+ Added differentiation from existing work",
                now=now,
            ),
            insert_artifact_row(
                connection=connection,
                project_id=project_id,
                title="experiment_plan.md",
                kind="markdown",
                content_markdown=render_experiment_markdown(bundle),
                content_json=bundle_json,
                diff="+ Added baseline/dataset/metric/ablation/resource plan",
                now=now,
            ),
        ]
        insert_tool_event(
            connection,
            session_id,
            "gap.generate",
            "done",
            f"已生成 {len(bundle.gaps)} 个 gap，并区分 true / engineering / pseudo gap。",
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "novelty.validate",
            "done",
            f"已生成 novelty risk={bundle.validation.novelty_risk} 的 idea validation report。",
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "experiment.plan",
            "done",
            "已生成包含 baseline、dataset、metric、ablation、resource estimate 的实验计划。",
            now,
        )
        connection.execute(
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            ("experiment-planning", now, project_id),
        )

    return ResearchDecisionResponse(
        gaps=[gap.to_dict() for gap in bundle.gaps],
        validation=bundle.validation.to_dict(),
        experiment=bundle.experiment.to_dict(),
        artifacts=[Artifact.model_validate(artifact) for artifact in artifacts],
    )


@app.post("/projects/{project_id}/research-memory/query", response_model=ResearchMemoryQueryResponse, status_code=201)
def query_project_research_memory(project_id: str, payload: ResearchMemoryQueryRequest) -> ResearchMemoryQueryResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, now)
        insert_tool_event(
            connection,
            session_id,
            "memory.retrieve",
            "running",
            f"正在从 Paper Memory Bank 检索 {payload.top_k} 篇相关论文。",
            now,
        )
        answer = query_research_memory(
            connection,
            project_id=project_id,
            question=payload.question,
            top_k=payload.top_k,
            now=now,
            direction=payload.direction,
        )
        answer_json = json.dumps(answer.to_dict(), ensure_ascii=False, indent=2)
        artifact = insert_artifact_row(
            connection=connection,
            project_id=project_id,
            title=f"research_memory_answer_{paper_slug(payload.question)}.md",
            kind="markdown",
            content_markdown=render_research_memory_answer_markdown(answer),
            content_json=answer_json,
            diff="+ Retrieved 3-8 paper memories\n+ Generated memory-grounded answer",
            now=now,
        )
        insert_tool_event(
            connection,
            session_id,
            "memory.retrieve",
            "done" if answer.hits else "queued",
            f"命中 {len(answer.hits)} 篇论文记忆；memory bank 总量 {answer.total_memories}。",
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "memory.answer",
            "done",
            f"已生成基于 {len(answer.hits)} 篇论文记忆的回答 artifact。",
            now,
        )
        connection.execute(
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            ("research-memory", now, project_id),
        )

    return ResearchMemoryQueryResponse(
        question=answer.question,
        top_k=answer.top_k,
        answer=answer.answer,
        hits=[to_paper_memory_hit(hit) for hit in answer.hits],
        direction_memory=to_direction_memory_response(answer.direction_memory) if answer.direction_memory else None,
        total_memories=answer.total_memories,
        artifact=Artifact.model_validate(artifact),
        warnings=answer.warnings,
    )


@app.get("/projects/{project_id}/artifacts", response_model=list[Artifact])
def list_project_artifacts(project_id: str) -> list[Artifact]:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM artifacts WHERE project_id = ? ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
    return [Artifact.model_validate(dict(row)) for row in rows]


@app.get("/projects/{project_id}/artifacts/summary", response_model=list[ArtifactSummary])
def list_project_artifact_summaries(project_id: str) -> list[ArtifactSummary]:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                project_id,
                title,
                kind,
                created_at,
                updated_at,
                length(CAST(content_markdown AS BLOB)) AS markdown_bytes,
                length(CAST(content_json AS BLOB)) AS json_bytes,
                substr(content_markdown, 1, 280) AS markdown_preview,
                CASE
                    WHEN json_valid(content_json)
                    THEN COALESCE(json_extract(content_json, '$.schema_version'), '')
                    ELSE ''
                END AS json_schema_version
            FROM artifacts
            WHERE project_id = ?
            ORDER BY updated_at DESC
            """,
            (project_id,),
        ).fetchall()
    return [ArtifactSummary.model_validate(artifact_summary_from_row(row)) for row in rows]


@app.post("/artifacts", response_model=Artifact, status_code=201)
def save_artifact(payload: ArtifactCreate) -> Artifact:
    ensure_project_exists(payload.project_id)
    now = utc_now()
    artifact_id = new_id("artifact")
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO artifacts (
                id, project_id, title, kind, content_markdown, content_json,
                diff, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                payload.project_id,
                payload.title,
                payload.kind,
                payload.content_markdown,
                payload.content_json,
                payload.diff,
                now,
                now,
            ),
        )
        session_row = connection.execute(
            "SELECT active_session_id FROM projects WHERE id = ?",
            (payload.project_id,),
        ).fetchone()
        if session_row and session_row["active_session_id"]:
            connection.execute(
                """
                INSERT INTO tool_events (id, session_id, time_label, tool, status, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("event"),
                    session_row["active_session_id"],
                    "Now",
                    "artifact.save",
                    "done",
                    f"已保存 artifact: {payload.title}",
                    now,
                ),
            )
        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (now, payload.project_id),
        )
        row = connection.execute(
            "SELECT * FROM artifacts WHERE id = ?",
            (artifact_id,),
        ).fetchone()
    return Artifact.model_validate(dict(row))


@app.get("/artifacts/{artifact_id}", response_model=Artifact)
def get_artifact(artifact_id: str) -> Artifact:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM artifacts WHERE id = ?",
            (artifact_id,),
        ).fetchone()
    artifact = row_to_dict(row)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return Artifact.model_validate(artifact)


@app.post("/agent/plan", response_model=AgentPlanResponse, status_code=201)
def create_agent_plan(payload: AgentPlanRequest) -> AgentPlanResponse:
    now = utc_now()
    run_id = new_id("run")
    with get_connection() as connection:
        project = fetch_project_dict(connection, payload.project_id)
        session_id = ensure_active_session(connection, project, now)
        provider = get_model_provider(payload.provider)
        draft = provider.create_plan(payload.task, project)
        plan = draft.to_dict()
        plan_artifact = insert_artifact_row(
            connection=connection,
            project_id=payload.project_id,
            title=f"agent_plan_{run_id}.md",
            kind="markdown",
            content_markdown=render_plan_markdown(payload.task, project, plan),
            content_json=json.dumps(
                {
                    "run_id": run_id,
                    "task": payload.task,
                    "plan": plan,
                },
                ensure_ascii=False,
                indent=2,
            ),
            diff="+ Created Research Plan Mode artifact",
            now=now,
        )
        connection.execute(
            """
            INSERT INTO agent_runs (
                id, project_id, session_id, task, provider, mode, status,
                plan_json, plan_artifact_id, result_artifact_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                payload.project_id,
                session_id,
                payload.task,
                draft.provider,
                "plan",
                "planned",
                json.dumps(plan, ensure_ascii=False, indent=2),
                plan_artifact["id"],
                None,
                now,
                now,
            ),
        )
        insert_tool_event(
            connection,
            session_id,
            "agent.create_plan",
            "done",
            "已生成 Research Plan，并等待用户确认执行。",
            now,
        )
        for step in plan["steps"]:
            if step["tool"] != "create_plan":
                insert_tool_event(
                    connection,
                    session_id,
                    step["tool"],
                    "queued",
                    step["detail"],
                    now,
                    time_label="Next",
                )
        connection.execute(
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            ("agent-loop", now, payload.project_id),
        )

    return AgentPlanResponse(
        run_id=run_id,
        project_id=payload.project_id,
        session_id=session_id,
        task=payload.task,
        provider=draft.provider,
        status="planned",
        rationale=plan["rationale"],
        steps=plan["steps"],
        artifact=Artifact.model_validate(plan_artifact),
    )


@app.post("/agent/runs/{run_id}/execute", response_model=AgentExecuteResponse)
def execute_agent_run(run_id: str, payload: AgentExecuteRequest) -> AgentExecuteResponse:
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Agent run execution requires confirmation")

    now = utc_now()
    with get_connection() as connection:
        run = connection.execute(
            "SELECT * FROM agent_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail="Agent run not found")

        run_dict = dict(run)
        project = fetch_project_dict(connection, run_dict["project_id"])
        plan = json.loads(run_dict["plan_json"])

        if run_dict["status"] == "completed" and run_dict["result_artifact_id"]:
            artifact = fetch_artifact_dict(connection, run_dict["result_artifact_id"])
            papers = plan.get("papers", [])
            paper_count = infer_agent_paper_count(plan, papers)
            return AgentExecuteResponse(
                run_id=run_id,
                status="completed",
                artifact=Artifact.model_validate(artifact),
                papers=papers,
                paper_count=paper_count,
                summary_metrics=collect_agent_summary_metrics(plan, paper_count),
                steps=plan["steps"],
            )

        connection.execute(
            "UPDATE agent_runs SET status = ?, updated_at = ? WHERE id = ?",
            ("running", now, run_id),
        )

        context = ToolContext(run_id=run_id, project=project, task=run_dict["task"], plan=plan)
        registry = build_agent_tool_registry(connection)
        for step in plan["steps"]:
            tool_name = step.get("tool", "")
            if tool_name == "create_plan":
                step["status"] = "done"
                continue
            if not registry.has(tool_name):
                fail_agent_run_step(
                    connection,
                    run_dict,
                    run_id,
                    plan,
                    step,
                    tool_name,
                    f"Agent tool is not registered: {tool_name}",
                )
                raise HTTPException(status_code=400, detail=f"Agent tool is not registered: {tool_name}")

            mark_plan_step_by_id(plan, step["id"], "running")
            insert_tool_event(
                connection,
                run_dict["session_id"],
                tool_name,
                "running",
                f"正在执行 {tool_name}。",
                utc_now(),
            )
            try:
                result = registry.run(tool_name, context)
                context.outputs[result.tool] = result.data
                step_metrics = result.summary_metrics or infer_tool_summary_metrics(result.data)
                context.summary_metrics[result.tool] = step_metrics
                if result.data.get("papers"):
                    context.papers = result.data["papers"]
                    plan["papers"] = context.papers
                if result.data.get("artifact"):
                    context.artifacts.append(result.data["artifact"])
                if result.data.get("artifacts"):
                    context.artifacts.extend(result.data["artifacts"])
                if result.data.get("artifact_id"):
                    context.artifact_id = result.data["artifact_id"]
                mark_plan_step_by_id(plan, step["id"], "done", step_metrics)
                insert_tool_event(
                    connection,
                    run_dict["session_id"],
                    tool_name,
                    "done",
                    result.summary,
                    utc_now(),
                )
            except Exception as error:
                fail_agent_run_step(connection, run_dict, run_id, plan, step, tool_name, error)
                raise

        if context.artifact_id is None and context.artifacts:
            context.artifact_id = context.artifacts[-1].get("id")
        if context.artifact_id is None:
            raise HTTPException(status_code=500, detail="Agent run completed without a result artifact")

        result_artifact = fetch_artifact_dict(connection, context.artifact_id)
        completed_at = utc_now()
        connection.execute(
            """
            UPDATE agent_runs
            SET status = ?, plan_json = ?, result_artifact_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                "completed",
                json.dumps(plan, ensure_ascii=False, indent=2),
                context.artifact_id,
                completed_at,
                run_id,
            ),
        )
        connection.execute(
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            ("agent-loop", completed_at, run_dict["project_id"]),
        )

    return AgentExecuteResponse(
        run_id=run_id,
        status="completed",
        artifact=Artifact.model_validate(result_artifact),
        papers=context.papers,
        paper_count=len(context.papers),
        summary_metrics=collect_agent_summary_metrics(plan, len(context.papers)),
        steps=plan["steps"],
    )


@app.get("/projects/{project_id}/sessions", response_model=list[Session])
def list_project_sessions(project_id: str) -> list[Session]:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM sessions WHERE project_id = ? ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
    return [Session.model_validate(dict(row)) for row in rows]


@app.get("/sessions/{session_id}/timeline", response_model=list[ToolEvent])
def get_session_timeline(session_id: str) -> list[ToolEvent]:
    with get_connection() as connection:
        session = connection.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        rows = connection.execute(
            "SELECT * FROM tool_events WHERE session_id = ? ORDER BY created_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
    return [ToolEvent.model_validate(dict(row)) for row in rows]


@app.get("/projects/{project_id}/timeline", response_model=list[ToolEvent])
def get_project_timeline(project_id: str) -> list[ToolEvent]:
    project = get_project(project_id)
    if not project.active_session_id:
        return []
    return get_session_timeline(project.active_session_id)

def build_agent_tool_registry(connection) -> ToolRegistry:
    registry = ToolRegistry()

    def create_plan_tool(context: ToolContext) -> ToolResult:
        return ToolResult(
            tool="create_plan",
            status="done",
            summary="Research Plan 已存在，继续等待或执行后续工具。",
        )

    def literature_search_tool(context: ToolContext) -> ToolResult:
        direction = infer_agent_direction(context)
        result = search_literature(direction, max_results=12, sources=["arxiv", "openalex"])
        now = utc_now()
        connection.execute(
            "DELETE FROM papers WHERE project_id = ?",
            (context.project["id"],),
        )
        paper_ids = insert_paper_candidates(connection, context.project["id"], result.papers, now)
        papers = fetch_project_papers_by_ids(connection, context.project["id"], paper_ids)
        artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_literature_search_{context.run_id}.md",
            kind="markdown",
            content_markdown=render_paper_table_markdown(result),
            content_json=render_paper_table_json(result),
            diff="+ Agent tool literature_search\n+ Retrieved and persisted real paper candidates",
            now=now,
        )
        return ToolResult(
            tool="literature_search",
            status="done",
            summary=f"已检索真实论文候选 {len(result.papers)} 篇；当前项目 paper table 共 {len(papers)} 篇。",
            summary_metrics={
                "paper_count": len(papers),
                "artifact_count": 1,
                "warning_count": len(result.errors),
            },
            data={
                "papers": papers,
                "artifact_id": artifact["id"],
                "artifact": artifact,
                "paper_count": len(papers),
                "errors": result.errors,
            },
        )

    def direction_review_tool(context: ToolContext) -> ToolResult:
        direction = infer_agent_direction(context)
        round_index = next_agent_direction_round(connection, context.project["id"])
        previous_titles = fetch_read_paper_titles(connection, context.project["id"]) if round_index > 1 else []
        scope, candidate_pool, candidates, errors = retrieve_direction_candidate_pool(direction, round_index, previous_titles)
        now = utc_now()
        paper_ids = insert_paper_candidates(connection, context.project["id"], candidates, now)
        paper_dicts = [fetch_paper_dict(connection, context.project["id"], paper_id) for paper_id in paper_ids]
        baseline_map = build_baseline_map(
            direction,
            [candidate.to_dict() for candidate in candidate_pool],
            paper_dicts,
        )
        readings = build_direction_readings(paper_dicts, direction, baseline_map)
        bundle = build_direction_review_bundle(
            direction,
            round_index,
            scope,
            baseline_map,
            readings,
            previous_read_count=len(previous_titles),
            errors=errors,
        )
        artifacts: list[dict] = []
        baseline_artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_baseline_map_round_{round_index}_{paper_slug(direction)}.md",
            kind="markdown",
            content_markdown=render_baseline_map_markdown(baseline_map),
            content_json=json.dumps(baseline_map.to_dict(), ensure_ascii=False, indent=2),
            diff="+ Agent tool direction_review\n+ Generated BaselineMap",
            now=now,
        )
        artifacts.append(baseline_artifact)
        review_artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_direction_review_round_{round_index}.md",
            kind="markdown",
            content_markdown=render_direction_review_markdown(bundle),
            content_json=render_direction_review_json(bundle),
            diff="+ Agent tool direction_review\n+ Generated direction review",
            now=now,
        )
        artifacts.append(review_artifact)

        for reading in readings:
            card_artifact = insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_direction_round_{round_index}_paper_card_{paper_slug(reading.card.paper_title)}.md",
                kind="markdown",
                content_markdown=render_card_markdown(reading.card, reading.paper),
                content_json=json.dumps(reading.to_dict(), ensure_ascii=False, indent=2),
                diff="+ Agent tool direction_review\n+ Generated direction-review paper card",
                now=now,
            )
            artifacts.append(card_artifact)
            connection.execute(
                """
                INSERT INTO paper_cards (
                    id, project_id, paper_id, artifact_id, sections_json, weakest_assumption,
                    minimal_reproduction, research_sight_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("paper_card"),
                    context.project["id"],
                    reading.paper.get("id"),
                    card_artifact["id"],
                    json.dumps([section.to_dict() for section in reading.card.sections], ensure_ascii=False, indent=2),
                    reading.card.weakest_assumption,
                    reading.card.minimal_reproduction,
                    json.dumps(reading.research_sight.to_dict(), ensure_ascii=False, indent=2),
                    now,
                ),
            )

        upsert_direction_reading_memories(
            connection,
            context.project["id"],
            direction,
            round_index,
            readings,
            now,
        )
        direction_memory = upsert_direction_memory_snapshot(
            connection,
            context.project["id"],
            direction,
            now,
            baseline_map=baseline_map.to_dict(),
        )
        memory_artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_direction_memory_{paper_slug(direction)}.md",
            kind="markdown",
            content_markdown="\n\n".join(
                [
                    f"# Direction Memory: {direction_memory.direction}",
                    direction_memory.summary,
                    f"Total papers: {direction_memory.total_papers}",
                    f"Rounds: {direction_memory.round_count}",
                ],
            ),
            content_json=json.dumps(direction_memory.to_dict(), ensure_ascii=False, indent=2),
            diff="+ Agent tool direction_review\n+ Updated paper memory bank",
            now=now,
        )
        artifacts.append(memory_artifact)
        return ToolResult(
            tool="direction_review",
            status="done",
            summary=f"已完成第 {round_index} 轮方向精读，生成 {len(readings)} 张 Paper Card。",
            summary_metrics={
                "review_status": bundle.review_status,
                "round_read_count": len(readings),
                "total_read_count": bundle.total_read_count,
                "artifact_count": len(artifacts),
                "warning_count": len(bundle.errors),
            },
            data={
                "papers": paper_dicts,
                "artifacts": artifacts,
                "artifact_id": review_artifact["id"],
                "round": round_index,
                "paper_count": len(readings),
                "review_status": bundle.review_status,
                "total_read_count": bundle.total_read_count,
                "recommended_paper_ids": bundle.recommended_paper_ids,
                "errors": bundle.errors,
            },
        )

    def research_memory_query_tool(context: ToolContext) -> ToolResult:
        now = utc_now()
        direction = infer_agent_direction(context)
        answer = query_research_memory(
            connection,
            project_id=context.project["id"],
            question=context.task,
            top_k=5,
            now=now,
            direction=direction,
        )
        answer_json = json.dumps(answer.to_dict(), ensure_ascii=False, indent=2)
        artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_research_memory_answer_{context.run_id}.md",
            kind="markdown",
            content_markdown=render_research_memory_answer_markdown(answer),
            content_json=answer_json,
            diff="+ Agent tool research_memory_query\n+ Retrieved paper memories",
            now=now,
        )
        return ToolResult(
            tool="research_memory_query",
            status="done",
            summary=f"已从 Paper Memory Bank 检索 {len(answer.hits)} 篇相关论文记忆。",
            summary_metrics={
                "memory_hit_count": len(answer.hits),
                "artifact_count": 1,
                "warning_count": len(answer.warnings),
            },
            data={
                "artifact_id": artifact["id"],
                "artifact": artifact,
                "hit_count": len(answer.hits),
                "memory_hit_count": len(answer.hits),
                "total_memories": answer.total_memories,
                "warnings": answer.warnings,
            },
        )

    def research_decision_tool(context: ToolContext) -> ToolResult:
        now = utc_now()
        papers = fetch_project_paper_dicts(connection, context.project["id"])
        paper_cards = fetch_project_paper_card_dicts(connection, context.project["id"])
        bundle = generate_research_decisions(context.project, papers, paper_cards, context.task)
        bundle_json = render_decision_json(bundle)
        artifacts = [
            insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_gap_board_{context.run_id}.md",
                kind="markdown",
                content_markdown=render_gap_board_markdown(bundle),
                content_json=bundle_json,
                diff="+ Agent tool research_decision\n+ Generated gap board",
                now=now,
            ),
            insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_idea_validation_{context.run_id}.md",
                kind="markdown",
                content_markdown=render_validation_markdown(bundle),
                content_json=bundle_json,
                diff="+ Agent tool research_decision\n+ Generated idea validation report",
                now=now,
            ),
            insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_experiment_plan_{context.run_id}.md",
                kind="markdown",
                content_markdown=render_experiment_markdown(bundle),
                content_json=bundle_json,
                diff="+ Agent tool research_decision\n+ Generated experiment plan",
                now=now,
            ),
        ]
        return ToolResult(
            tool="research_decision",
            status="done",
            summary=f"已生成 {len(bundle.gaps)} 个 gap、idea validation 和 experiment plan。",
            summary_metrics={
                "gap_count": len(bundle.gaps),
                "artifact_count": len(artifacts),
                "experiment_status": bundle.experiment.status,
            },
            data={
                "artifacts": artifacts,
                "artifact_id": artifacts[-1]["id"],
                "gap_count": len(bundle.gaps),
                "experiment_status": bundle.experiment.status,
                "anchor_paper_title": bundle.experiment.anchor_paper_title,
                "experiment_claim": bundle.experiment.claim,
            },
        )

    def search_mock_papers_tool(context: ToolContext) -> ToolResult:
        papers = build_mock_papers(context.task, context.project)
        return ToolResult(
            tool="search_mock_papers",
            status="done",
            summary=f"已生成 {len(papers)} 条 mock paper candidates。",
            summary_metrics={"paper_count": len(papers), "demo_mode": True},
            data={"papers": papers, "paper_count": len(papers), "demo_mode": True},
        )

    def save_artifact_tool(context: ToolContext) -> ToolResult:
        plan_snapshot = completed_plan_snapshot(context.plan)
        plan_snapshot.pop("papers", None)
        artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_run_{context.run_id}.md",
            kind="markdown",
            content_markdown=render_execution_markdown(
                context.task,
                context.project,
                plan_snapshot,
                context.papers,
                context.outputs,
                context.artifacts,
            ),
            content_json=json.dumps(
                {
                    "run_id": context.run_id,
                    "task": context.task,
                    "plan": plan_snapshot,
                    "paper_count": len(context.papers),
                    "tool_outputs": output_summary(context.outputs),
                    "artifact_refs": [artifact_ref(item) for item in context.artifacts],
                },
                ensure_ascii=False,
                indent=2,
            ),
            diff="+ Executed registered research tools\n+ Saved agent run artifact",
            now=utc_now(),
        )
        return ToolResult(
            tool="save_artifact",
            status="done",
            summary=f"已保存 agent run artifact: {artifact['title']}。",
            summary_metrics={"artifact_id": artifact["id"], "artifact_count": 1},
            data={"artifact_id": artifact["id"], "artifact": artifact},
        )

    def update_timeline_tool(context: ToolContext) -> ToolResult:
        return ToolResult(
            tool="update_timeline",
            status="done",
            summary="已完成本次最小 Agent Loop，并同步 session timeline。",
            summary_metrics={"artifact_id": context.artifact_id or ""},
            data={"artifact_id": context.artifact_id},
        )

    registry.register("create_plan", create_plan_tool, "Generate the confirmed research plan.")
    registry.register("literature_search", literature_search_tool, "Retrieve real paper candidates from literature sources.")
    registry.register("direction_review", direction_review_tool, "Run direction review, paper cards, baseline map, and memory writes.")
    registry.register("research_memory_query", research_memory_query_tool, "Retrieve relevant memories from Paper Memory Bank.")
    registry.register("research_decision", research_decision_tool, "Generate gap board, novelty validation, and experiment plan.")
    registry.register("search_mock_papers", search_mock_papers_tool, "Demo Mode: return local mock papers without external retrieval.")
    registry.register("save_artifact", save_artifact_tool, "Persist the agent output as Markdown and JSON.")
    registry.register("update_timeline", update_timeline_tool, "Finalize visible tool timeline state.")
    return registry
