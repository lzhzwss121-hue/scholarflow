from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from scholarflow_api.agent_core import ToolContext, validate_workflow_plan
from scholarflow_api.api_helpers import (
    artifact_ref,
    build_warning_summary_metrics,
    collect_agent_summary_metrics,
    fetch_artifact_dict,
    fetch_project_dict,
    infer_agent_paper_count,
    infer_tool_summary_metrics,
    mark_plan_step_by_id,
    output_summary,
)
from scholarflow_api.database import get_connection, utc_now
from scholarflow_api.jobs.models import DurableJob
from scholarflow_api.jobs.repository import cancel_job, enqueue_job
from scholarflow_api.literature import LOW_RECALL_THRESHOLD
from scholarflow_api.repositories.agent_run_repository import (
    agent_cancellation_requested,
    fetch_agent_run,
    mark_agent_run_running,
    request_agent_cancellation,
    update_agent_plan,
    update_agent_run_progress,
    update_project_stage,
)
from scholarflow_api.repositories.tool_event_repository import insert_tool_event
from scholarflow_api.schemas import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentRunStatusResponse,
    Artifact,
    ArtifactRef,
    WorkflowStepState,
)
from scholarflow_api.services.agent_plan_service import (
    ensure_real_project_for_agent,
)
from scholarflow_api.services.agent_tool_service import (
    build_agent_tool_registry,
)


TERMINAL_AGENT_RUN_STATUSES = {
    "completed",
    "completed_with_warnings",
    "partial",
    "failed",
    "cancelled",
}


def make_artifact_refs(artifacts: list[dict]) -> list[ArtifactRef]:
    return [
        ArtifactRef.model_validate(artifact_ref(artifact))
        for artifact in artifacts
    ]


def workflow_step_state(
    step_id: str,
    status: str,
    label: str,
    summary: str,
    updated_at: str,
    *,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    artifacts: list[dict] | None = None,
) -> WorkflowStepState:
    return WorkflowStepState(
        step_id=step_id,
        status=status,  # type: ignore[arg-type]
        label=label,
        summary=summary,
        warnings=warnings or [],
        errors=errors or [],
        artifact_refs=make_artifact_refs(artifacts or []),
        updated_at=updated_at,
    )


def literature_step_status(
    paper_count: int,
    errors: list[str],
    relevance_coverage: dict[str, int] | None = None,
) -> str:
    coverage = relevance_coverage or {}
    if paper_count <= 0:
        return "error" if errors else "blocked"
    if (
        coverage.get("off_topic_count", 0) > 0
        or coverage.get("weak_match_count", 0) > 0
    ):
        return "partial"
    if coverage.get("returned_count", paper_count) < LOW_RECALL_THRESHOLD:
        return "partial"
    if any(error.startswith("low_recall:") for error in errors):
        return "partial"
    if errors:
        return "partial"
    return "complete"


def direction_step_status(
    review_status: str,
    round_read_count: int,
) -> str:
    if review_status == "blocked":
        return "blocked"
    if review_status == "partial" or round_read_count < 5:
        return "partial"
    return "complete"


def memory_step_status(hit_count: int, warnings: list[str]) -> str:
    if hit_count <= 0:
        return "partial" if warnings else "blocked"
    return "partial" if warnings else "complete"


