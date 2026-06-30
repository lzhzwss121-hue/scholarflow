from __future__ import annotations

import hashlib
import json

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
from scholarflow_api.baseline_map import build_baseline_map, render_baseline_map_markdown
from scholarflow_api.database import get_connection, init_db, new_id, row_to_dict, seed_papers, utc_now
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
    BaselineMap,
    DirectionPaperReading,
    DirectionReviewRequest,
    DirectionReviewResponse,
    DirectionScope,
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


app = FastAPI(
    title="ScholarFlow API",
    version=__version__,
    description="Backend API and persistence layer for the ScholarFlow research workflow agent.",
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


@app.on_event("startup")
def startup() -> None:
    init_db()


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
        seed_papers(connection, project_id, now)
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
        if result.papers:
            connection.execute(
                "DELETE FROM papers WHERE project_id = ?",
                (project_id,),
            )
        insert_paper_candidates(connection, project_id, result.papers, completed_at)
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
            f"第 {payload.round} 轮检索并筛选 {len(readings)} 篇近三年高相关论文。",
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "direction.read",
            "done" if readings else "queued",
            f"已生成 {len(readings)} 张 12 条规则论文精读卡片。",
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
            f"已生成方向总结，并推荐 {len(bundle.recommended_paper_ids)} 篇用户亲自精读论文。",
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
        total_read_count=bundle.total_read_count,
        scope=DirectionScope(**bundle.scope.to_dict()),
        baseline_map=BaselineMap(**bundle.baseline_map.to_dict()),
        papers=[
            DirectionPaperReading(
                paper=Paper.model_validate(reading.paper),
                abstract_translation=reading.abstract_translation,
                sections=[section.to_dict() for section in reading.card.sections],
                research_sight=ResearchSight(**reading.research_sight.to_dict()),
                weakest_assumption=reading.card.weakest_assumption,
                minimal_reproduction=reading.card.minimal_reproduction,
                counterexample=reading.card.counterexample,
                follow_up_idea=reading.card.follow_up_idea,
                why_selected=reading.why_selected,
                venue_signal=reading.venue_signal,
                self_read_priority=reading.self_read_priority,
            )
            for reading in bundle.readings
        ],
        recommended_paper_ids=bundle.recommended_paper_ids,
        direction_summary=bundle.direction_summary,
        artifacts=[Artifact.model_validate(artifact) for artifact in artifacts],
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
            return AgentExecuteResponse(
                run_id=run_id,
                status="completed",
                artifact=Artifact.model_validate(artifact),
                papers=plan.get("papers", []),
                steps=plan["steps"],
            )

        connection.execute(
            "UPDATE agent_runs SET status = ?, updated_at = ? WHERE id = ?",
            ("running", now, run_id),
        )

        context = ToolContext(run_id=run_id, project=project, task=run_dict["task"], plan=plan)
        registry = build_agent_tool_registry(connection)
        for tool_name in ["search_mock_papers", "save_artifact", "update_timeline"]:
            mark_plan_step(plan, tool_name, "running")
            insert_tool_event(
                connection,
                run_dict["session_id"],
                tool_name,
                "running",
                f"正在执行 {tool_name}。",
                utc_now(),
            )
            result = registry.run(tool_name, context)
            if result.data.get("papers"):
                context.papers = result.data["papers"]
                plan["papers"] = context.papers
            if result.data.get("artifact_id"):
                context.artifact_id = result.data["artifact_id"]
            mark_plan_step(plan, tool_name, "done")
            insert_tool_event(
                connection,
                run_dict["session_id"],
                tool_name,
                "done",
                result.summary,
                utc_now(),
            )

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


def ensure_project_exists(project_id: str) -> None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")


def fetch_project_dict(connection, project_id: str) -> dict:
    row = connection.execute(
        "SELECT * FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    project = row_to_dict(row)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def fetch_artifact_dict(connection, artifact_id: str | None) -> dict:
    if not artifact_id:
        raise HTTPException(status_code=500, detail="Agent did not create an artifact")
    row = connection.execute(
        "SELECT * FROM artifacts WHERE id = ?",
        (artifact_id,),
    ).fetchone()
    artifact = row_to_dict(row)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


def fetch_paper_dict(connection, project_id: str, paper_id: str) -> dict:
    row = connection.execute(
        "SELECT * FROM papers WHERE id = ? AND project_id = ?",
        (paper_id, project_id),
    ).fetchone()
    paper = row_to_dict(row)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def fetch_project_paper_dicts(connection, project_id: str) -> list[dict]:
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
    return [dict(row) for row in rows]


def fetch_project_paper_card_dicts(connection, project_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT * FROM paper_cards
        WHERE project_id = ?
        ORDER BY created_at DESC, rowid DESC
        """,
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_read_paper_titles(connection, project_id: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT DISTINCT p.title
        FROM paper_cards pc
        JOIN papers p ON p.id = pc.paper_id
        JOIN artifacts a ON a.id = pc.artifact_id
        WHERE pc.project_id = ? AND pc.paper_id IS NOT NULL
          AND a.title LIKE 'direction_round_%_paper_card_%'
        ORDER BY pc.created_at ASC, pc.rowid ASC
        """,
        (project_id,),
    ).fetchall()
    return [row["title"] for row in rows if row["title"]]


def to_paper_memory_hit(hit) -> PaperMemoryHit:
    memory = hit.memory
    paper = Paper(
        id=memory.get("paper_id") or memory.get("id"),
        project_id=memory.get("project_id", ""),
        title=memory.get("title", ""),
        authors=memory.get("authors", ""),
        abstract="",
        year=memory.get("year", ""),
        type="memory",
        venue=memory.get("venue", ""),
        source=memory.get("source", ""),
        url=memory.get("url", ""),
        relation=memory.get("why_selected", ""),
        priority="High" if int(memory.get("self_read_priority") or 0) == 1 else "Medium",
        code="unknown",
        relevance_score=float(hit.score),
        created_at=memory.get("created_at", ""),
    )
    return PaperMemoryHit(
        paper=paper,
        direction=memory.get("direction", ""),
        round=int(memory.get("round_index") or 0),
        score=float(hit.score),
        snippets=hit.snippets,
        abstract_translation=memory.get("abstract_translation", ""),
        weakest_assumption=memory.get("weakest_assumption", ""),
        minimal_reproduction=memory.get("minimal_reproduction", ""),
        counterexample=memory.get("counterexample", ""),
        follow_up_idea=memory.get("follow_up_idea", ""),
        why_selected=memory.get("why_selected", ""),
        research_sight=build_research_sight_response(memory.get("research_sight_json", "{}")),
        self_read_priority=bool(int(memory.get("self_read_priority") or 0)),
    )


def to_direction_memory_response(memory) -> DirectionMemory:
    baseline_map = memory.baseline_map if isinstance(memory.baseline_map, dict) else {}
    return DirectionMemory(
        direction=memory.direction,
        total_papers=memory.total_papers,
        round_count=memory.round_count,
        summary=memory.summary,
        paper_ids=memory.paper_ids,
        baseline_map=BaselineMap(**baseline_map) if baseline_map.get("direction") else None,
        updated_at=memory.updated_at,
    )


def build_research_sight_response(value: str) -> ResearchSight:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    defaults = {
        "motivation_sharpness": "",
        "solution_elegance": "",
        "evaluation_integrity": "",
        "paradigm_inspiration": "",
        "why_good": "",
        "why_not_good": "",
        "better_angle": "",
        "baseline_comparison": "",
        "next_step_proposal": "",
    }
    defaults.update({key: str(parsed.get(key, "")) for key in defaults})
    return ResearchSight(**defaults)


def build_paper_card_source(connection, project_id: str, payload: PaperCardCreateRequest) -> dict:
    if payload.paper_id:
        paper = fetch_paper_dict(connection, project_id, payload.paper_id)
        if payload.title:
            paper["title"] = payload.title
        if payload.abstract:
            paper["abstract"] = payload.abstract
        return paper

    title = payload.title.strip() or "User Provided Paper"
    if not payload.abstract and not payload.paper_text:
        raise HTTPException(status_code=400, detail="paper_id, abstract, or paper_text is required")
    return {
        "id": None,
        "project_id": project_id,
        "title": title,
        "authors": "user provided",
        "abstract": payload.abstract,
        "year": "",
        "type": "user_input",
        "venue": "pasted content",
        "source": "user",
        "url": "",
        "relation": "用户提供内容生成的 Deep Paper Card。",
        "priority": "High",
        "code": "unknown",
        "relevance_score": 1.0,
        "created_at": "",
    }


def ensure_active_session(connection, project: dict, now: str) -> str:
    if project.get("active_session_id"):
        return project["active_session_id"]

    session_id = new_id("session")
    connection.execute(
        """
        INSERT INTO sessions (id, project_id, title, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, project["id"], "Agent Loop Session", "active", now, now),
    )
    connection.execute(
        "UPDATE projects SET active_session_id = ?, updated_at = ? WHERE id = ?",
        (session_id, now, project["id"]),
    )
    project["active_session_id"] = session_id
    return session_id


def insert_artifact_row(
    connection,
    project_id: str,
    title: str,
    kind: str,
    content_markdown: str,
    content_json: str,
    diff: str,
    now: str,
) -> dict:
    artifact_id = new_id("artifact")
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
            project_id,
            title,
            kind,
            content_markdown,
            content_json,
            diff,
            now,
            now,
        ),
    )
    connection.execute(
        "UPDATE projects SET updated_at = ? WHERE id = ?",
        (now, project_id),
    )
    artifact = connection.execute(
        "SELECT * FROM artifacts WHERE id = ?",
        (artifact_id,),
    ).fetchone()
    return dict(artifact)


def insert_tool_event(
    connection,
    session_id: str,
    tool: str,
    status: str,
    summary: str,
    created_at: str,
    time_label: str = "Now",
) -> None:
    connection.execute(
        """
        INSERT INTO tool_events (id, session_id, time_label, tool, status, summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (new_id("event"), session_id, time_label, tool, status, summary, created_at),
    )


def insert_paper_candidates(connection, project_id: str, papers: list, now: str) -> list[str]:
    paper_ids: list[str] = []
    for paper in papers:
        paper_id = build_paper_id(project_id, paper.source, paper.title)
        paper_ids.append(paper_id)
        connection.execute(
            """
            INSERT INTO papers (
                id, project_id, title, authors, abstract, year, type, venue, source, url,
                relation, priority, code, relevance_score, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                abstract = excluded.abstract,
                year = excluded.year,
                type = excluded.type,
                venue = excluded.venue,
                source = excluded.source,
                url = excluded.url,
                relation = excluded.relation,
                priority = excluded.priority,
                code = excluded.code,
                relevance_score = excluded.relevance_score
            """,
            (
                paper_id,
                project_id,
                paper.title,
                paper.authors,
                paper.abstract,
                paper.year,
                paper.type,
                paper.venue,
                paper.source,
                paper.url,
                paper.relation,
                paper.priority,
                paper.code,
                paper.relevance_score,
                now,
            ),
        )
    return paper_ids


def build_paper_id(project_id: str, source: str, title: str) -> str:
    digest = hashlib.sha1(f"{project_id}:{source}:{title.lower()}".encode("utf-8")).hexdigest()[:16]
    return f"paper_{digest}"


def build_agent_tool_registry(connection) -> ToolRegistry:
    registry = ToolRegistry()

    def create_plan_tool(context: ToolContext) -> ToolResult:
        return ToolResult(
            tool="create_plan",
            status="done",
            summary="Research Plan 已存在，继续等待或执行后续工具。",
        )

    def search_mock_papers_tool(context: ToolContext) -> ToolResult:
        papers = build_mock_papers(context.task, context.project)
        return ToolResult(
            tool="search_mock_papers",
            status="done",
            summary=f"已生成 {len(papers)} 条 mock paper candidates。",
            data={"papers": papers},
        )

    def save_artifact_tool(context: ToolContext) -> ToolResult:
        plan_snapshot = completed_plan_snapshot(context.plan)
        plan_snapshot["papers"] = context.papers
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
            ),
            content_json=json.dumps(
                {
                    "run_id": context.run_id,
                    "task": context.task,
                    "plan": plan_snapshot,
                    "papers": context.papers,
                },
                ensure_ascii=False,
                indent=2,
            ),
            diff="+ Executed mock research tools\n+ Saved agent run artifact",
            now=utc_now(),
        )
        return ToolResult(
            tool="save_artifact",
            status="done",
            summary=f"已保存 agent run artifact: {artifact['title']}。",
            data={"artifact_id": artifact["id"]},
        )

    def update_timeline_tool(context: ToolContext) -> ToolResult:
        return ToolResult(
            tool="update_timeline",
            status="done",
            summary="已完成本次最小 Agent Loop，并同步 session timeline。",
            data={"artifact_id": context.artifact_id},
        )

    registry.register("create_plan", create_plan_tool, "Generate the confirmed research plan.")
    registry.register("search_mock_papers", search_mock_papers_tool, "Return local mock papers for Phase 5.")
    registry.register("save_artifact", save_artifact_tool, "Persist the agent output as Markdown and JSON.")
    registry.register("update_timeline", update_timeline_tool, "Finalize visible tool timeline state.")
    return registry


def mark_plan_step(plan: dict, tool_name: str, status: str) -> None:
    for step in plan["steps"]:
        if step["tool"] == tool_name:
            step["status"] = status


def completed_plan_snapshot(plan: dict) -> dict:
    snapshot = json.loads(json.dumps(plan, ensure_ascii=False))
    for step in snapshot["steps"]:
        step["status"] = "done"
    return snapshot
