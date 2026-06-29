from __future__ import annotations

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
from scholarflow_api.database import get_connection, init_db, new_id, row_to_dict, seed_papers, utc_now
from scholarflow_api.schemas import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentPlanRequest,
    AgentPlanResponse,
    Artifact,
    ArtifactCreate,
    HealthResponse,
    Paper,
    Project,
    ProjectCreate,
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
            "SELECT * FROM papers WHERE project_id = ? ORDER BY priority, year DESC",
            (project_id,),
        ).fetchall()
    return [Paper.model_validate(dict(row)) for row in rows]


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