def experiment_step_status(status: str) -> str:
    if status == "blocked":
        return "blocked"
    if status == "partial":
        return "partial"
    return "complete"


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def agent_run_summary(
    plan: dict,
    outputs: dict[str, object] | None,
    paper_count: int,
    artifacts: list[dict] | None = None,
) -> dict[str, object]:
    outputs = outputs or {}
    artifacts = artifacts or []
    warnings: list[str] = []

    literature_output = outputs.get("literature_search")
    if isinstance(literature_output, dict):
        for error in literature_output.get("errors", []) or []:
            warnings.append(f"degraded retrieval: {error}")
        coverage = (
            literature_output.get("relevance_coverage")
            if isinstance(
                literature_output.get("relevance_coverage"),
                dict,
            )
            else {}
        )
        if coverage:
            off_topic_count = int(
                coverage.get("off_topic_count") or 0
            )
            weak_count = int(
                coverage.get("weak_match_count") or 0
            )
            returned_count = int(
                coverage.get("returned_count") or paper_count
            )
            if off_topic_count or weak_count:
                warnings.append(
                    "Paper Table partial: filtered "
                    f"weak={weak_count}, off-topic={off_topic_count}."
                )
            if returned_count < LOW_RECALL_THRESHOLD:
                warnings.append(
                    f"Paper Table partial: only {returned_count} "
                    "returned papers."
                )

    direction_output = outputs.get("direction_review")
    if isinstance(direction_output, dict):
        review_status = str(
            direction_output.get("review_status") or ""
        )
        if review_status and review_status != "complete":
            warnings.append(
                "Direction Review "
                f"{review_status}: relevant_read_count="
                f"{direction_output.get('relevant_read_count', 0)}."
            )
        for error in direction_output.get("errors", []) or []:
            warnings.append(f"Direction Review warning: {error}")

    memory_output = outputs.get("research_memory_query")
    if isinstance(memory_output, dict):
        for warning in memory_output.get("warnings", []) or []:
            warnings.append(f"Paper Memory warning: {warning}")

    decision_output = outputs.get("research_decision")
    if isinstance(decision_output, dict):
        decision_status = str(
            decision_output.get("decision_status") or ""
        )
        if decision_status and decision_status != "complete":
            warnings.append(
                f"Gap Board {decision_status}: "
                "evidence quality is insufficient."
            )
        if decision_output.get("experiment_status") == "blocked":
            warnings.append(
                "Experiment Plan blocked: missing reproducible anchor."
            )
        elif decision_output.get("experiment_status") == "partial":
            warnings.append(
                "Experiment Plan partial: research anchors exist "
                "but execution conditions remain unknown."
            )
        for warning in decision_output.get("warnings", []) or []:
            warnings.append(f"Research Decision warning: {warning}")

    for step in plan.get("steps", []) or []:
        metrics = step.get("metrics") if isinstance(step, dict) else {}
        if isinstance(metrics, dict) and metrics.get("warning_count"):
            tool = (
                step.get("tool", "tool")
                if isinstance(step, dict)
                else "tool"
            )
            warnings.append(
                f"{tool} reported {metrics.get('warning_count')} warnings."
            )

    warnings = unique_strings(warnings)
    run_status = "completed_with_warnings" if warnings else "completed"
    if any("blocked" in warning.lower() for warning in warnings):
        run_status = "partial"

    summary = (
        "completed"
        if run_status == "completed"
        else (
            f"{run_status}: {len(warnings)} warning(s); "
            f"latest artifact count={len(artifacts)}."
        )
    )
    return {
        "status": run_status,
        "summary": summary,
        "warnings": warnings,
        "artifact_refs": make_artifact_refs(artifacts),
    }


