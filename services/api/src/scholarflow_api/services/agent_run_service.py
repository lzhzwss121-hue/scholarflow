from __future__ import annotations

import json
import time
from typing import Any

from fastapi import HTTPException

from scholarflow_api.agent_core import (
    AgentActionDecision,
    AgentBudgets,
    BOUNDED_AGENT_LABEL,
    ToolContext,
    ToolResult,
    PlanRevisionCandidate,
    find_forbidden_model_fields,
    get_model_provider,
    qualify_tool_result,
    sanitize_agent_payload,
    validate_workflow_plan,
)
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
    insert_model_call_audit,
    mark_agent_run_running,
    request_agent_cancellation,
    update_agent_plan,
    update_agent_run_progress,
    update_project_stage,
)
from scholarflow_api.repositories.plan_revision_repository import (
    insert_plan_revision,
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
from scholarflow_api.services.plan_revision_service import (
    apply_accepted_plan_revision,
    build_plan_revision,
    deterministic_revision_candidate,
    remaining_plan_steps,
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
            "failed: Bounded Research Agent stopped with an error."
        )
    elif status == "cancelled":
        summary_text = (
            "cancelled: Bounded Research Agent stopped by user request."
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
            detail="Bounded Research Agent run not found",
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
        agent_label=BOUNDED_AGENT_LABEL,
        execution_mode=str(
            plan.get("execution_mode") or "deterministic_tool_graph"
        ),  # type: ignore[arg-type]
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
        agent_label=status.agent_label,
        execution_mode=status.execution_mode,
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
                        f"Bounded Research Agent run failed: {error}"
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


def _bounded_state(plan: dict[str, Any]) -> dict[str, Any]:
    state = plan.get("bounded_agent")
    if not isinstance(state, dict):
        state = {}
        plan["bounded_agent"] = state
    state.setdefault("version", "bounded-research-agent.v2")
    state.setdefault("budgets", AgentBudgets().to_dict())
    state.setdefault("steps_executed", 0)
    state.setdefault("replans", 0)
    # `replans` is a deprecated compatibility alias. Every accepted or rejected
    # versioned revision attempt increments both counters.
    state.setdefault("plan_revision_count", int(state.get("replans") or 0))
    state.setdefault("active_revision_id", "")
    state.setdefault("revision_fingerprints", [])
    state.setdefault("revision_history", [])
    state.setdefault("retired_steps", [])
    state.setdefault("model_calls", 0)
    state.setdefault("estimated_cost_usd", 0.0)
    state.setdefault("runtime_seconds_used", 0.0)
    state.setdefault("consecutive_failures", 0)
    state.setdefault("trace", [])
    state.setdefault("last_observation", {"type": "run_started"})
    state.setdefault("fallback_reason", "")
    state.setdefault("needs_replan", False)
    return state


def _agent_budgets(state: dict[str, Any]) -> AgentBudgets:
    payload = state.get("budgets") if isinstance(state.get("budgets"), dict) else {}
    max_cost = payload.get("max_cost_usd")
    return AgentBudgets(
        max_steps=max(1, int(payload.get("max_steps") or 8)),
        max_replans=max(0, int(payload.get("max_replans") or 0)),
        max_runtime_seconds=max(1, int(payload.get("max_runtime_seconds") or 900)),
        max_model_calls=max(1, int(payload.get("max_model_calls") or 8)),
        max_cost_usd=(
            float(max_cost)
            if isinstance(max_cost, (int, float)) and float(max_cost) > 0
            else None
        ),
    )


def restore_bounded_checkpoint(
    plan: dict[str, Any],
    durable_checkpoint: dict[str, Any] | None,
) -> None:
    if not isinstance(durable_checkpoint, dict):
        return
    checkpoint_plan = (
        durable_checkpoint.get("plan")
        if isinstance(durable_checkpoint.get("plan"), dict)
        else {}
    )
    checkpoint_state = (
        durable_checkpoint.get("bounded_agent")
        if isinstance(durable_checkpoint.get("bounded_agent"), dict)
        else checkpoint_plan.get("bounded_agent")
        if isinstance(checkpoint_plan.get("bounded_agent"), dict)
        else None
    )
    if checkpoint_state is None:
        return
    current = _bounded_state(plan)
    checkpoint_progress = (
        int(checkpoint_state.get("steps_executed") or 0),
        int(
            checkpoint_state.get("plan_revision_count")
            or checkpoint_state.get("replans")
            or 0
        ),
        len(checkpoint_state.get("trace") or []),
    )
    current_progress = (
        int(current.get("steps_executed") or 0),
        int(current.get("plan_revision_count") or current.get("replans") or 0),
        len(current.get("trace") or []),
    )
    if checkpoint_progress <= current_progress:
        return
    plan["bounded_agent"] = sanitize_agent_payload(checkpoint_state)
    for key in (
        "steps",
        "tool_outputs",
        "papers",
        "artifact_refs",
        "summary_metrics",
        "workflow_steps",
        "warnings",
        "current_tool",
    ):
        if key in checkpoint_plan:
            plan[key] = checkpoint_plan[key]


def _restored_tool_outputs(plan: dict[str, Any]) -> dict[str, Any]:
    step_by_tool = {
        str(step.get("tool") or ""): step
        for step in plan.get("steps", []) or []
        if isinstance(step, dict)
    }
    if not isinstance(plan.get("tool_outputs"), dict):
        return {}
    restored: dict[str, Any] = {}
    for key, value in plan["tool_outputs"].items():
        if not isinstance(value, dict) or not value:
            continue
        step = step_by_tool.get(str(key), {})
        step_status = str(step.get("status") or "done")
        metrics = step.get("metrics") if isinstance(step.get("metrics"), dict) else {}
        is_retry_observation = (
            str(metrics.get("tool_result_status") or "") == "retryable_error"
        )
        if step_status in {"done", "partial", "blocked", "failed"} or is_retry_observation:
            restored[str(key)] = value
    return restored


def _build_agent_context(
    connection: Any,
    run_dict: dict[str, Any],
    project: dict[str, Any],
    plan: dict[str, Any],
) -> ToolContext:
    papers = [
        item for item in plan.get("papers", [])
        if isinstance(item, dict)
    ] if isinstance(plan.get("papers"), list) else []
    outputs = _restored_tool_outputs(plan)
    artifacts: list[dict[str, Any]] = []
    for ref in plan.get("artifact_refs", []) or []:
        if not isinstance(ref, dict) or not ref.get("id"):
            continue
        artifact = fetch_artifact_dict(connection, str(ref["id"]))
        if artifact is not None:
            artifacts.append(artifact)
    context = ToolContext(
        run_id=str(run_dict["id"]),
        project=project,
        task=str(run_dict["task"]),
        plan=plan,
        papers=papers,
        artifacts=artifacts,
        outputs=outputs,
    )
    saved = outputs.get("save_artifact")
    if isinstance(saved, dict) and saved.get("artifact_id"):
        context.artifact_id = str(saved["artifact_id"])
    elif artifacts:
        run_artifacts = [
            item for item in artifacts
            if str(item.get("title") or "").startswith("agent_run_")
        ]
        if run_artifacts:
            context.artifact_id = str(run_artifacts[-1].get("id") or "") or None
    return context


def _step_for_tool(plan: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    return next(
        (
            step for step in plan.get("steps", []) or []
            if isinstance(step, dict) and str(step.get("tool") or "") == tool_name
        ),
        None,
    )


def _eligible_agent_tools(
    plan: dict[str, Any],
    context: ToolContext,
    registry: Any,
) -> list[str]:
    outputs = context.outputs
    has_papers = bool(context.papers)
    has_research_output = any(
        tool in outputs
        for tool in (
            "literature_search",
            "direction_review",
            "research_memory_query",
            "research_decision",
        )
    )
    eligible: list[str] = []
    for step in plan.get("steps", []) or []:
        if not isinstance(step, dict) or step.get("status") != "queued":
            continue
        tool = str(step.get("tool") or "")
        if tool == "create_plan" or not registry.has(tool):
            continue
        if tool == "literature_search":
            eligible.append(tool)
        elif tool == "direction_review" and (
            has_papers or "literature_search" in outputs
        ):
            eligible.append(tool)
        elif tool == "research_memory_query" and (
            has_papers
            or "literature_search" in outputs
            or "direction_review" in outputs
        ):
            eligible.append(tool)
        elif tool == "research_decision" and (
            "direction_review" in outputs
            or "research_memory_query" in outputs
        ):
            eligible.append(tool)
        elif tool == "save_artifact" and has_research_output:
            eligible.append(tool)
        elif tool == "update_timeline" and context.artifact_id:
            eligible.append(tool)
    return eligible


def _remaining_budgets(
    state: dict[str, Any],
    budgets: AgentBudgets,
    elapsed_seconds: float,
) -> dict[str, Any]:
    cost = float(state.get("estimated_cost_usd") or 0.0)
    return {
        "steps": max(0, budgets.max_steps - int(state.get("steps_executed") or 0)),
        "replans": max(0, budgets.max_replans - int(state.get("replans") or 0)),
        "runtime_seconds": max(0.0, budgets.max_runtime_seconds - elapsed_seconds),
        "model_calls": max(0, budgets.max_model_calls - int(state.get("model_calls") or 0)),
        "cost_usd": (
            max(0.0, budgets.max_cost_usd - cost)
            if budgets.max_cost_usd is not None
            else None
        ),
    }


def _agent_observation(
    state: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    return {
        "research_task": context.task[:1000],
        "project_context": {
            "title": str(context.project.get("title") or "")[:300],
            "keyword": str(context.project.get("keyword") or "")[:500],
            "field": str(context.project.get("field") or "")[:200],
        },
        "last_tool_result": sanitize_agent_payload(state.get("last_observation")),
        "completed_or_attempted_tools": sorted(context.outputs),
        "paper_count": len(context.papers),
        "artifact_created": bool(context.artifact_id),
        "consecutive_failures": int(state.get("consecutive_failures") or 0),
    }


def _validate_runtime_decision(
    decision: AgentActionDecision,
    eligible_tools: set[str],
) -> None:
    forbidden = find_forbidden_model_fields(decision.arguments)
    if forbidden:
        raise ValueError(
            "agent_action_forbidden_control_fields: " + ", ".join(sorted(forbidden))
        )
    if decision.arguments:
        raise ValueError("agent_action_arguments_not_allowed")
    if decision.action == "tool" and decision.tool not in eligible_tools:
        raise ValueError(
            f"agent_action_tool_not_allowed: {decision.tool or '<empty>'}"
        )
    if decision.action not in {"tool", "finish", "fallback"}:
        raise ValueError("agent_action_invalid")


def _append_agent_trace(
    state: dict[str, Any],
    *,
    observation: dict[str, Any],
    decision: AgentActionDecision | None,
    result: dict[str, Any],
) -> None:
    trace = state.get("trace")
    if not isinstance(trace, list):
        trace = []
        state["trace"] = trace
    trace.append(
        {
            "index": len(trace) + 1,
            "recorded_at": utc_now(),
            "observation": sanitize_agent_payload(observation),
            "reasoning_summary": (
                decision.reasoning_summary[:1000] if decision is not None else ""
            ),
            "selected_tool": decision.tool if decision is not None else "",
            "arguments": sanitize_agent_payload(
                decision.arguments if decision is not None else {}
            ),
            "action": decision.action if decision is not None else "rejected",
            "result": sanitize_agent_payload(result),
            "checkpoint": {
                "steps_executed": int(state.get("steps_executed") or 0),
                "replans": int(state.get("replans") or 0),
                "model_calls": int(state.get("model_calls") or 0),
            },
        }
    )
    if len(trace) > 100:
        del trace[:-100]


def _apply_tool_result(
    context: ToolContext,
    plan: dict[str, Any],
    result: ToolResult,
) -> dict[str, Any]:
    context.outputs[result.tool] = result.data
    metrics = result.summary_metrics or infer_tool_summary_metrics(result.data)
    metrics = {**metrics, "tool_result_status": result.status}
    context.summary_metrics[result.tool] = metrics
    papers = result.data.get("papers")
    if isinstance(papers, list) and papers:
        context.papers = [item for item in papers if isinstance(item, dict)]
        plan["papers"] = context.papers
    artifact = result.data.get("artifact")
    if isinstance(artifact, dict):
        context.artifacts.append(artifact)
    artifacts = result.data.get("artifacts")
    if isinstance(artifacts, list):
        context.artifacts.extend(item for item in artifacts if isinstance(item, dict))
    if result.data.get("artifact_id"):
        context.artifact_id = str(result.data["artifact_id"])
    step_status = {
        "success": "done",
        "partial": "partial",
        "blocked": "blocked",
        "retryable_error": "queued",
        "fatal_error": "failed",
    }[str(result.status)]
    step = _step_for_tool(plan, result.tool)
    if step is not None:
        mark_plan_step_by_id(plan, str(step.get("id") or ""), step_status, metrics)
    return metrics


def _bounded_checkpoint(
    execution: Any,
    plan: dict[str, Any],
    state: dict[str, Any],
    tool_name: str,
    progress: int,
) -> None:
    if execution is None:
        return
    execution.checkpoint(
        tool_name,
        progress,
        {
            "execution_mode": "bounded_observe_reason_act",
            "bounded_agent": state,
            "plan": plan,
        },
    )


def _attempt_plan_revision(
    *,
    connection: Any,
    execution: Any,
    run_dict: dict[str, Any],
    plan: dict[str, Any],
    state: dict[str, Any],
    context: ToolContext,
    registry: Any,
    provider: Any,
    budgets: AgentBudgets,
    observation: dict[str, Any],
    elapsed: float,
    trigger: str,
    preferred_tool: str = "",
) -> Any:
    previous = remaining_plan_steps(plan)
    source_observation = state.get("last_observation")
    source_tool = (
        str(source_observation.get("tool") or "")
        if isinstance(source_observation, dict)
        else ""
    )
    source_tool_result_id = str(state.get("last_tool_result_id") or "") or None
    fallback_reason = ""
    candidate: PlanRevisionCandidate | None = None
    proposal = getattr(provider, "propose_plan_revision", None)
    can_call_model = (
        callable(proposal)
        and int(state.get("model_calls") or 0) < budgets.max_model_calls
    )
    if can_call_model:
        state["model_calls"] = int(state.get("model_calls") or 0) + 1
        try:
            candidate = proposal(
                observation,
                previous,
                registry.describe(),
                _remaining_budgets(state, budgets, elapsed),
            )
            if not isinstance(candidate, PlanRevisionCandidate):
                raise ValueError("plan_revision_candidate_invalid")
        except Exception as error:
            fallback_reason = f"invalid_plan_revision_candidate:{error}"
    else:
        fallback_reason = (
            "max_model_calls_budget_reached"
            if callable(proposal)
            else "provider_has_no_plan_revision"
        )

    model_request_id: str | None = None
    if candidate is not None and candidate.audit is not None:
        model_request_id = insert_model_call_audit(
            connection,
            project_id=str(run_dict["project_id"]),
            run_id=str(run_dict["id"]),
            audit=candidate.audit.to_dict(),
        )
        state["estimated_cost_usd"] = round(
            float(state.get("estimated_cost_usd") or 0.0)
            + float(candidate.audit.estimated_cost_usd or 0.0),
            8,
        )
        fallback_reason = candidate.deterministic_fallback_reason or fallback_reason

    if candidate is None or candidate.deterministic_fallback_reason:
        fallback_reason = fallback_reason or "deterministic_revision_policy"
        candidate = deterministic_revision_candidate(
            previous,
            reason=(
                f"Revise remaining steps after {trigger}; deterministic policy "
                "preserves completed history and research-state gates."
            ),
            preferred_tool=preferred_tool,
            source_tool=source_tool,
            fallback_reason=fallback_reason,
        )

    previous_fingerprints = {
        str(value)
        for value in state.get("revision_fingerprints", [])
        if isinstance(value, str)
    }
    revision = build_plan_revision(
        run_id=str(run_dict["id"]),
        plan=plan,
        candidate=candidate,
        trigger=trigger,
        source_tool_result_id=source_tool_result_id,
        model_request_id=model_request_id,
        registered_tools=registry.names(),
        budgets=budgets,
        revision_attempts=int(
            state.get("plan_revision_count") or state.get("replans") or 0
        ),
        previous_fingerprints=previous_fingerprints,
    )
    stored_revision = insert_plan_revision(connection, revision)
    history = state.get("revision_history")
    if not isinstance(history, list):
        history = []
        state["revision_history"] = history
    already_recorded = any(
        isinstance(item, dict)
        and str(item.get("revision_id") or "") == stored_revision.revision_id
        for item in history
    )
    if not already_recorded:
        count = int(state.get("plan_revision_count") or state.get("replans") or 0) + 1
        state["plan_revision_count"] = count
        state["replans"] = count
        history.append(
            {
                "revision_id": stored_revision.revision_id,
                "parent_revision_id": stored_revision.parent_revision_id,
                "trigger": stored_revision.trigger,
                "reason": stored_revision.reason,
                "created_at": stored_revision.created_at,
                "validation_result": stored_revision.validation_result,
                "plan_diff": stored_revision.plan_diff,
            }
        )
    apply_accepted_plan_revision(plan, stored_revision)
    state["needs_replan"] = False
    state["needs_plan_revision"] = False
    validation_status = str(
        stored_revision.validation_result.get("status") or "rejected"
    )
    insert_tool_event(
        connection,
        str(run_dict["session_id"]),
        "agent.plan_revision",
        "done" if validation_status == "accepted" else "partial",
        (
            f"PlanRevision {stored_revision.revision_id} {validation_status}: "
            f"{stored_revision.reason}"
        )[:500],
        utc_now(),
    )
    persist_agent_run_progress(
        connection,
        str(run_dict["id"]),
        plan,
        "running",
        outputs=context.outputs,
        papers=context.papers,
        artifacts=context.artifacts,
        warnings=(
            []
            if validation_status == "accepted"
            else [
                "Plan revision rejected: "
                + ", ".join(stored_revision.validation_result.get("reasons") or [])
            ]
        ),
        run_status_summary=(
            f"running: plan revision {validation_status}."
        ),
    )
    _bounded_checkpoint(
        execution,
        plan,
        state,
        "plan_revision",
        min(90, 10 + int(state.get("steps_executed") or 0) * 10),
    )
    return stored_revision


def _has_reliable_agent_evidence(context: ToolContext) -> bool:
    memory = context.outputs.get("research_memory_query")
    if isinstance(memory, dict):
        if str(memory.get("reliability_status") or "") == "no_reliable_hit":
            return False
        if int(memory.get("hit_count") or memory.get("memory_hit_count") or 0) > 0:
            return True
    direction = context.outputs.get("direction_review")
    if isinstance(direction, dict) and int(direction.get("relevant_read_count") or 0) > 0:
        return True
    return False


def _mark_remaining_steps(plan: dict[str, Any], status: str) -> None:
    for step in plan.get("steps", []) or []:
        if isinstance(step, dict) and step.get("status") in {"queued", "running"}:
            step["status"] = status


def _persist_bounded_trace_artifact(
    connection: Any,
    context: ToolContext,
    plan: dict[str, Any],
) -> None:
    if not context.artifact_id:
        return
    row = connection.execute(
        "SELECT content_json FROM artifacts WHERE id = ? AND project_id = ?",
        (context.artifact_id, context.project["id"]),
    ).fetchone()
    if row is None:
        return
    try:
        payload = json.loads(str(row["content_json"] or "{}"))
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["agent_label"] = BOUNDED_AGENT_LABEL
    payload["execution_mode"] = str(
        plan.get("execution_mode") or "bounded_observe_reason_act"
    )
    payload["bounded_agent"] = sanitize_agent_payload(_bounded_state(plan))
    connection.execute(
        "UPDATE artifacts SET content_json = ?, updated_at = ? WHERE id = ?",
        (
            json.dumps(payload, ensure_ascii=False, indent=2),
            utc_now(),
            context.artifact_id,
        ),
    )


def _stop_bounded_agent(
    connection: Any,
    run_dict: dict[str, Any],
    plan: dict[str, Any],
    context: ToolContext,
    state: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    _mark_remaining_steps(plan, "blocked")
    state["stop_reason"] = reason
    state["last_observation"] = {
        "type": "safe_stop",
        "status": "blocked",
        "summary": reason,
    }
    _persist_bounded_trace_artifact(connection, context, plan)
    persist_agent_run_progress(
        connection,
        str(run_dict["id"]),
        plan,
        "partial",
        outputs=context.outputs,
        papers=context.papers,
        artifacts=context.artifacts,
        warnings=[reason],
        run_status_summary=f"blocked: {reason}",
    )
    insert_tool_event(
        connection,
        str(run_dict["session_id"]),
        "bounded_agent.stop",
        "blocked",
        reason[:500],
        utc_now(),
    )
    connection.commit()
    return {"run_id": str(run_dict["id"]), "status": "partial", "reason": reason}


def _finalize_bounded_agent(
    connection: Any,
    run_dict: dict[str, Any],
    project: dict[str, Any],
    plan: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    _mark_remaining_steps(plan, "blocked")
    if context.artifact_id is None and context.artifacts:
        context.artifact_id = str(context.artifacts[-1].get("id") or "") or None
    if context.artifact_id is None:
        return _stop_bounded_agent(
            connection,
            run_dict,
            plan,
            context,
            _bounded_state(plan),
            reason="no result artifact was produced before the bounded stop",
        )
    _persist_bounded_trace_artifact(connection, context, plan)
    run_summary = agent_run_summary(
        plan,
        context.outputs,
        len(context.papers),
        context.artifacts,
    )
    final_status = str(run_summary["status"])
    if any(
        isinstance(step, dict) and step.get("status") in {"partial", "blocked", "failed"}
        for step in plan.get("steps", []) or []
    ):
        final_status = "partial"
    if not _has_reliable_agent_evidence(context):
        final_status = "partial"
        run_summary["summary"] = "no_reliable_hit: no reliable paper evidence was established."
    persist_agent_run_progress(
        connection,
        str(run_dict["id"]),
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
        str(run_dict["session_id"]),
        "bounded_agent.complete",
        "done" if final_status == "completed" else "partial",
        str(run_summary["summary"]),
        utc_now(),
    )
    update_project_stage(
        connection,
        project_id=str(run_dict["project_id"]),
        stage="workflow-run",
        updated_at=utc_now(),
    )
    connection.commit()
    return {
        "run_id": str(run_dict["id"]),
        "status": final_status,
        "artifact_id": context.artifact_id,
    }


def run_bounded_agent_loop(
    run_id: str,
    execution: Any = None,
    durable_checkpoint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        project = fetch_project_dict(connection, str(run_dict["project_id"]))
        ensure_real_project_for_agent(project)
        plan = parse_agent_plan(str(run_dict["plan_json"]))
        if not plan.get("user_confirmed"):
            return _stop_bounded_agent(
                connection,
                run_dict,
                plan,
                _build_agent_context(connection, run_dict, project, plan),
                _bounded_state(plan),
                reason="user confirmation is required before external or tool actions",
            )
        restore_bounded_checkpoint(plan, durable_checkpoint)
        state = _bounded_state(plan)
        budgets = _agent_budgets(state)
        prior_runtime_seconds = float(state.get("runtime_seconds_used") or 0.0)
        context = _build_agent_context(connection, run_dict, project, plan)
        registry = build_agent_tool_registry(connection)
        validate_workflow_plan(plan, registered_tools=registry.names())
        for step in plan.get("steps", []) or []:
            if isinstance(step, dict) and step.get("status") == "running":
                step["status"] = "queued"

        while True:
            if execution is not None:
                execution.raise_if_cancelled()
            if agent_cancellation_requested(connection, run_id):
                mark_queued_agent_steps_cancelled(plan)
                persist_agent_run_progress(
                    connection,
                    run_id,
                    plan,
                    "cancelled",
                    outputs=context.outputs,
                    papers=context.papers,
                    artifacts=context.artifacts,
                    warnings=["Bounded Research Agent cancelled by user request."],
                    run_status_summary="cancelled: stopped at a tool boundary.",
                )
                return {"run_id": run_id, "status": "cancelled"}

            elapsed = prior_runtime_seconds + (time.monotonic() - started)
            state["runtime_seconds_used"] = round(elapsed, 3)
            if elapsed >= budgets.max_runtime_seconds:
                return _stop_bounded_agent(
                    connection, run_dict, plan, context, state,
                    reason="max_runtime_seconds budget reached",
                )
            if int(state.get("steps_executed") or 0) >= budgets.max_steps:
                return _stop_bounded_agent(
                    connection, run_dict, plan, context, state,
                    reason="max_steps budget reached",
                )
            if (
                int(state.get("model_calls") or 0) >= budgets.max_model_calls
                and not state.get("needs_plan_revision")
                and not state.get("needs_replan")
            ):
                return _stop_bounded_agent(
                    connection, run_dict, plan, context, state,
                    reason="max_model_calls budget reached",
                )
            current_cost = float(state.get("estimated_cost_usd") or 0.0)
            if budgets.max_cost_usd is not None and current_cost >= budgets.max_cost_usd:
                return _stop_bounded_agent(
                    connection, run_dict, plan, context, state,
                    reason="optional model cost budget reached",
                )
            if int(state.get("consecutive_failures") or 0) >= 3:
                return _stop_bounded_agent(
                    connection, run_dict, plan, context, state,
                    reason="consecutive tool failure limit reached",
                )

            eligible = _eligible_agent_tools(plan, context, registry)
            if not eligible:
                if context.artifact_id:
                    return _finalize_bounded_agent(
                        connection, run_dict, project, plan, context
                    )
                return _stop_bounded_agent(
                    connection, run_dict, plan, context, state,
                    reason=(
                        "no_reliable_hit: no eligible evidence-producing tool remains"
                    ),
                )

            observation = _agent_observation(state, context)
            provider = get_model_provider()
            revision_handled = False
            if state.get("needs_plan_revision") or state.get("needs_replan"):
                if int(
                    state.get("plan_revision_count")
                    or state.get("replans")
                    or 0
                ) >= budgets.max_replans:
                    _append_agent_trace(
                        state,
                        observation=observation,
                        decision=None,
                        result={
                            "status": "blocked",
                            "summary": "max_plan_revisions budget reached",
                        },
                    )
                    return _stop_bounded_agent(
                        connection, run_dict, plan, context, state,
                        reason="max_plan_revisions budget reached",
                    )
                _attempt_plan_revision(
                    connection=connection,
                    execution=execution,
                    run_dict=run_dict,
                    plan=plan,
                    state=state,
                    context=context,
                    registry=registry,
                    provider=provider,
                    budgets=budgets,
                    observation=observation,
                    elapsed=elapsed,
                    trigger="retryable_tool_result",
                )
                revision_handled = True
                eligible = _eligible_agent_tools(plan, context, registry)
                observation = _agent_observation(state, context)
                if not eligible:
                    return _stop_bounded_agent(
                        connection, run_dict, plan, context, state,
                        reason="no_reliable_hit: plan revision left no eligible tool",
                    )
                if int(state.get("model_calls") or 0) >= budgets.max_model_calls:
                    return _stop_bounded_agent(
                        connection, run_dict, plan, context, state,
                        reason="max_model_calls budget reached after plan revision",
                    )
            descriptions = {
                item["name"]: item["description"]
                for item in registry.describe()
                if item.get("name") in eligible
            }
            allowed = [
                {"name": name, "description": descriptions.get(name, "")}
                for name in eligible
            ]
            state["model_calls"] = int(state.get("model_calls") or 0) + 1
            try:
                decision = provider.choose_next_action(
                    observation,
                    allowed,
                    _remaining_budgets(state, budgets, elapsed),
                )
                _validate_runtime_decision(decision, set(eligible))
            except Exception as error:
                rejection = {
                    "status": "fatal_error",
                    "summary": f"model action rejected: {error}",
                }
                _append_agent_trace(
                    state,
                    observation=observation,
                    decision=None,
                    result=rejection,
                )
                state["fallback_reason"] = "invalid_or_unregistered_model_action"
                plan["execution_mode"] = "deterministic_tool_graph"
                persist_agent_run_progress(
                    connection,
                    run_id,
                    plan,
                    "running",
                    outputs=context.outputs,
                    papers=context.papers,
                    artifacts=context.artifacts,
                    warnings=[rejection["summary"]],
                    run_status_summary="fallback: rejected model action.",
                )
                _bounded_checkpoint(execution, plan, state, "fallback", 10)
                return {"run_id": run_id, "status": "running", "fallback": True}

            if decision.audit is not None:
                audit = decision.audit.to_dict()
                insert_model_call_audit(
                    connection,
                    project_id=str(run_dict["project_id"]),
                    run_id=run_id,
                    audit=audit,
                )
                state["estimated_cost_usd"] = round(
                    float(state.get("estimated_cost_usd") or 0.0)
                    + float(decision.audit.estimated_cost_usd or 0.0),
                    8,
                )

            if decision.replan and not revision_handled:
                if int(
                    state.get("plan_revision_count")
                    or state.get("replans")
                    or 0
                ) >= budgets.max_replans:
                    _append_agent_trace(
                        state,
                        observation=observation,
                        decision=decision,
                        result={
                            "status": "blocked",
                            "summary": "max_plan_revisions budget reached",
                        },
                    )
                    return _stop_bounded_agent(
                        connection, run_dict, plan, context, state,
                        reason="max_plan_revisions budget reached",
                    )
                _attempt_plan_revision(
                    connection=connection,
                    execution=execution,
                    run_dict=run_dict,
                    plan=plan,
                    state=state,
                    context=context,
                    registry=registry,
                    provider=provider,
                    budgets=budgets,
                    observation=observation,
                    elapsed=elapsed,
                    trigger="model_requested_revision",
                    preferred_tool=decision.tool,
                )
                eligible = _eligible_agent_tools(plan, context, registry)
                try:
                    _validate_runtime_decision(decision, set(eligible))
                except ValueError as error:
                    state["last_observation"] = {
                        "status": "blocked",
                        "summary": f"revised plan rejected selected action: {error}",
                    }
                    continue

            if decision.action == "fallback":
                state["fallback_reason"] = (
                    decision.audit.fallback_reason
                    if decision.audit is not None
                    else "provider_requested_fallback"
                )
                _append_agent_trace(
                    state,
                    observation=observation,
                    decision=decision,
                    result={"status": "partial", "summary": "deterministic fallback"},
                )
                plan["execution_mode"] = "deterministic_tool_graph"
                persist_agent_run_progress(
                    connection,
                    run_id,
                    plan,
                    "running",
                    outputs=context.outputs,
                    papers=context.papers,
                    artifacts=context.artifacts,
                    warnings=["Bounded action provider unavailable; deterministic fallback used."],
                    run_status_summary="running: deterministic fallback.",
                )
                _bounded_checkpoint(execution, plan, state, "fallback", 10)
                return {"run_id": run_id, "status": "running", "fallback": True}

            if decision.action == "finish":
                if context.artifact_id is None:
                    blocked_result = {
                        "status": "blocked",
                        "summary": "finish rejected until save_artifact creates a result",
                    }
                    state["last_observation"] = blocked_result
                    _append_agent_trace(
                        state,
                        observation=observation,
                        decision=decision,
                        result=blocked_result,
                    )
                    persist_agent_run_progress(
                        connection,
                        run_id,
                        plan,
                        "running",
                        outputs=context.outputs,
                        papers=context.papers,
                        artifacts=context.artifacts,
                        warnings=[blocked_result["summary"]],
                    )
                    continue
                return _finalize_bounded_agent(
                    connection, run_dict, project, plan, context
                )

            tool_name = decision.tool
            step = _step_for_tool(plan, tool_name)
            if step is None:
                raise RuntimeError(f"Missing plan step for allowlisted tool {tool_name}")
            mark_plan_step_by_id(plan, str(step.get("id") or ""), "running")
            insert_tool_event(
                connection,
                str(run_dict["session_id"]),
                tool_name,
                "running",
                f"Bounded Research Agent selected {tool_name}.",
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
            _bounded_checkpoint(
                execution,
                plan,
                state,
                tool_name,
                min(90, 10 + int(state.get("steps_executed") or 0) * 10),
            )
            try:
                result = qualify_tool_result(registry.run(tool_name, context))
            except (ValueError, KeyError, PermissionError, HTTPException) as error:
                result = ToolResult(
                    tool=tool_name,
                    status="fatal_error",
                    summary=str(error) or error.__class__.__name__,
                    data={"errors": [str(error)]},
                )
            except Exception as error:  # A recoverable tool failure is model-visible.
                result = ToolResult(
                    tool=tool_name,
                    status="retryable_error",
                    summary=str(error) or error.__class__.__name__,
                    data={"errors": [str(error)]},
                )

            state["steps_executed"] = int(state.get("steps_executed") or 0) + 1
            _apply_tool_result(context, plan, result)
            result_observation = result.to_observation()
            state["last_observation"] = result_observation
            if result.status in {"retryable_error", "fatal_error"}:
                state["consecutive_failures"] = int(
                    state.get("consecutive_failures") or 0
                ) + 1
                state["needs_plan_revision"] = result.status == "retryable_error"
                state["needs_replan"] = state["needs_plan_revision"]
            else:
                state["consecutive_failures"] = 0
                state["needs_replan"] = False
                state["needs_plan_revision"] = False
            _append_agent_trace(
                state,
                observation=observation,
                decision=decision,
                result=result_observation,
            )
            event_status = {
                "success": "done",
                "partial": "partial",
                "blocked": "blocked",
                "retryable_error": "partial",
                "fatal_error": "failed",
            }[str(result.status)]
            tool_result_event_id = insert_tool_event(
                connection,
                str(run_dict["session_id"]),
                tool_name,
                event_status,  # type: ignore[arg-type]
                result.summary[:500],
                utc_now(),
            )
            state["last_tool_result_id"] = tool_result_event_id
            persist_agent_run_progress(
                connection,
                run_id,
                plan,
                "running",
                outputs=context.outputs,
                papers=context.papers,
                artifacts=context.artifacts,
                warnings=(
                    [f"{tool_name}: {result.status}: {result.summary}"]
                    if result.status != "success"
                    else []
                ),
            )
            _bounded_checkpoint(
                execution,
                plan,
                state,
                tool_name,
                min(95, 15 + int(state.get("steps_executed") or 0) * 10),
            )
            if tool_name == "update_timeline" and result.status == "success":
                return _finalize_bounded_agent(
                    connection, run_dict, project, plan, context
                )
            if result.status == "fatal_error":
                return _stop_bounded_agent(
                    connection, run_dict, plan, context, state,
                    reason=f"fatal tool error in {tool_name}: {result.summary}",
                )


def run_agent_loop(
    run_id: str,
    execution: Any = None,
    durable_checkpoint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        plan = parse_agent_plan(str(run_dict.get("plan_json") or "{}"))
        execution_mode = str(plan.get("execution_mode") or "deterministic_tool_graph")
    if execution_mode == "bounded_observe_reason_act":
        outcome = run_bounded_agent_loop(
            run_id,
            execution=execution,
            durable_checkpoint=durable_checkpoint,
        )
        if outcome.get("fallback"):
            return run_deterministic_agent_loop(run_id, execution=execution)
        return outcome
    return run_deterministic_agent_loop(run_id, execution=execution)


def run_deterministic_agent_loop(run_id: str, execution: Any = None) -> dict:
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
        restored_outputs = _restored_tool_outputs(plan)
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
            if step.get("status") in {
                "done",
                "partial",
                "blocked",
                "failed",
                "cancelled",
            }:
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
                        "Bounded Research Agent run cancelled "
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
                        "用户已取消 Bounded Research Agent run，"
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
                    "Bounded Research Agent run completed "
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
    return run_agent_loop(
        job.id,
        execution=execution,
        durable_checkpoint=job.checkpoint,
    )


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
                "Bounded Research Agent run exhausted retries: "
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
                "Bounded Research Agent run cancelled "
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
                    "Bounded Research Agent run cancelled before execution."
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
                "已请求取消 Bounded Research Agent run；"
                "当前 tool 结束后会停止后续步骤。"
                if status == "running"
                else "已取消尚未开始执行的 Bounded Research Agent run。"
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
                "Bounded Research Agent run execution "
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
        plan["user_confirmed"] = True
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
                "Bounded Research Agent 已启动；前端将通过轮询刷新 "
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
