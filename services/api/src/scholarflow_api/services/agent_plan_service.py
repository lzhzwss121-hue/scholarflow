from __future__ import annotations

import json

from fastapi import HTTPException

from scholarflow_api.agent_core import (
    BOUNDED_AGENT_LABEL,
    bounded_agent_budgets_from_env,
    get_model_provider,
    provider_supports_bounded_actions,
    render_plan_markdown,
    validate_workflow_plan,
)
from scholarflow_api.api_helpers import (
    ensure_active_session,
    fetch_project_dict,
    insert_artifact_row,
)
from scholarflow_api.database import get_connection, new_id, utc_now
from scholarflow_api.repositories.agent_run_repository import (
    insert_agent_run,
    insert_model_call_audit,
    update_project_stage,
)
from scholarflow_api.repositories.tool_event_repository import insert_tool_event
from scholarflow_api.schemas import AgentPlanRequest, AgentPlanResponse, Artifact


def is_demo_project_dict(project: dict) -> bool:
    return (
        project.get("id") == "local-bootstrap"
        or str(project.get("workflow", "")).lower() == "demo-preview"
        or str(project.get("stage", "")).lower() in {"seed", "demo"}
    )


def ensure_real_project_for_agent(project: dict) -> None:
    if is_demo_project_dict(project):
        raise HTTPException(
            status_code=400,
            detail=(
                "Demo project is read-only preview. "
                "Create a real project before running workflow tools."
            ),
        )


def create_agent_plan(payload: AgentPlanRequest) -> AgentPlanResponse:
    now = utc_now()
    run_id = new_id("run")
    with get_connection() as connection:
        project = fetch_project_dict(connection, payload.project_id)
        ensure_real_project_for_agent(project)
        session_id = ensure_active_session(connection, project, now)
        provider = get_model_provider()
        draft = provider.create_plan(payload.task, project)
        plan = draft.to_dict()
        validate_workflow_plan(plan)
        budgets = bounded_agent_budgets_from_env()
        execution_mode = (
            "bounded_observe_reason_act"
            if provider_supports_bounded_actions(provider)
            and draft.model_call is not None
            and draft.model_call.response_status == "success"
            else "deterministic_tool_graph"
        )
        initial_model_calls = (
            1
            if draft.model_call is not None
            and draft.model_call.external_data_sent
            else 0
        )
        initial_cost = (
            float(draft.model_call.estimated_cost_usd or 0.0)
            if draft.model_call is not None
            else 0.0
        )
        plan["agent_label"] = BOUNDED_AGENT_LABEL
        plan["execution_mode"] = execution_mode
        plan["bounded_agent"] = {
            "version": "bounded-research-agent.v1",
            "budgets": budgets.to_dict(),
            "steps_executed": 0,
            "replans": 0,
            "model_calls": initial_model_calls,
            "estimated_cost_usd": initial_cost,
            "runtime_seconds_used": 0.0,
            "consecutive_failures": 0,
            "trace": [],
            "last_observation": {
                "type": "plan_confirmed",
                "summary": "User confirmation is required before any tool executes.",
            },
            "fallback_reason": (
                ""
                if execution_mode == "bounded_observe_reason_act"
                else (
                    draft.model_call.fallback_reason
                    if draft.model_call is not None
                    else "provider_has_no_tool_call"
                )
            ),
        }
        plan["user_confirmed"] = False
        plan["queued_at"] = now
        plan["started_at"] = ""
        plan["completed_at"] = None
        plan["current_tool"] = ""
        plan["last_heartbeat"] = now
        plan_artifact = insert_artifact_row(
            connection=connection,
            project_id=payload.project_id,
            title=f"research_workflow_plan_{run_id}.md",
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
            diff="+ Created Bounded Research Agent plan artifact",
            now=now,
        )
        insert_agent_run(
            connection,
            run_id=run_id,
            project_id=payload.project_id,
            session_id=session_id,
            task=payload.task,
            provider=draft.provider,
            plan=plan,
            plan_artifact_id=str(plan_artifact["id"]),
            now=now,
        )
        if draft.model_call is None:
            raise RuntimeError(
                "ModelProvider returned a plan without a model-call audit."
            )
        model_call = draft.model_call.to_dict()
        insert_model_call_audit(
            connection,
            project_id=payload.project_id,
            run_id=run_id,
            audit=model_call,
        )
        insert_tool_event(
            connection,
            session_id,
            "agent.create_plan",
            "done",
            "已生成 Bounded Research Agent 计划，并等待用户确认执行。",
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
        update_project_stage(
            connection,
            project_id=payload.project_id,
            stage="workflow-run",
            updated_at=now,
        )

    return AgentPlanResponse(
        run_id=run_id,
        project_id=payload.project_id,
        session_id=session_id,
        task=payload.task,
        provider=draft.provider,
        execution_mode=execution_mode,
        model_call=model_call,
        status="planned",
        rationale=plan["rationale"],
        steps=plan["steps"],
        artifact=Artifact.model_validate(plan_artifact),
    )