def agent_workflow_steps(
    outputs: dict[str, object] | None,
    artifacts: list[dict] | None,
    updated_at: str,
) -> list[WorkflowStepState]:
    outputs = outputs or {}
    artifacts = artifacts or []
    steps: list[WorkflowStepState] = []

    literature_output = outputs.get("literature_search")
    if isinstance(literature_output, dict):
        papers = (
            literature_output.get("papers")
            if isinstance(literature_output.get("papers"), list)
            else []
        )
        errors = [
            str(error)
            for error in literature_output.get("errors", []) or []
        ]
        coverage = (
            literature_output.get("relevance_coverage")
            if isinstance(
                literature_output.get("relevance_coverage"),
                dict,
            )
            else {}
        )
        artifact = (
            literature_output.get("artifact")
            if isinstance(literature_output.get("artifact"), dict)
            else None
        )
        steps.append(
            workflow_step_state(
                step_id="paper-table",
                status=literature_step_status(
                    len(papers),
                    errors,
                    coverage,
                ),
                label="Paper Table",
                summary=(
                    f"{coverage.get('candidate_count', len(papers))} "
                    "candidates / "
                    f"{coverage.get('eligible_count', coverage.get('returned_count', len(papers)))} "
                    "eligible / "
                    f"{coverage.get('returned_count', len(papers))} "
                    "returned / "
                    f"{coverage.get('truncated_count', 0)} truncated / "
                    f"{coverage.get('off_topic_count', 0)} "
                    "off-topic filtered"
                ),
                warnings=[
                    f"degraded retrieval: {error}"
                    for error in errors
                ],
                updated_at=updated_at,
                artifacts=[artifact] if artifact else [],
            )
        )

    direction_output = outputs.get("direction_review")
    if isinstance(direction_output, dict):
        review_status = str(
            direction_output.get("review_status") or "partial"
        )
        round_read_count = int(
            direction_output.get("paper_count")
            or direction_output.get("round_read_count")
            or 0
        )
        direction_artifacts = [
            item
            for item in direction_output.get("artifacts", []) or []
            if isinstance(item, dict)
        ]
        steps.append(
            workflow_step_state(
                step_id="direction-review",
                status=direction_step_status(
                    review_status,
                    round_read_count,
                ),
                label="Direction Review",
                summary=(
                    f"{review_status}: "
                    f"{direction_output.get('relevant_read_count', round_read_count)} "
                    "strong/medium readings; "
                    f"off-topic={direction_output.get('off_topic_count', 0)}"
                ),
                warnings=[
                    str(error)
                    for error in direction_output.get("errors", []) or []
                ],
                updated_at=updated_at,
                artifacts=direction_artifacts[:3],
            )
        )

    memory_output = outputs.get("research_memory_query")
    if isinstance(memory_output, dict):
        warnings = [
            str(warning)
            for warning in memory_output.get("warnings", []) or []
        ]
        artifact = (
            memory_output.get("artifact")
            if isinstance(memory_output.get("artifact"), dict)
            else None
        )
        hit_count = int(
            memory_output.get("hit_count")
            or memory_output.get("memory_hit_count")
            or 0
        )
        steps.append(
            workflow_step_state(
                step_id="paper-memory",
                status=memory_step_status(hit_count, warnings),
                label="Paper Memory",
                summary=f"命中 {hit_count} 篇论文记忆。",
                warnings=warnings,
                updated_at=updated_at,
                artifacts=[artifact] if artifact else [],
            )
        )

    decision_output = outputs.get("research_decision")
    if isinstance(decision_output, dict):
        decision_status = str(
            decision_output.get("decision_status") or "partial"
        )
        warnings = [
            str(warning)
            for warning in decision_output.get("warnings", []) or []
        ]
        decision_artifacts = [
            item
            for item in decision_output.get("artifacts", []) or []
            if isinstance(item, dict)
        ]
        evidence_quality = (
            decision_output.get("evidence_quality")
            if isinstance(
                decision_output.get("evidence_quality"),
                dict,
            )
            else {}
        )
        steps.append(
            workflow_step_state(
                step_id="gap-board",
                status=(
                    decision_status
                    if decision_status
                    in {"complete", "partial", "blocked"}
                    else "partial"
                ),
                label="Gap Board",
                summary=(
                    f"{decision_status}: gap evidence="
                    f"{evidence_quality.get('gap_evidence_paper_count', 0)}"
                ),
                warnings=warnings,
                updated_at=updated_at,
                artifacts=decision_artifacts[:2],
            )
        )
        experiment_status = str(
            decision_output.get("experiment_status") or "blocked"
        )
        steps.append(
            workflow_step_state(
                step_id="experiment-planner",
                status=experiment_step_status(experiment_status),
                label="Experiment Plan",
                summary=(
                    "缺少可复现实验 anchor。"
                    if experiment_status == "blocked"
                    else (
                        "实验 anchor："
                        f"{decision_output.get('anchor_paper_title') or 'N/A'}。"
                    )
                ),
                warnings=(
                    warnings
                    if experiment_status in {"blocked", "partial"}
                    else []
                ),
                updated_at=updated_at,
                artifacts=decision_artifacts[2:],
            )
        )

    return steps


def serialize_artifact_refs(
    artifacts: list[dict],
) -> list[dict[str, str]]:
    return [
        artifact_ref(artifact)
        for artifact in artifacts
        if isinstance(artifact, dict)
    ]


def serialize_workflow_steps(
    steps: list[WorkflowStepState],
) -> list[dict]:
    return [step.model_dump() for step in steps]


def current_agent_tool(plan: dict) -> str:
    for step in plan.get("steps", []) or []:
        if isinstance(step, dict) and step.get("status") == "running":
            return str(
                step.get("tool") or step.get("title") or ""
            )
    for step in plan.get("steps", []) or []:
        if isinstance(step, dict) and step.get("status") == "queued":
            return str(
                step.get("tool") or step.get("title") or ""
            )
    return ""


def persist_agent_run_progress(
    connection: Any,
    run_id: str,
    plan: dict,
    status: str,
    *,
    outputs: dict[str, object] | None = None,
    papers: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    result_artifact_id: str | None = None,
    warnings: list[str] | None = None,
    run_status_summary: str | None = None,
) -> None:
    papers = papers or []
    artifacts = artifacts or []
    outputs = outputs or {}
    updated_at = utc_now()
    run_summary = agent_run_summary(
        plan,
        outputs,
        len(papers),
        artifacts,
    )
    workflow_steps = agent_workflow_steps(
        outputs,
        artifacts,
        updated_at,
    )
    raw_warnings = [
        *(warnings or []),
        *[str(item) for item in run_summary["warnings"]],
    ]
    merged_warnings = unique_strings(raw_warnings)
    active_tool = (
        ""
        if status in TERMINAL_AGENT_RUN_STATUSES
        else current_agent_tool(plan)
    )
    if run_status_summary is not None:
        summary_text = run_status_summary
    elif status == "running":
        summary_text = (
            f"running: {active_tool or 'deterministic workflow'}."
        )
    elif status == "failed":
        summary_text = (
            "failed: Research Workflow Run stopped with an error."
        )
    elif status == "cancelled":
        summary_text = (
            "cancelled: Research Workflow Run stopped by user request."
        )
    else:
        summary_text = str(run_summary["summary"])
    summary_metrics = collect_agent_summary_metrics(
        plan,
        len(papers),
    )
    summary_metrics.update(
        build_warning_summary_metrics(raw_warnings)
    )
    plan["summary_metrics"] = summary_metrics
    plan["warnings"] = merged_warnings
    plan["artifact_refs"] = serialize_artifact_refs(artifacts)
    plan["workflow_steps"] = serialize_workflow_steps(workflow_steps)
    plan["run_status_summary"] = summary_text
    plan["paper_count"] = len(papers)
    plan["current_tool"] = active_tool
    plan["queued_at"] = str(
        plan.get("queued_at")
        or plan.get("created_at")
        or updated_at
    )
    if status == "running" and not plan.get("started_at"):
        plan["started_at"] = updated_at
    if status in TERMINAL_AGENT_RUN_STATUSES:
        plan["completed_at"] = str(
            plan.get("completed_at") or updated_at
        )
    plan["last_heartbeat"] = updated_at
    plan["updated_at"] = updated_at
    if outputs:
        plan["tool_outputs"] = output_summary(outputs)
    if papers:
        plan["papers"] = papers

    update_agent_run_progress(
        connection,
        run_id=run_id,
        status=status,
        plan=plan,
        result_artifact_id=result_artifact_id,
        updated_at=updated_at,
    )
    connection.commit()


def fetch_agent_run_dict(connection: Any, run_id: str) -> dict:
    run = fetch_agent_run(connection, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Research Workflow Run not found",
        )
    return run


def parse_agent_plan(value: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def agent_status_response_from_run(
    connection: Any,
    run_dict: dict,
) -> AgentRunStatusResponse:
    plan = parse_agent_plan(run_dict.get("plan_json", "{}"))
    steps = (
        plan.get("steps")
        if isinstance(plan.get("steps"), list)
        else []
    )
    artifact = None
    result_artifact_id = run_dict.get("result_artifact_id")
    if result_artifact_id:
        artifact_dict = fetch_artifact_dict(
            connection,
            str(result_artifact_id),
        )
        artifact = Artifact.model_validate(artifact_dict)

    artifact_refs_payload = (
        plan.get("artifact_refs")
        if isinstance(plan.get("artifact_refs"), list)
        else []
    )
    workflow_steps_payload = (
        plan.get("workflow_steps")
        if isinstance(plan.get("workflow_steps"), list)
        else []
    )
    papers_payload = (
        plan.get("papers")
        if isinstance(plan.get("papers"), list)
        else []
    )
    return AgentRunStatusResponse(
        run_id=str(run_dict["id"]),
        model_call=(
            plan.get("model_call")
            if isinstance(plan.get("model_call"), dict)
            else None
        ),
        status=str(run_dict["status"]),  # type: ignore[arg-type]
        steps=[
            step
            for step in steps
            if isinstance(step, dict)
        ],
        summary_metrics=(
            plan.get("summary_metrics")
            if isinstance(plan.get("summary_metrics"), dict)
            else {}
        ),
        warnings=[
            str(warning)
            for warning in plan.get("warnings", []) or []
        ],
        artifact_refs=[
            ArtifactRef.model_validate(ref)
            for ref in artifact_refs_payload
            if isinstance(ref, dict)
        ],
        workflow_steps=[
            WorkflowStepState.model_validate(step)
            for step in workflow_steps_payload
            if isinstance(step, dict)
        ],
        run_status_summary=str(
            plan.get("run_status_summary") or ""
        ),
        current_tool=str(
            plan.get("current_tool") or current_agent_tool(plan)
        ),
        papers=[
            paper
            for paper in papers_payload
            if isinstance(paper, dict)
        ],
        paper_count=int(
            plan.get("paper_count")
            or infer_agent_paper_count(
                plan,
                (
                    plan.get("papers", [])
                    if isinstance(plan.get("papers"), list)
                    else []
                ),
            )
        ),
        artifact=artifact,
        queued_at=str(
            plan.get("queued_at")
            or run_dict.get("created_at")
            or ""
        ),
        started_at=str(plan.get("started_at") or ""),
        completed_at=(
            str(plan.get("completed_at") or "") or None
        ),
        last_heartbeat=str(
            plan.get("last_heartbeat")
            or run_dict.get("updated_at")
            or ""
        ),
        updated_at=str(run_dict.get("updated_at") or ""),
    )


def execute_response_from_status(
    status: AgentRunStatusResponse,
) -> AgentExecuteResponse:
    return AgentExecuteResponse(
        run_id=status.run_id,
        model_call=status.model_call,
        status=status.status,
        artifact=status.artifact,
        papers=status.papers,
        paper_count=status.paper_count,
        summary_metrics=status.summary_metrics,
        run_status_summary=status.run_status_summary,
        warnings=status.warnings,
        artifact_refs=status.artifact_refs,
        workflow_steps=status.workflow_steps,
        steps=status.steps,
        queued_at=status.queued_at,
        started_at=status.started_at,
        completed_at=status.completed_at,
        current_tool=status.current_tool,
        last_heartbeat=status.last_heartbeat,
        updated_at=status.updated_at,
    )


def mark_queued_agent_steps_cancelled(plan: dict) -> None:
    for step in plan.get("steps", []) or []:
        if (
            isinstance(step, dict)
            and step.get("status") in {"queued", "running"}
        ):
            step["status"] = "cancelled"


def fail_agent_run_step(
    connection: Any,
    run_dict: dict,
    run_id: str,
    plan: dict,
    step: dict,
    tool_name: str,
    error: object,
) -> None:
    error_message = (
        error.detail
        if isinstance(error, HTTPException)
        else str(error)
    )
    error_message = error_message or error.__class__.__name__
    failed_at = utc_now()
    mark_plan_step_by_id(
        plan,
        step.get("id", ""),
        "failed",
    )
    update_agent_run_progress(
        connection,
        run_id=run_id,
        status="failed",
        plan=plan,
        result_artifact_id=None,
        updated_at=failed_at,
    )
    insert_tool_event(
        connection,
        run_dict["session_id"],
        tool_name or "unknown_tool",
        "failed",
        error_message[:500],
        failed_at,
    )
    connection.commit()


def run_agent_loop_background(run_id: str) -> None:
    try:
        run_agent_loop(run_id)
    except Exception as error:  # noqa: BLE001
        try:
            with get_connection() as connection:
                run_dict = fetch_agent_run_dict(connection, run_id)
                plan = parse_agent_plan(run_dict["plan_json"])
                for step in plan.get("steps", []) or []:
                    if (
                        isinstance(step, dict)
                        and step.get("status") == "running"
                    ):
                        step["status"] = "failed"
                        break
                persist_agent_run_progress(
                    connection,
                    run_id,
                    plan,
                    "failed",
                    warnings=[
                        f"Research Workflow Run failed: {error}"
                    ],
                    run_status_summary=f"failed: {error}",
                )
                insert_tool_event(
                    connection,
                    run_dict["session_id"],
                    "agent.execute",
                    "failed",
                    str(error)[:500],
                    utc_now(),
                )
                connection.commit()
        except Exception:
            return


def run_agent_loop(run_id: str, execution: Any = None) -> dict:
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        project = fetch_project_dict(
            connection,
            run_dict["project_id"],
        )
        ensure_real_project_for_agent(project)
        plan = parse_agent_plan(run_dict["plan_json"])
        restored_papers = (
            [
                item
                for item in plan.get("papers", [])
                if isinstance(item, dict)
            ]
            if isinstance(plan.get("papers"), list)
            else []
        )
        restored_outputs = (
            dict(plan["tool_outputs"])
            if isinstance(plan.get("tool_outputs"), dict)
            else {}
        )
        restored_artifacts = []
        for ref in plan.get("artifact_refs", []) or []:
            if not isinstance(ref, dict) or not ref.get("id"):
                continue
            artifact = fetch_artifact_dict(
                connection,
                str(ref["id"]),
            )
            if artifact is not None:
                restored_artifacts.append(artifact)
        context = ToolContext(
            run_id=run_id,
            project=project,
            task=run_dict["task"],
            plan=plan,
            papers=restored_papers,
            artifacts=restored_artifacts,
            outputs=restored_outputs,
        )
        registry = build_agent_tool_registry(connection)
        registered_tools = {
            item["name"]
            for item in registry.describe()
            if isinstance(item, dict)
        }
        steps = validate_workflow_plan(
            plan,
            registered_tools=registered_tools,
        )
        executable_steps = [
            step
            for step in steps
            if str(step.get("tool") or "") != "create_plan"
        ]

        for step in steps:
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool", ""))
            if step.get("status") == "done":
                continue
            if tool_name == "create_plan":
                step["status"] = "done"
                persist_agent_run_progress(
                    connection,
                    run_id,
                    plan,
                    "running",
                )
                continue
            if execution is not None:
                execution.raise_if_cancelled()
            if agent_cancellation_requested(connection, run_id):
                cancelled_at = utc_now()
                mark_queued_agent_steps_cancelled(plan)
                persist_agent_run_progress(
                    connection,
                    run_id,
                    plan,
                    "cancelled",
                    outputs=context.outputs,
                    papers=context.papers,
                    artifacts=context.artifacts,
                    warnings=[
                        "Research Workflow Run cancelled "
                        "by user request."
                    ],
                    run_status_summary=(
                        "cancelled: stopped before "
                        "the next tool step."
                    ),
                )
                insert_tool_event(
                    connection,
                    run_dict["session_id"],
                    "agent.cancel",
                    "cancelled",
                    (
                        "用户已取消 Research Workflow Run，"
                        "后续 tool step 已停止。"
                    ),
                    cancelled_at,
                )
                connection.commit()
                return {
                    "run_id": run_id,
                    "status": "cancelled",
                }
            if not registry.has(tool_name):
                fail_agent_run_step(
                    connection,
                    run_dict,
                    run_id,
                    plan,
                    step,
                    tool_name,
                    (
                        "Workflow tool is not registered: "
                        f"{tool_name}"
                    ),
                )
                return {
                    "run_id": run_id,
                    "status": "failed",
                }

            mark_plan_step_by_id(
                plan,
                str(step["id"]),
                "running",
            )
            insert_tool_event(
                connection,
                run_dict["session_id"],
                tool_name,
                "running",
                f"正在执行 {tool_name}。",
                utc_now(),
            )
            persist_agent_run_progress(
                connection,
                run_id,
                plan,
                "running",
                outputs=context.outputs,
                papers=context.papers,
                artifacts=context.artifacts,
            )
            if execution is not None:
                completed_count = sum(
                    item.get("status") == "done"
                    for item in executable_steps
                )
                execution.checkpoint(
                    tool_name,
                    min(
                        90,
                        10
                        + int(
                            80
                            * completed_count
                            / max(1, len(executable_steps))
                        ),
                    ),
                    {
                        "step_id": str(step.get("id") or ""),
                        "plan": plan,
                    },
                )
            try:
                result = registry.run(tool_name, context)
                context.outputs[result.tool] = result.data
                step_metrics = (
                    result.summary_metrics
                    or infer_tool_summary_metrics(result.data)
                )
                context.summary_metrics[result.tool] = step_metrics
                if result.data.get("papers"):
                    context.papers = result.data["papers"]
                    plan["papers"] = context.papers
                if result.data.get("artifact"):
                    context.artifacts.append(
                        result.data["artifact"]
                    )
                if result.data.get("artifacts"):
                    context.artifacts.extend(
                        result.data["artifacts"]
                    )
                if result.data.get("artifact_id"):
                    context.artifact_id = result.data["artifact_id"]
                mark_plan_step_by_id(
                    plan,
                    str(step["id"]),
                    "done",
                    step_metrics,
                )
                insert_tool_event(
                    connection,
                    run_dict["session_id"],
                    tool_name,
                    "done",
                    result.summary,
                    utc_now(),
                )
                persist_agent_run_progress(
                    connection,
                    run_id,
                    plan,
                    "running",
                    outputs=context.outputs,
                    papers=context.papers,
                    artifacts=context.artifacts,
                )
                if execution is not None:
                    completed_count = sum(
                        item.get("status") == "done"
                        for item in executable_steps
                    )
                    execution.checkpoint(
                        tool_name,
                        min(
                            95,
                            10
                            + int(
                                80
                                * completed_count
                                / max(
                                    1,
                                    len(executable_steps),
                                )
                            ),
                        ),
                        {
                            "step_id": str(
                                step.get("id") or ""
                            ),
                            "plan": plan,
                        },
                    )
            except Exception as error:
                if execution is not None:
                    mark_plan_step_by_id(
                        plan,
                        str(step["id"]),
                        "queued",
                    )
                    persist_agent_run_progress(
                        connection,
                        run_id,
                        plan,
                        "running",
                        outputs=context.outputs,
                        papers=context.papers,
                        artifacts=context.artifacts,
                        warnings=[
                            f"{tool_name} attempt failed "
                            f"and will be retried: {error}"
                        ],
                        run_status_summary=(
                            f"retrying: {tool_name} failed "
                            "on this attempt."
                        ),
                    )
                    raise
                fail_agent_run_step(
                    connection,
                    run_dict,
                    run_id,
                    plan,
                    step,
                    tool_name,
                    error,
                )
                return {
                    "run_id": run_id,
                    "status": "failed",
                }

        if context.artifact_id is None and context.artifacts:
            context.artifact_id = context.artifacts[-1].get("id")
        if context.artifact_id is None:
            persist_agent_run_progress(
                connection,
                run_id,
                plan,
                "failed",
                outputs=context.outputs,
                papers=context.papers,
                artifacts=context.artifacts,
                warnings=[
                    "Research Workflow Run completed "
                    "without a result artifact."
                ],
                run_status_summary=(
                    "failed: completed without a result artifact."
                ),
            )
            return {
                "run_id": run_id,
                "status": "failed",
            }

        completed_at = utc_now()
        run_summary = agent_run_summary(
            plan,
            context.outputs,
            len(context.papers),
            context.artifacts,
        )
        final_status = str(run_summary["status"])
        persist_agent_run_progress(
            connection,
            run_id,
            plan,
            final_status,
            outputs=context.outputs,
            papers=context.papers,
            artifacts=context.artifacts,
            result_artifact_id=context.artifact_id,
            run_status_summary=str(run_summary["summary"]),
        )
        insert_tool_event(
            connection,
            run_dict["session_id"],
            "agent.execute",
            (
                final_status
                if final_status != "completed_with_warnings"
                else "partial"
            ),
            str(run_summary["summary"]),
            completed_at,
        )
        update_project_stage(
            connection,
            project_id=str(run_dict["project_id"]),
            stage="workflow-run",
            updated_at=completed_at,
        )
        connection.commit()
        return {
            "run_id": run_id,
            "status": final_status,
            "artifact_id": context.artifact_id,
        }


def run_agent_job(
    job: DurableJob,
    execution: Any,
) -> dict:
    return run_agent_loop(job.id, execution=execution)


def persist_agent_job_failure(
    job: DurableJob,
    error: object,
) -> None:
    if job.job_type != "agent_run":
        return
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, job.id)
        plan = parse_agent_plan(run_dict["plan_json"])
        for step in plan.get("steps", []) or []:
            if (
                isinstance(step, dict)
                and step.get("status") in {"running", "queued"}
            ):
                step["status"] = "failed"
                break
        persist_agent_run_progress(
            connection,
            job.id,
            plan,
            "failed",
            warnings=[
                "Research Workflow Run exhausted retries: "
                f"{error}"
            ],
            run_status_summary=(
                f"failed after {job.attempts}/"
                f"{job.max_attempts} attempts: {error}"
            ),
        )
        insert_tool_event(
            connection,
            str(run_dict["session_id"]),
            "agent.execute",
            "failed",
            str(error)[:500],
            utc_now(),
        )


def persist_agent_job_cancellation(job: DurableJob) -> None:
    if job.job_type != "agent_run":
        return
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, job.id)
        plan = parse_agent_plan(run_dict["plan_json"])
        mark_queued_agent_steps_cancelled(plan)
        persist_agent_run_progress(
            connection,
            job.id,
            plan,
            "cancelled",
            warnings=[
                "Research Workflow Run cancelled "
                "by durable worker request."
            ],
            run_status_summary=(
                "cancelled: stopped at a durable tool boundary."
            ),
        )


def get_agent_run_status(run_id: str) -> AgentRunStatusResponse:
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        return agent_status_response_from_run(
            connection,
            run_dict,
        )


def cancel_agent_run(run_id: str) -> AgentRunStatusResponse:
    cancelled_at = utc_now()
    should_cancel_job = False
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        plan = parse_agent_plan(run_dict["plan_json"])
        status = str(run_dict["status"])
        if status in TERMINAL_AGENT_RUN_STATUSES:
            return agent_status_response_from_run(
                connection,
                run_dict,
            )
        if status == "planned":
            mark_queued_agent_steps_cancelled(plan)
            persist_agent_run_progress(
                connection,
                run_id,
                plan,
                "cancelled",
                warnings=[
                    "Research Workflow Run cancelled before execution."
                ],
                run_status_summary=(
                    "cancelled: stopped before execution."
                ),
            )
        else:
            should_cancel_job = True
            request_agent_cancellation(
                connection,
                run_id=run_id,
                requested_at=cancelled_at,
            )
            plan["warnings"] = unique_strings(
                [
                    *(plan.get("warnings", []) or []),
                    (
                        "Cancellation requested; current tool "
                        "will finish before stopping."
                    ),
                ]
            )
            plan["run_status_summary"] = (
                "running: cancellation requested; "
                "waiting for current tool to finish."
            )
            plan["updated_at"] = cancelled_at
            update_agent_plan(
                connection,
                run_id=run_id,
                plan=plan,
                updated_at=cancelled_at,
            )
        insert_tool_event(
            connection,
            run_dict["session_id"],
            "agent.cancel",
            "running" if status == "running" else "cancelled",
            (
                "已请求取消 Research Workflow Run；"
                "当前 tool 结束后会停止后续步骤。"
                if status == "running"
                else "已取消尚未开始执行的 Research Workflow Run。"
            ),
            cancelled_at,
        )
        connection.commit()
    if should_cancel_job:
        cancelled_job = cancel_job(run_id)
        if (
            cancelled_job is not None
            and cancelled_job.status == "cancelled"
        ):
            persist_agent_job_cancellation(cancelled_job)
    with get_connection() as connection:
        return agent_status_response_from_run(
            connection,
            fetch_agent_run_dict(connection, run_id),
        )


def execute_agent_run(
    run_id: str,
    payload: AgentExecuteRequest,
) -> AgentExecuteResponse:
    if not payload.confirmed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Research Workflow Run execution "
                "requires confirmation"
            ),
        )

    now = utc_now()
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        project = fetch_project_dict(
            connection,
            run_dict["project_id"],
        )
        ensure_real_project_for_agent(project)
        if str(run_dict["status"]) in {
            "running",
            *TERMINAL_AGENT_RUN_STATUSES,
        }:
            return execute_response_from_status(
                agent_status_response_from_run(
                    connection,
                    run_dict,
                )
            )

        plan = parse_agent_plan(run_dict["plan_json"])
        mark_agent_run_running(
            connection,
            run_id=run_id,
            started_at=now,
        )
        insert_tool_event(
            connection,
            run_dict["session_id"],
            "agent.execute",
            "running",
            (
                "Research Workflow Run 已启动；前端将通过轮询刷新 "
                "tool timeline、artifact 和 workflow steps。"
            ),
            now,
        )
        persist_agent_run_progress(
            connection,
            run_id,
            plan,
            "running",
        )
        enqueue_job(
            job_id=run_id,
            project_id=str(run_dict["project_id"]),
            session_id=str(run_dict["session_id"]),
            job_type="agent_run",
            payload={"run_id": run_id},
            dedupe_key=f"agent_run:{run_id}",
            connection=connection,
        )

    with get_connection() as connection:
        return execute_response_from_status(
            agent_status_response_from_run(
                connection,
                fetch_agent_run_dict(connection, run_id),
            )
        )
