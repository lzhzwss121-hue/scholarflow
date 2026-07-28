from __future__ import annotations

import hashlib
import json
import re
from typing import Callable

from fastapi import APIRouter, Body, HTTPException

from scholarflow_api import __version__
from scholarflow_api.agent_core import (
    ToolContext,
    ToolRegistry,
    ToolResult,
    build_mock_papers,
    get_model_provider,
    render_execution_markdown,
    render_plan_markdown,
    validate_workflow_plan,
)
from scholarflow_api.api_helpers import (
    artifact_ref,
    build_paper_card_source,
    build_warning_summary_metrics,
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
from scholarflow_api.database import get_connection, init_db, new_id, row_to_dict, utc_now
from scholarflow_api.direction_review import (
    build_baseline_papers_from_readings,
    build_direction_readings,
    build_direction_review_bundle,
    refresh_direction_reading_research_sights,
    render_direction_review_json,
    render_direction_review_markdown,
    retrieve_direction_candidate_pool,
)
from scholarflow_api.full_text import FullTextResult, parse_pdf_bytes, provided_full_text, resolve_open_full_text
from scholarflow_api.literature import LOW_RECALL_THRESHOLD, render_paper_table_json, render_paper_table_markdown, search_literature
from scholarflow_api.jobs.models import DurableJob, JobCancelled
from scholarflow_api.jobs.repository import (
    cancel_job,
    enqueue_job,
    recover_orphaned_runs,
    worker_health,
)
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
from scholarflow_api.rag_index import (
    delete_paper_chunks,
    fetch_paper_chunks,
    index_paper_full_text,
    paper_index_status,
    project_index_status,
)
from scholarflow_api.rag_answer import answer_project_rag, render_rag_answer_markdown
from scholarflow_api.rag_evaluation import (
    assess_rag_answer,
    insert_rag_evaluation,
    list_rag_evaluations,
)
from scholarflow_api.rag_retrieval import (
    EmbeddingError,
    embed_project_chunks,
    get_embedding_provider,
    retrieve_project_chunks,
)
from scholarflow_api.repositories.workflow import statement as workflow_sql
from scholarflow_api.routers.artifacts import get_artifact, list_project_artifact_summaries, save_artifact
from scholarflow_api.schemas import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentRunStatusResponse,
    AgentPlanRequest,
    AgentPlanResponse,
    Artifact,
    ArtifactCreate,
    ArtifactRef,
    ArtifactSummary,
    BaselineMap,
    DirectionReviewRequest,
    DirectionReviewResponse,
    DirectionReviewRunStatusResponse,
    HealthResponse,
    LiteratureSearchRequest,
    LiteratureSearchResponse,
    Paper,
    PaperCard,
    PaperCardCreateRequest,
    PaperCardResponse,
    PaperChunk,
    PaperChunkIndexRequest,
    PaperChunkIndexStatus,
    PaperFullTextExtractResponse,
    Project,
    ProjectCreate,
    ProjectRagIndexStatus,
    RagAnswerRequest,
    RagAnswerResponse,
    RagEmbeddingRequest,
    RagEmbeddingStatus,
    RagEvaluationListResponse,
    RagEvaluationRecord,
    RagSearchRequest,
    RagSearchResponse,
    ResearchSight,
    ResearchDecisionRequest,
    ResearchDecisionResponse,
    DirectionMemory,
    PaperMemoryHit,
    ResearchMemoryQueryRequest,
    ResearchMemoryQueryResponse,
    Session,
    ToolEvent,
    WorkflowStepState,
)


router = APIRouter()


def make_artifact_refs(artifacts: list[dict]) -> list[ArtifactRef]:
    return [ArtifactRef.model_validate(artifact_ref(artifact)) for artifact in artifacts]


def insert_model_call_audit(
    connection,
    *,
    project_id: str,
    run_id: str,
    audit: dict,
) -> None:
    safe_fields = {
        "provider": str(audit.get("provider") or "local"),
        "model": str(audit.get("model") or ""),
        "purpose": str(audit.get("purpose") or ""),
        "prompt_version": str(audit.get("prompt_version") or ""),
        "request_timestamp": str(audit.get("request_timestamp") or utc_now()),
        "latency_ms": max(0, int(audit.get("latency_ms") or 0)),
        "response_status": str(audit.get("response_status") or "unknown"),
        "fallback_reason": str(audit.get("fallback_reason") or ""),
        "requested_provider": str(audit.get("requested_provider") or ""),
        "requested_model": str(audit.get("requested_model") or ""),
        "external_data_sent": int(bool(audit.get("external_data_sent"))),
    }
    connection.execute(
        workflow_sql("insert_model_call_audit_1"),
        (
            new_id("model_call"),
            project_id,
            run_id,
            safe_fields["provider"],
            safe_fields["model"],
            safe_fields["purpose"],
            safe_fields["prompt_version"],
            safe_fields["request_timestamp"],
            safe_fields["latency_ms"],
            safe_fields["response_status"],
            safe_fields["fallback_reason"],
            safe_fields["requested_provider"],
            safe_fields["requested_model"],
            safe_fields["external_data_sent"],
            utc_now(),
        ),
    )


def is_demo_project_dict(project: dict) -> bool:
    return (
        project.get("id") == "local-bootstrap"
        or str(project.get("workflow", "")).lower() == "demo-preview"
        or str(project.get("stage", "")).lower() in {"seed", "demo"}
    )


def project_response_dict(project: dict) -> dict:
    data = dict(project)
    data["is_demo"] = is_demo_project_dict(data)
    return data


def ensure_real_project_for_agent(project: dict) -> None:
    if is_demo_project_dict(project):
        raise HTTPException(
            status_code=400,
            detail="Demo project is read-only preview. Create a real project before running workflow tools.",
        )


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


def literature_step_status(paper_count: int, errors: list[str], relevance_coverage: dict[str, int] | None = None) -> str:
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


def direction_step_status(review_status: str, round_read_count: int) -> str:
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


def agent_run_summary(plan: dict, outputs: dict[str, object] | None, paper_count: int, artifacts: list[dict] | None = None) -> dict[str, object]:
    outputs = outputs or {}
    artifacts = artifacts or []
    warnings: list[str] = []

    literature_output = outputs.get("literature_search")
    if isinstance(literature_output, dict):
        for error in literature_output.get("errors", []) or []:
            warnings.append(f"degraded retrieval: {error}")
        coverage = literature_output.get("relevance_coverage") if isinstance(literature_output.get("relevance_coverage"), dict) else {}
        if coverage:
            off_topic_count = int(coverage.get("off_topic_count") or 0)
            weak_count = int(coverage.get("weak_match_count") or 0)
            returned_count = int(coverage.get("returned_count") or paper_count)
            if off_topic_count or weak_count:
                warnings.append(f"Paper Table partial: filtered weak={weak_count}, off-topic={off_topic_count}.")
            if returned_count < LOW_RECALL_THRESHOLD:
                warnings.append(f"Paper Table partial: only {returned_count} returned papers.")

    direction_output = outputs.get("direction_review")
    if isinstance(direction_output, dict):
        review_status = str(direction_output.get("review_status") or "")
        if review_status and review_status != "complete":
            warnings.append(
                "Direction Review "
                f"{review_status}: relevant_read_count={direction_output.get('relevant_read_count', 0)}."
            )
        for error in direction_output.get("errors", []) or []:
            warnings.append(f"Direction Review warning: {error}")

    memory_output = outputs.get("research_memory_query")
    if isinstance(memory_output, dict):
        for warning in memory_output.get("warnings", []) or []:
            warnings.append(f"Paper Memory warning: {warning}")

    decision_output = outputs.get("research_decision")
    if isinstance(decision_output, dict):
        decision_status = str(decision_output.get("decision_status") or "")
        if decision_status and decision_status != "complete":
            warnings.append(f"Gap Board {decision_status}: evidence quality is insufficient.")
        if decision_output.get("experiment_status") == "blocked":
            warnings.append("Experiment Plan blocked: missing reproducible anchor.")
        elif decision_output.get("experiment_status") == "partial":
            warnings.append("Experiment Plan partial: research anchors exist but execution conditions remain unknown.")
        for warning in decision_output.get("warnings", []) or []:
            warnings.append(f"Research Decision warning: {warning}")

    for step in plan.get("steps", []) or []:
        metrics = step.get("metrics") if isinstance(step, dict) else {}
        if isinstance(metrics, dict) and metrics.get("warning_count"):
            tool = step.get("tool", "tool") if isinstance(step, dict) else "tool"
            warnings.append(f"{tool} reported {metrics.get('warning_count')} warnings.")

    warnings = unique_strings(warnings)
    run_status = "completed_with_warnings" if warnings else "completed"
    if any("blocked" in warning.lower() for warning in warnings):
        run_status = "partial"

    summary = (
        "completed"
        if run_status == "completed"
        else f"{run_status}: {len(warnings)} warning(s); latest artifact count={len(artifacts)}."
    )
    return {
        "status": run_status,
        "summary": summary,
        "warnings": warnings,
        "artifact_refs": make_artifact_refs(artifacts),
    }


def agent_workflow_steps(outputs: dict[str, object] | None, artifacts: list[dict] | None, updated_at: str) -> list[WorkflowStepState]:
    outputs = outputs or {}
    artifacts = artifacts or []
    steps: list[WorkflowStepState] = []

    literature_output = outputs.get("literature_search")
    if isinstance(literature_output, dict):
        papers = literature_output.get("papers") if isinstance(literature_output.get("papers"), list) else []
        errors = [str(error) for error in literature_output.get("errors", []) or []]
        coverage = literature_output.get("relevance_coverage") if isinstance(literature_output.get("relevance_coverage"), dict) else {}
        artifact = literature_output.get("artifact") if isinstance(literature_output.get("artifact"), dict) else None
        steps.append(
            workflow_step_state(
                step_id="paper-table",
                status=literature_step_status(len(papers), errors, coverage),
                label="Paper Table",
                summary=(
                    f"{coverage.get('candidate_count', len(papers))} candidates / "
                    f"{coverage.get('eligible_count', coverage.get('returned_count', len(papers)))} eligible / "
                    f"{coverage.get('returned_count', len(papers))} returned / "
                    f"{coverage.get('truncated_count', 0)} truncated / "
                    f"{coverage.get('off_topic_count', 0)} off-topic filtered"
                ),
                warnings=[f"degraded retrieval: {error}" for error in errors],
                updated_at=updated_at,
                artifacts=[artifact] if artifact else [],
            )
        )

    direction_output = outputs.get("direction_review")
    if isinstance(direction_output, dict):
        review_status = str(direction_output.get("review_status") or "partial")
        round_read_count = int(direction_output.get("paper_count") or direction_output.get("round_read_count") or 0)
        direction_artifacts = [item for item in direction_output.get("artifacts", []) or [] if isinstance(item, dict)]
        steps.append(
            workflow_step_state(
                step_id="direction-review",
                status=direction_step_status(review_status, round_read_count),
                label="Direction Review",
                summary=(
                    f"{review_status}: {direction_output.get('relevant_read_count', round_read_count)} "
                    f"strong/medium readings; off-topic={direction_output.get('off_topic_count', 0)}"
                ),
                warnings=[str(error) for error in direction_output.get("errors", []) or []],
                updated_at=updated_at,
                artifacts=direction_artifacts[:3],
            )
        )

    memory_output = outputs.get("research_memory_query")
    if isinstance(memory_output, dict):
        warnings = [str(warning) for warning in memory_output.get("warnings", []) or []]
        artifact = memory_output.get("artifact") if isinstance(memory_output.get("artifact"), dict) else None
        hit_count = int(memory_output.get("hit_count") or memory_output.get("memory_hit_count") or 0)
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
        decision_status = str(decision_output.get("decision_status") or "partial")
        warnings = [str(warning) for warning in decision_output.get("warnings", []) or []]
        decision_artifacts = [item for item in decision_output.get("artifacts", []) or [] if isinstance(item, dict)]
        steps.append(
            workflow_step_state(
                step_id="gap-board",
                status=decision_status if decision_status in {"complete", "partial", "blocked"} else "partial",
                label="Gap Board",
                summary=(
                    f"{decision_status}: gap evidence="
                    f"{decision_output.get('evidence_quality', {}).get('gap_evidence_paper_count', 0) if isinstance(decision_output.get('evidence_quality'), dict) else 0}"
                ),
                warnings=warnings,
                updated_at=updated_at,
                artifacts=decision_artifacts[:2],
            )
        )
        experiment_status = str(decision_output.get("experiment_status") or "blocked")
        steps.append(
            workflow_step_state(
                step_id="experiment-planner",
                status=experiment_step_status(experiment_status),
                label="Experiment Plan",
                summary=(
                    "缺少可复现实验 anchor。"
                    if experiment_status == "blocked"
                    else f"实验 anchor：{decision_output.get('anchor_paper_title') or 'N/A'}。"
                ),
                warnings=warnings if experiment_status in {"blocked", "partial"} else [],
                updated_at=updated_at,
                artifacts=decision_artifacts[2:],
            )
        )

    return steps


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


TERMINAL_AGENT_RUN_STATUSES = {"completed", "completed_with_warnings", "partial", "failed", "cancelled"}


def serialize_artifact_refs(artifacts: list[dict]) -> list[dict[str, str]]:
    return [artifact_ref(artifact) for artifact in artifacts if isinstance(artifact, dict)]


def serialize_workflow_steps(steps: list[WorkflowStepState]) -> list[dict]:
    return [step.model_dump() for step in steps]


def current_agent_tool(plan: dict) -> str:
    for step in plan.get("steps", []) or []:
        if isinstance(step, dict) and step.get("status") == "running":
            return str(step.get("tool") or step.get("title") or "")
    for step in plan.get("steps", []) or []:
        if isinstance(step, dict) and step.get("status") == "queued":
            return str(step.get("tool") or step.get("title") or "")
    return ""


def persist_agent_run_progress(
    connection,
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
    run_summary = agent_run_summary(plan, outputs, len(papers), artifacts)
    workflow_steps = agent_workflow_steps(outputs, artifacts, updated_at)
    raw_warnings = [*(warnings or []), *[str(item) for item in run_summary["warnings"]]]
    merged_warnings = unique_strings(raw_warnings)
    current_tool = "" if status in TERMINAL_AGENT_RUN_STATUSES else current_agent_tool(plan)
    if run_status_summary is not None:
        summary_text = run_status_summary
    elif status == "running":
        summary_text = f"running: {current_tool or 'deterministic workflow'}."
    elif status == "failed":
        summary_text = "failed: Research Workflow Run stopped with an error."
    elif status == "cancelled":
        summary_text = "cancelled: Research Workflow Run stopped by user request."
    else:
        summary_text = str(run_summary["summary"])
    summary_metrics = collect_agent_summary_metrics(plan, len(papers))
    summary_metrics.update(build_warning_summary_metrics(raw_warnings))
    plan["summary_metrics"] = summary_metrics
    plan["warnings"] = merged_warnings
    plan["artifact_refs"] = serialize_artifact_refs(artifacts)
    plan["workflow_steps"] = serialize_workflow_steps(workflow_steps)
    plan["run_status_summary"] = summary_text
    plan["paper_count"] = len(papers)
    plan["current_tool"] = current_tool
    plan["queued_at"] = str(plan.get("queued_at") or plan.get("created_at") or updated_at)
    if status == "running" and not plan.get("started_at"):
        plan["started_at"] = updated_at
    if status in TERMINAL_AGENT_RUN_STATUSES:
        plan["completed_at"] = str(plan.get("completed_at") or updated_at)
    plan["last_heartbeat"] = updated_at
    plan["updated_at"] = updated_at
    if outputs:
        plan["tool_outputs"] = output_summary(outputs)
    if papers:
        plan["papers"] = papers

    connection.execute(
        workflow_sql("persist_agent_run_progress_1"),
        (
            status,
            json.dumps(plan, ensure_ascii=False, indent=2),
            result_artifact_id,
            updated_at,
            run_id,
        ),
    )
    connection.commit()


def fetch_agent_run_dict(connection, run_id: str) -> dict:
    run = connection.execute(
        workflow_sql("fetch_agent_run_dict_1"),
        (run_id,),
    ).fetchone()
    if run is None:
        raise HTTPException(status_code=404, detail="Research Workflow Run not found")
    return dict(run)


def parse_agent_plan(value: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def agent_status_response_from_run(connection, run_dict: dict) -> AgentRunStatusResponse:
    plan = parse_agent_plan(run_dict.get("plan_json", "{}"))
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    artifact = None
    result_artifact_id = run_dict.get("result_artifact_id")
    if result_artifact_id:
        artifact_dict = fetch_artifact_dict(connection, str(result_artifact_id))
        artifact = Artifact.model_validate(artifact_dict)

    artifact_refs_payload = plan.get("artifact_refs") if isinstance(plan.get("artifact_refs"), list) else []
    workflow_steps_payload = plan.get("workflow_steps") if isinstance(plan.get("workflow_steps"), list) else []
    papers_payload = plan.get("papers") if isinstance(plan.get("papers"), list) else []
    return AgentRunStatusResponse(
        run_id=str(run_dict["id"]),
        model_call=plan.get("model_call") if isinstance(plan.get("model_call"), dict) else None,
        status=str(run_dict["status"]),  # type: ignore[arg-type]
        steps=[step for step in steps if isinstance(step, dict)],
        summary_metrics=plan.get("summary_metrics") if isinstance(plan.get("summary_metrics"), dict) else {},
        warnings=[str(warning) for warning in plan.get("warnings", []) or []],
        artifact_refs=[ArtifactRef.model_validate(ref) for ref in artifact_refs_payload if isinstance(ref, dict)],
        workflow_steps=[
            WorkflowStepState.model_validate(step)
            for step in workflow_steps_payload
            if isinstance(step, dict)
        ],
        run_status_summary=str(plan.get("run_status_summary") or ""),
        current_tool=str(plan.get("current_tool") or current_agent_tool(plan)),
        papers=[paper for paper in papers_payload if isinstance(paper, dict)],
        paper_count=int(plan.get("paper_count") or infer_agent_paper_count(plan, plan.get("papers", []) if isinstance(plan.get("papers"), list) else [])),
        artifact=artifact,
        queued_at=str(plan.get("queued_at") or run_dict.get("created_at") or ""),
        started_at=str(plan.get("started_at") or ""),
        completed_at=str(plan.get("completed_at") or "") or None,
        last_heartbeat=str(plan.get("last_heartbeat") or run_dict.get("updated_at") or ""),
        updated_at=str(run_dict.get("updated_at") or ""),
    )


def execute_response_from_status(status: AgentRunStatusResponse) -> AgentExecuteResponse:
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


def is_agent_cancellation_requested(connection, run_id: str) -> bool:
    row = connection.execute(
        workflow_sql("is_agent_cancellation_requested_1"),
        (run_id,),
    ).fetchone()
    return bool(row and int(row["cancellation_requested"] or 0))


def mark_queued_agent_steps_cancelled(plan: dict) -> None:
    for step in plan.get("steps", []) or []:
        if isinstance(step, dict) and step.get("status") in {"queued", "running"}:
            step["status"] = "cancelled"


def run_agent_loop_background(run_id: str) -> None:
    try:
        run_agent_loop(run_id)
    except Exception as error:  # noqa: BLE001 - last-resort guard so background failures persist.
        try:
            with get_connection() as connection:
                run_dict = fetch_agent_run_dict(connection, run_id)
                plan = parse_agent_plan(run_dict["plan_json"])
                for step in plan.get("steps", []) or []:
                    if isinstance(step, dict) and step.get("status") == "running":
                        step["status"] = "failed"
                        break
                persist_agent_run_progress(
                    connection,
                    run_id,
                    plan,
                    "failed",
                    warnings=[f"Research Workflow Run failed: {error}"],
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


def run_agent_loop(run_id: str, execution=None) -> dict:
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        project = fetch_project_dict(connection, run_dict["project_id"])
        ensure_real_project_for_agent(project)
        plan = parse_agent_plan(run_dict["plan_json"])
        restored_papers = (
            [item for item in plan.get("papers", []) if isinstance(item, dict)]
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
            artifact = fetch_artifact_dict(connection, str(ref["id"]))
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
            item["name"] for item in registry.describe() if isinstance(item, dict)
        }
        steps = validate_workflow_plan(
            plan,
            registered_tools=registered_tools,
        )
        executable_steps = [
            step for step in steps if str(step.get("tool") or "") != "create_plan"
        ]

        for step in steps:
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool", ""))
            if step.get("status") == "done":
                continue
            if tool_name == "create_plan":
                step["status"] = "done"
                persist_agent_run_progress(connection, run_id, plan, "running")
                continue
            if execution is not None:
                execution.raise_if_cancelled()
            if is_agent_cancellation_requested(connection, run_id):
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
                    warnings=["Research Workflow Run cancelled by user request."],
                    run_status_summary="cancelled: stopped before the next tool step.",
                )
                insert_tool_event(
                    connection,
                    run_dict["session_id"],
                    "agent.cancel",
                    "cancelled",
                    "用户已取消 Research Workflow Run，后续 tool step 已停止。",
                    cancelled_at,
                )
                connection.commit()
                return {"run_id": run_id, "status": "cancelled"}
            if not registry.has(tool_name):
                fail_agent_run_step(
                    connection,
                    run_dict,
                    run_id,
                    plan,
                    step,
                    tool_name,
                    f"Workflow tool is not registered: {tool_name}",
                )
                return {"run_id": run_id, "status": "failed"}

            mark_plan_step_by_id(plan, str(step["id"]), "running")
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
                    item.get("status") == "done" for item in executable_steps
                )
                execution.checkpoint(
                    tool_name,
                    min(90, 10 + int(80 * completed_count / max(1, len(executable_steps)))),
                    {"step_id": str(step.get("id") or ""), "plan": plan},
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
                mark_plan_step_by_id(plan, str(step["id"]), "done", step_metrics)
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
                        item.get("status") == "done" for item in executable_steps
                    )
                    execution.checkpoint(
                        tool_name,
                        min(
                            95,
                            10
                            + int(
                                80
                                * completed_count
                                / max(1, len(executable_steps))
                            ),
                        ),
                        {"step_id": str(step.get("id") or ""), "plan": plan},
                    )
            except Exception as error:  # noqa: BLE001 - persist failed step for polling clients.
                if execution is not None:
                    mark_plan_step_by_id(plan, str(step["id"]), "queued")
                    persist_agent_run_progress(
                        connection,
                        run_id,
                        plan,
                        "running",
                        outputs=context.outputs,
                        papers=context.papers,
                        artifacts=context.artifacts,
                        warnings=[f"{tool_name} attempt failed and will be retried: {error}"],
                        run_status_summary=f"retrying: {tool_name} failed on this attempt.",
                    )
                    raise
                fail_agent_run_step(connection, run_dict, run_id, plan, step, tool_name, error)
                return {"run_id": run_id, "status": "failed"}

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
                warnings=["Research Workflow Run completed without a result artifact."],
                run_status_summary="failed: completed without a result artifact.",
            )
            return {"run_id": run_id, "status": "failed"}

        completed_at = utc_now()
        run_summary = agent_run_summary(plan, context.outputs, len(context.papers), context.artifacts)
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
            final_status if final_status != "completed_with_warnings" else "partial",
            str(run_summary["summary"]),
            completed_at,
        )
        connection.execute(
            workflow_sql("run_agent_loop_1"),
            ("workflow-run", completed_at, run_dict["project_id"]),
        )
        connection.commit()
        return {
            "run_id": run_id,
            "status": final_status,
            "artifact_id": context.artifact_id,
        }


def run_agent_job(job: DurableJob, execution) -> dict:
    return run_agent_loop(job.id, execution=execution)


def persist_durable_job_failure(job: DurableJob, error: object) -> None:
    if job.job_type == "direction_review":
        persist_direction_review_failure(job.id, job.project_id, error)
        return
    if job.job_type != "agent_run":
        return
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, job.id)
        plan = parse_agent_plan(run_dict["plan_json"])
        for step in plan.get("steps", []) or []:
            if isinstance(step, dict) and step.get("status") in {"running", "queued"}:
                step["status"] = "failed"
                break
        persist_agent_run_progress(
            connection,
            job.id,
            plan,
            "failed",
            warnings=[f"Research Workflow Run exhausted retries: {error}"],
            run_status_summary=f"failed after {job.attempts}/{job.max_attempts} attempts: {error}",
        )
        insert_tool_event(
            connection,
            str(run_dict["session_id"]),
            "agent.execute",
            "failed",
            str(error)[:500],
            utc_now(),
        )


def persist_durable_job_cancellation(job: DurableJob) -> None:
    if job.job_type == "direction_review":
        with get_connection() as connection:
            run = fetch_direction_review_run_dict(connection, job.project_id, job.id)
        persist_direction_review_run(
            job.id,
            status="cancelled",
            stage="cancelled",
            progress=int(run.get("progress") or 0),
            message="Direction Review 已取消；未执行后续工具阶段。",
            completed=True,
        )
        return
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
            warnings=["Research Workflow Run cancelled by durable worker request."],
            run_status_summary="cancelled: stopped at a durable tool boundary.",
        )

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


@router.get("/projects/{project_id}/papers", response_model=list[Paper])
def list_project_papers(project_id: str) -> list[Paper]:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            workflow_sql("list_project_papers_1"),
            (project_id,),
        ).fetchall()
    return [Paper.model_validate(dict(row)) for row in rows]


@router.post("/projects/{project_id}/literature/search", response_model=LiteratureSearchResponse)
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
            workflow_sql("search_project_literature_1"),
            ("literature-retrieval", completed_at, project_id),
        )
        rows = fetch_project_papers_by_ids(connection, project_id, paper_ids)

    return LiteratureSearchResponse(
        query=result.query,
        expanded_queries=result.expanded_queries,
        papers=[Paper.model_validate(dict(row)) for row in rows],
        artifact=Artifact.model_validate(artifact),
        errors=result.errors,
        relevance_coverage=result.relevance_coverage,
        workflow_steps=[
            workflow_step_state(
                step_id="paper-table",
                status=literature_step_status(len(rows), result.errors, result.relevance_coverage),
                label="Paper Table",
                summary=(
                    f"{result.relevance_coverage.get('candidate_count', len(rows))} candidates / "
                    f"{result.relevance_coverage.get('eligible_count', result.relevance_coverage.get('returned_count', len(rows)))} eligible / "
                    f"{result.relevance_coverage.get('returned_count', len(rows))} returned / "
                    f"{result.relevance_coverage.get('truncated_count', 0)} truncated / "
                    f"{result.relevance_coverage.get('off_topic_count', 0)} off-topic filtered"
                ),
                warnings=result.errors,
                updated_at=completed_at,
                artifacts=[artifact],
            ),
        ],
    )


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


@router.get("/projects/{project_id}/rag-index", response_model=ProjectRagIndexStatus)
def get_project_rag_index_status(project_id: str) -> ProjectRagIndexStatus:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        status = project_index_status(connection, project_id)
    return ProjectRagIndexStatus.model_validate(status)


@router.post(
    "/projects/{project_id}/rag-index/embeddings",
    response_model=RagEmbeddingStatus,
)
def embed_project_rag_index(
    project_id: str,
    payload: RagEmbeddingRequest,
) -> RagEmbeddingStatus:
    ensure_project_exists(project_id)
    try:
        provider = get_embedding_provider()
    except EmbeddingError as error:
        with get_connection() as connection:
            chunk_count = int(project_index_status(connection, project_id)["total_chunks"])
        return RagEmbeddingStatus(
            scope="project",
            project_id=project_id,
            status="failed",
            requested_chunks=chunk_count,
            failed_chunks=chunk_count,
            warnings=[str(error)],
        )
    with get_connection() as connection:
        run = embed_project_chunks(
            connection,
            project_id=project_id,
            force=payload.force,
            provider=provider,
        )
    return RagEmbeddingStatus(
        scope="project",
        project_id=project_id,
        **run.to_dict(),
    )


@router.post(
    "/projects/{project_id}/rag-search",
    response_model=RagSearchResponse,
)
def search_project_rag(
    project_id: str,
    payload: RagSearchRequest,
) -> RagSearchResponse:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        result = retrieve_project_chunks(
            connection,
            project_id=project_id,
            query=payload.query,
            top_k=payload.top_k,
            paper_ids=payload.paper_ids,
            evidence_levels=payload.evidence_levels,
            sections=payload.sections,
            min_score=payload.min_score,
            max_chunks_per_paper=payload.max_chunks_per_paper,
            refresh_embeddings=payload.refresh_embeddings,
        )
    return RagSearchResponse.model_validate(result)


@router.post(
    "/projects/{project_id}/rag-answer",
    response_model=RagAnswerResponse,
    status_code=201,
)
def create_project_rag_answer(
    project_id: str,
    payload: RagAnswerRequest,
) -> RagAnswerResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, now)
        insert_tool_event(
            connection,
            session_id,
            "rag.retrieve",
            "running",
            f"正在从项目原文索引检索最多 {payload.top_k} 个证据 chunk。",
            now,
        )
        answer = answer_project_rag(
            connection,
            project_id=project_id,
            question=payload.query,
            language=payload.language,
            top_k=payload.top_k,
            paper_ids=payload.paper_ids,
            evidence_levels=payload.evidence_levels,
            sections=payload.sections,
            min_score=payload.min_score,
            max_chunks_per_paper=payload.max_chunks_per_paper,
            refresh_embeddings=payload.refresh_embeddings,
        )
        evaluation = assess_rag_answer(
            answer,
            evaluation_id=new_id("rag_eval"),
            evaluated_at=now,
        )
        answer["quality_assessment"] = evaluation
        artifact_payload = {
            "schema_version": "rag_answer.v3",
            **answer,
        }
        artifact = insert_artifact_row(
            connection=connection,
            project_id=project_id,
            title=f"rag_answer_{paper_slug(payload.query)}.md",
            kind="markdown",
            content_markdown=render_rag_answer_markdown(answer),
            content_json=json.dumps(artifact_payload, ensure_ascii=False, indent=2),
            diff=(
                "+ Retrieved traceable paper chunks\n"
                "+ Recorded claim verification status and method\n"
                "+ Saved citation-grounded RAG answer"
            ),
            now=now,
        )
        answer["artifact"] = artifact
        insert_rag_evaluation(
            connection,
            project_id=project_id,
            answer_artifact_id=str(artifact["id"]),
            answer=answer,
            assessment=evaluation,
            created_at=now,
        )
        insert_tool_event(
            connection,
            session_id,
            "rag.retrieve",
            "done" if answer["citations"] else "partial",
            (
                f"返回 {len(answer['citations'])} 个可追溯引用；"
                f"状态 {answer['status']}。"
            ),
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "rag.answer",
            "done" if answer["claims"] else "partial",
            (
                f"记录 {len(answer['claims'])} 条带结构化验证状态的主张；"
                f"模式 {answer['answer_kind']}。"
            ),
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "rag.evaluate",
            "done",
            (
                "已完成自动证据质量检查；"
                f"状态 {evaluation['quality_status']}，"
                f"分数 {evaluation['score'] if evaluation['score'] is not None else 'not_scored'}。"
            ),
            now,
        )
    return RagAnswerResponse.model_validate(answer)


@router.get(
    "/projects/{project_id}/rag-evaluations",
    response_model=RagEvaluationListResponse,
)
def get_project_rag_evaluations(
    project_id: str,
    limit: int = 20,
) -> RagEvaluationListResponse:
    ensure_project_exists(project_id)
    safe_limit = max(1, min(100, limit))
    with get_connection() as connection:
        rows = list_rag_evaluations(
            connection,
            project_id=project_id,
            limit=safe_limit,
        )
        total_row = connection.execute(
            workflow_sql("get_project_rag_evaluations_1"),
            (project_id,),
        ).fetchone()
    return RagEvaluationListResponse(
        project_id=project_id,
        total=int(total_row["total"]) if total_row else 0,
        evaluations=[
            RagEvaluationRecord.model_validate(item)
            for item in rows
        ],
    )


@router.get(
    "/projects/{project_id}/papers/{paper_id}/rag-index",
    response_model=PaperChunkIndexStatus,
)
def get_paper_rag_index_status(project_id: str, paper_id: str) -> PaperChunkIndexStatus:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
        status = paper_index_status(connection, project_id, paper_id)
    return PaperChunkIndexStatus.model_validate(status)


@router.post(
    "/projects/{project_id}/papers/{paper_id}/rag-index/embeddings",
    response_model=RagEmbeddingStatus,
)
def embed_project_paper_rag_index(
    project_id: str,
    paper_id: str,
    payload: RagEmbeddingRequest,
) -> RagEmbeddingStatus:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
    try:
        provider = get_embedding_provider()
    except EmbeddingError as error:
        with get_connection() as connection:
            chunk_count = int(paper_index_status(connection, project_id, paper_id)["chunk_count"])
        return RagEmbeddingStatus(
            scope="paper",
            project_id=project_id,
            paper_id=paper_id,
            status="failed",
            requested_chunks=chunk_count,
            failed_chunks=chunk_count,
            warnings=[str(error)],
        )
    with get_connection() as connection:
        run = embed_project_chunks(
            connection,
            project_id=project_id,
            paper_id=paper_id,
            force=payload.force,
            provider=provider,
        )
    return RagEmbeddingStatus(
        scope="paper",
        project_id=project_id,
        paper_id=paper_id,
        **run.to_dict(),
    )


@router.get(
    "/projects/{project_id}/papers/{paper_id}/chunks",
    response_model=list[PaperChunk],
)
def list_project_paper_chunks(project_id: str, paper_id: str) -> list[PaperChunk]:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
        chunks = fetch_paper_chunks(connection, project_id, paper_id)
    return [PaperChunk.model_validate(chunk) for chunk in chunks]


@router.post(
    "/projects/{project_id}/papers/{paper_id}/rag-index",
    response_model=PaperChunkIndexStatus,
)
def rebuild_project_paper_rag_index(
    project_id: str,
    paper_id: str,
    payload: PaperChunkIndexRequest,
) -> PaperChunkIndexStatus:
    with get_connection() as connection:
        paper = fetch_paper_dict(connection, project_id, paper_id)
    result = provided_full_text(payload.paper_text) if payload.paper_text else resolve_open_full_text(paper)
    if not result.is_extracted:
        qualification = result.evidence_qualification(
            has_abstract=bool(str(paper.get("abstract") or "").strip()),
        )
        with get_connection() as connection:
            status = paper_index_status(
                connection,
                project_id,
                paper_id,
                message=(
                    f"全文索引未重建：{result.error or qualification.reason} "
                    "已有高等级索引未被删除。"
                ),
            )
        if status["status"] == "not_indexed":
            status["status"] = "failed"
        return PaperChunkIndexStatus.model_validate(status)

    now = utc_now()
    with get_connection() as connection:
        index_paper_full_text(
            connection,
            project_id=project_id,
            paper_id=paper_id,
            text=result.text,
            source_origin=result.source,
            now=now,
            evidence_verified=True,
        )
        status = paper_index_status(
            connection,
            project_id,
            paper_id,
            message="已从真实全文重建可追溯 chunk；embedding 尚未执行。",
        )
    return PaperChunkIndexStatus.model_validate(status)


@router.delete(
    "/projects/{project_id}/papers/{paper_id}/rag-index",
    response_model=PaperChunkIndexStatus,
)
def delete_project_paper_rag_index(project_id: str, paper_id: str) -> PaperChunkIndexStatus:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
        deleted_count = delete_paper_chunks(connection, project_id, paper_id)
        status = paper_index_status(
            connection,
            project_id,
            paper_id,
            message=f"已清除 {deleted_count} 个本地原文 chunk；论文、Paper Card 与 Memory 保持不变。",
        )
    return PaperChunkIndexStatus.model_validate(status)


def execute_project_direction_review(
    project_id: str,
    payload: DirectionReviewRequest,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> DirectionReviewResponse:
    def report(stage: str, progress: int, message: str) -> None:
        if progress_callback is not None:
            progress_callback(stage, progress, message)

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

    report("scoping", 10, f"已确认第 {payload.round} 轮方向范围，正在生成检索查询。")
    report("retrieving", 20, "正在从 arXiv 与 OpenAlex 检索、去重并按原始研究方向重排候选。")
    scope, candidate_pool, candidates, errors, relevance_coverage = retrieve_direction_candidate_pool(
        payload.direction,
        payload.round,
        previous_titles,
    )
    report(
        "reading",
        45,
        f"候选检索完成：{len(candidate_pool)} 条原始候选，{len(candidates)} 篇达到强/中相关阅读门槛；正在获取 PDF。",
    )
    papers_persisted_at = utc_now()
    artifacts: list[dict] = []
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, papers_persisted_at)
        paper_ids = insert_paper_candidates(connection, project_id, candidates, papers_persisted_at)
        paper_dicts = [fetch_paper_dict(connection, project_id, paper_id) for paper_id in paper_ids]

    reading_context_map = build_baseline_map(payload.direction, [], [])
    readings = build_direction_readings(paper_dicts, payload.direction, reading_context_map)
    full_text_count = sum(reading.full_text.get("status") == "extracted" for reading in readings)
    report(
        "curating",
        68,
        f"结构化阅读完成：{len(readings)} 篇中 {full_text_count} 篇具有已解析全文；正在校准 BaselineMap 与 ResearchSight。",
    )
    baseline_map = build_baseline_map(
        payload.direction,
        [candidate.to_dict() for candidate in candidate_pool],
        build_baseline_papers_from_readings(readings),
    )
    refresh_direction_reading_research_sights(readings, payload.direction, baseline_map)
    bundle = build_direction_review_bundle(
        payload.direction,
        payload.round,
        scope,
        baseline_map,
        readings,
        previous_read_count=len(previous_titles),
        errors=errors,
        relevance_coverage=relevance_coverage,
    )
    report("persisting", 82, "证据状态已计算，正在写入 Direction Review、Paper Card、BaselineMap 与 Memory artifacts。")
    completed_at = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, completed_at)
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
                content_markdown=render_card_markdown(reading.card, reading.paper, reading.full_text),
                content_json=json.dumps(reading.to_dict(), ensure_ascii=False, indent=2),
                diff="+ Generated direction-review paper card\n+ Added abstract translation for interactive UI",
                now=completed_at,
            )
            artifacts.append(card_artifact)
            connection.execute(
                workflow_sql("execute_project_direction_review_1"),
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
            if reading.source_text and reading.paper.get("id"):
                index_paper_full_text(
                    connection,
                    project_id=project_id,
                    paper_id=str(reading.paper["id"]),
                    text=reading.source_text,
                    source_origin=str(reading.full_text.get("source") or ""),
                    now=completed_at,
                    evidence_verified=bool(
                        (
                            reading.full_text.get("evidence_qualification")
                            if isinstance(
                                reading.full_text.get("evidence_qualification"),
                                dict,
                            )
                            else {}
                        ).get("verified")
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
                f"{bundle.review_status}：第 {payload.round} 轮仅筛选 {bundle.relevant_read_count}/10 篇强/中相关论文；off-topic={bundle.off_topic_count}。"
                if bundle.review_status != "complete"
                else f"第 {payload.round} 轮检索并筛选 {bundle.relevant_read_count} 篇近三年高相关论文。"
            ),
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "direction.read",
            "done" if readings else "queued",
            (
                f"{bundle.review_status}：已生成 {len(readings)} 张论文阅读卡片，低于可信完整综述阈值。"
                if bundle.review_status != "complete"
                else f"已生成 {len(readings)} 张 12 条规则论文精读卡片。"
            ),
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "baseline.curate",
            "done",
            f"已生成 BaselineMap：经典证据参照 {len(baseline_map.classic_baselines)} 篇，近三年直接候选 {len(baseline_map.recent_strong_baselines)} 篇，异质范式 {len(baseline_map.alternative_paradigms)} 篇。",
            completed_at,
        )
        insert_tool_event(
            connection,
            session_id,
            "direction.summarize",
            "done",
            (
                f"{bundle.review_status}：已生成临时方向总结；本轮仅 {bundle.relevant_read_count}/10 篇强/中相关论文，推荐需谨慎使用。"
                if bundle.review_status != "complete"
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
            workflow_sql("execute_project_direction_review_2"),
            ("direction-review", completed_at, project_id),
        )

    report("persisting", 96, f"已持久化 {len(artifacts)} 个 artifacts，正在生成最终运行状态。")
    return DirectionReviewResponse(
        direction=bundle.direction,
        round=bundle.round,
        review_status=bundle.review_status,
        target_paper_count=bundle.target_paper_count,
        round_read_count=len(bundle.readings),
        relevant_read_count=bundle.relevant_read_count,
        low_relevance_count=bundle.low_relevance_count,
        off_topic_count=bundle.off_topic_count,
        relevance_coverage=bundle.relevance_coverage,
        total_read_count=bundle.total_read_count,
        recommended_paper_ids=bundle.recommended_paper_ids,
        direction_summary=bundle.direction_summary,
        artifact_refs=make_artifact_refs(artifacts),
        errors=bundle.errors,
        workflow_steps=[
            workflow_step_state(
                step_id="direction-review",
                status=direction_step_status(bundle.review_status, len(bundle.readings)),
                label="Direction Review",
                summary=(
                    f"第 {bundle.round} 轮读取 {bundle.relevant_read_count}/{bundle.target_paper_count} 篇强/中相关论文；"
                    f"off-topic filtered={bundle.off_topic_count}；累计 {bundle.total_read_count} 篇。"
                ),
                warnings=bundle.errors,
                updated_at=completed_at,
                artifacts=artifacts,
            ),
        ],
    )


@router.post("/projects/{project_id}/direction-reviews", response_model=DirectionReviewResponse, status_code=201)
def create_project_direction_review(project_id: str, payload: DirectionReviewRequest) -> DirectionReviewResponse:
    """Compatibility endpoint for CLI and existing API clients.

    The web product uses the persisted async run endpoints below so it can show
    server-authored progress instead of a timer-based approximation.
    """

    return execute_project_direction_review(project_id, payload)


def parse_json_list(value: str) -> list[dict]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        parsed = []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def direction_review_run_response(run: dict) -> DirectionReviewRunStatusResponse:
    result = None
    if str(run.get("result_json") or "").strip():
        try:
            result = DirectionReviewResponse.model_validate(json.loads(str(run["result_json"])))
        except (json.JSONDecodeError, ValueError):
            result = None
    status = str(run["status"])
    stage = str(run["stage"])
    created_at = str(run["created_at"])
    updated_at = str(run["updated_at"])
    return DirectionReviewRunStatusResponse(
        run_id=str(run["id"]),
        project_id=str(run["project_id"]),
        direction=str(run["direction"]),
        round=int(run["round_index"]),
        status=status,  # type: ignore[arg-type]
        stage=stage,  # type: ignore[arg-type]
        progress=max(0, min(100, int(run["progress"] or 0))),
        message=str(run.get("message") or ""),
        notices=parse_json_list(str(run.get("notices_json") or "[]")),
        result=result,
        queued_at=created_at,
        started_at=str(run.get("started_at") or ""),
        current_tool=stage if status == "running" else "",
        last_heartbeat=updated_at,
        created_at=created_at,
        updated_at=updated_at,
        completed_at=str(run["completed_at"]) if run.get("completed_at") else None,
    )


def fetch_direction_review_run_dict(connection, project_id: str, run_id: str) -> dict:
    row = connection.execute(
        workflow_sql("fetch_direction_review_run_dict_1"),
        (run_id, project_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Direction Review run not found")
    return dict(row)


def persist_direction_review_run(
    run_id: str,
    *,
    status: str,
    stage: str,
    progress: int,
    message: str,
    notices: list[dict] | None = None,
    result: DirectionReviewResponse | None = None,
    completed: bool = False,
) -> None:
    updated_at = utc_now()
    with get_connection() as connection:
        row = connection.execute(
            workflow_sql("persist_direction_review_run_1"),
            (run_id,),
        ).fetchone()
        if row is None:
            return
        current_notices = parse_json_list(str(row["notices_json"] or "[]"))
        merged_notices = current_notices
        for notice in notices or []:
            identity = (str(notice.get("code") or ""), str(notice.get("message") or ""))
            if identity not in {
                (str(item.get("code") or ""), str(item.get("message") or ""))
                for item in merged_notices
            }:
                merged_notices.append(notice)
        connection.execute(
            workflow_sql("persist_direction_review_run_2"),
            (
                status,
                stage,
                max(0, min(100, int(progress))),
                message,
                json.dumps(merged_notices, ensure_ascii=False, indent=2),
                result.model_dump_json() if result is not None else None,
                updated_at,
                status,
                updated_at,
                1 if completed else 0,
                updated_at,
                run_id,
            ),
        )


def build_direction_review_run_notices(result: DirectionReviewResponse) -> list[dict]:
    occurred_at = utc_now()
    notices: list[dict] = [
        {
            "severity": "info",
            "code": "direction_review_evidence_summary",
            "stage": "completed",
            "message": (
                f"本轮保存 {result.relevant_read_count}/{result.target_paper_count} 篇强/中相关结构化阅读；"
                "候选覆盖不等于所有论文均已完成全文阅读。"
            ),
            "occurred_at": occurred_at,
        },
    ]
    for index, warning in enumerate(unique_strings(result.errors)):
        lower = warning.lower()
        severity = "error" if "blocked_direction_review" in lower else "warning"
        notices.append(
            {
                "severity": severity,
                "code": f"direction_review_source_{index + 1}",
                "stage": "completed",
                "message": warning,
                "occurred_at": occurred_at,
            },
        )
    if result.review_status == "partial":
        notices.append(
            {
                "severity": "warning",
                "code": "direction_review_partial",
                "stage": "completed",
                "message": (
                    f"Direction Review 仅部分完成：可靠阅读 {result.relevant_read_count}/"
                    f"{result.target_paper_count}，后续决策必须保留证据不足边界。"
                ),
                "occurred_at": occurred_at,
            },
        )
    elif result.review_status == "blocked":
        notices.append(
            {
                "severity": "error",
                "code": "direction_review_blocked",
                "stage": "completed",
                "message": "Direction Review 被证据门槛阻塞，不能视为已完成方向综述。",
                "occurred_at": occurred_at,
            },
        )
    return notices


def execute_direction_review_run(
    run_id: str,
    project_id: str,
    *,
    checkpoint_callback: Callable[[str, int, str], None] | None = None,
    cancellation_check: Callable[[], None] | None = None,
) -> dict:
    def report(stage: str, progress: int, message: str) -> None:
        if cancellation_check is not None:
            cancellation_check()
        persist_direction_review_run(
            run_id,
            status="running",
            stage=stage,
            progress=progress,
            message=message,
        )
        if checkpoint_callback is not None:
            checkpoint_callback(stage, progress, message)

    with get_connection() as connection:
        run = fetch_direction_review_run_dict(connection, project_id, run_id)
        if str(run["status"]) not in {"queued", "running"}:
            return {"status": str(run["status"])}
        payload = DirectionReviewRequest(
            direction=str(run["direction"]),
            round=int(run["round_index"]),
        )
    report("scoping", 5, "Direction Review worker 已领取任务，正在确认范围与历史已读论文。")
    result = execute_project_direction_review(project_id, payload, report)
    if cancellation_check is not None:
        cancellation_check()
    terminal_status = result.review_status
    terminal_message = {
        "complete": f"Direction Review 完成：可靠阅读 {result.relevant_read_count}/{result.target_paper_count} 篇。",
        "partial": f"Direction Review 部分完成：可靠阅读 {result.relevant_read_count}/{result.target_paper_count} 篇。",
        "blocked": "Direction Review 被证据门槛阻塞；结果已保留，但不能视为完成。",
    }[terminal_status]
    persist_direction_review_run(
        run_id,
        status=terminal_status,
        stage="completed",
        progress=100,
        message=terminal_message,
        notices=build_direction_review_run_notices(result),
        result=result,
        completed=True,
    )
    with get_connection() as connection:
        run = fetch_direction_review_run_dict(connection, project_id, run_id)
        insert_tool_event(
            connection,
            str(run["session_id"]),
            "direction.run",
            {"complete": "done", "partial": "partial", "blocked": "blocked"}[terminal_status],  # type: ignore[arg-type]
            terminal_message,
            utc_now(),
        )
    return {
        "run_id": run_id,
        "project_id": project_id,
        "status": terminal_status,
        "result": result.model_dump(),
    }


def run_direction_review_job(job: DurableJob, execution) -> dict:
    project_id = str(job.payload.get("project_id") or job.project_id)
    return execute_direction_review_run(
        job.id,
        project_id,
        checkpoint_callback=lambda stage, progress, message: execution.checkpoint(
            stage,
            progress,
            {"message": message},
        ),
        cancellation_check=execution.raise_if_cancelled,
    )


def persist_direction_review_failure(
    run_id: str,
    project_id: str,
    error: object,
) -> None:
    failed_at = utc_now()
    persist_direction_review_run(
        run_id,
        status="failed",
        stage="failed",
        progress=100,
        message=f"Direction Review 运行失败：{error}",
        notices=[
            {
                "severity": "error",
                "code": "direction_review_execution_failed",
                "stage": "failed",
                "message": str(error)[:500],
                "occurred_at": failed_at,
            },
        ],
        completed=True,
    )
    try:
        with get_connection() as connection:
            run = fetch_direction_review_run_dict(connection, project_id, run_id)
            insert_tool_event(
                connection,
                str(run["session_id"]),
                "direction.run",
                "failed",
                str(error)[:500],
                failed_at,
            )
    except Exception:
        return


def run_direction_review_background(run_id: str, project_id: str) -> None:
    """Synchronous compatibility helper; API requests never start this in a thread."""

    try:
        execute_direction_review_run(run_id, project_id)
    except Exception as error:  # noqa: BLE001 - compatibility calls expose failures.
        if isinstance(error, JobCancelled):
            raise
        persist_direction_review_failure(run_id, project_id, error)


@router.post(
    "/projects/{project_id}/direction-review-runs",
    response_model=DirectionReviewRunStatusResponse,
    status_code=202,
)
def start_project_direction_review_run(
    project_id: str,
    payload: DirectionReviewRequest,
) -> DirectionReviewRunStatusResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        if is_demo_project_dict(project):
            raise HTTPException(status_code=400, detail="Demo project cannot run Direction Review")
        active = connection.execute(
            workflow_sql("start_project_direction_review_run_1"),
            (project_id,),
        ).fetchone()
        if active is not None:
            active_dict = dict(active)
            if (
                str(active_dict["direction"]).strip() == payload.direction.strip()
                and int(active_dict["round_index"]) == payload.round
            ):
                return direction_review_run_response(active_dict)
            raise HTTPException(
                status_code=409,
                detail=(
                    "This project already has an active Direction Review run "
                    f"({active_dict['id']}, round {active_dict['round_index']})."
                ),
            )
        session_id = ensure_active_session(connection, project, now)
        run_id = new_id("direction_run")
        message = f"Direction Review 第 {payload.round} 轮已进入后端队列。"
        connection.execute(
            workflow_sql("start_project_direction_review_run_2"),
            (run_id, project_id, session_id, payload.direction.strip(), payload.round, message, now, now),
        )
        insert_tool_event(
            connection,
            session_id,
            "direction.run",
            "queued",
            message,
            now,
        )
        enqueue_job(
            job_id=run_id,
            project_id=project_id,
            session_id=session_id,
            job_type="direction_review",
            payload={
                "run_id": run_id,
                "project_id": project_id,
                "direction": payload.direction.strip(),
                "round": payload.round,
            },
            dedupe_key=f"direction_review:{run_id}",
            connection=connection,
        )

    with get_connection() as connection:
        return direction_review_run_response(fetch_direction_review_run_dict(connection, project_id, run_id))


@router.get(
    "/projects/{project_id}/direction-review-runs/latest",
    response_model=DirectionReviewRunStatusResponse | None,
)
def get_latest_project_direction_review_run(project_id: str) -> DirectionReviewRunStatusResponse | None:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        row = connection.execute(
            workflow_sql("get_latest_project_direction_review_run_1"),
            (project_id,),
        ).fetchone()
    return direction_review_run_response(dict(row)) if row is not None else None


@router.get(
    "/projects/{project_id}/direction-review-runs/{run_id}",
    response_model=DirectionReviewRunStatusResponse,
)
def get_project_direction_review_run(
    project_id: str,
    run_id: str,
) -> DirectionReviewRunStatusResponse:
    with get_connection() as connection:
        return direction_review_run_response(fetch_direction_review_run_dict(connection, project_id, run_id))


@router.post(
    "/projects/{project_id}/direction-review-runs/{run_id}/cancel",
    response_model=DirectionReviewRunStatusResponse,
)
def cancel_project_direction_review_run(
    project_id: str,
    run_id: str,
) -> DirectionReviewRunStatusResponse:
    with get_connection() as connection:
        current = fetch_direction_review_run_dict(connection, project_id, run_id)
    if str(current["status"]) in {
        "complete",
        "partial",
        "blocked",
        "failed",
        "cancelled",
    }:
        return direction_review_run_response(current)

    job = cancel_job(run_id)
    if job is None:
        raise HTTPException(status_code=409, detail="Direction Review job is missing")
    if job.status == "cancelled":
        persist_direction_review_run(
            run_id,
            status="cancelled",
            stage="cancelled",
            progress=int(current.get("progress") or 0),
            message="Direction Review 已在执行前取消。",
            completed=True,
        )
    else:
        persist_direction_review_run(
            run_id,
            status="running",
            stage=str(current["stage"]),
            progress=int(current.get("progress") or 0),
            message="已请求取消 Direction Review；worker 将在下一个工具阶段边界停止。",
        )
    with get_connection() as connection:
        return direction_review_run_response(
            fetch_direction_review_run_dict(connection, project_id, run_id)
        )


@router.post("/projects/{project_id}/research-decisions", response_model=ResearchDecisionResponse, status_code=201)
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
            f"已生成 {len(bundle.gaps)} 个 gap；decision_status={bundle.decision_status}。",
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "novelty.validate",
            "done",
            f"已生成 novelty risk={bundle.validation.novelty_risk} 的 idea validation report；证据质量={bundle.decision_status}。",
            now,
        )
        insert_tool_event(
            connection,
            session_id,
            "experiment.plan",
            "done" if bundle.experiment.status == "ready" else bundle.experiment.status,
            (
                "已生成包含目标对齐、baseline、dataset、metric、ablation 与资源就绪检查的实验计划。"
                if bundle.experiment.status == "ready"
                else "实验计划为 partial：科研锚点存在，但执行条件尚未全部确认。"
                if bundle.experiment.status == "partial"
                else "实验计划被阻塞：缺少满足目标约束的全文级可复现 anchor。"
            ),
            now,
        )
        connection.execute(
            workflow_sql("create_project_research_decisions_1"),
            ("experiment-planning", now, project_id),
        )

    return ResearchDecisionResponse(
        gaps=[gap.to_dict() for gap in bundle.gaps],
        validation=bundle.validation.to_dict(),
        experiment=bundle.experiment.to_dict(),
        artifacts=[Artifact.model_validate(artifact) for artifact in artifacts],
        decision_status=bundle.decision_status,  # type: ignore[arg-type]
        evidence_quality=bundle.evidence_quality,
        warnings=bundle.warnings,
        decision_intent=bundle.decision_intent.to_dict() if bundle.decision_intent else None,
        workflow_steps=[
            workflow_step_state(
                step_id="gap-board",
                status=bundle.decision_status if bundle.gaps else "partial",
                label="Gap Board",
                summary=(
                    f"{bundle.decision_status}：生成 {len(bundle.gaps)} 个 gap；"
                    f"gap evidence={bundle.evidence_quality.get('gap_evidence_paper_count', 0)}。"
                ),
                warnings=bundle.warnings or bundle.validation.key_risks,
                updated_at=now,
                artifacts=artifacts[:2],
            ),
            workflow_step_state(
                step_id="experiment-planner",
                status=experiment_step_status(bundle.experiment.status),
                label="Experiment Plan",
                summary=(
                    "缺少可复现实验 anchor。"
                    if bundle.experiment.status == "blocked"
                    else "科研锚点完整，但执行条件仍需补齐。"
                    if bundle.experiment.status == "partial"
                    else f"实验 anchor：{bundle.experiment.anchor_paper_title or 'N/A'}。"
                ),
                warnings=bundle.experiment.unblock_suggestions,
                updated_at=now,
                artifacts=artifacts[2:],
            ),
        ],
    )


@router.post("/projects/{project_id}/research-memory/query", response_model=ResearchMemoryQueryResponse, status_code=201)
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
            "done" if answer.hits else "queued",
            (
                f"已生成基于 {len(answer.hits)} 篇论文记忆的回答 artifact。"
                if answer.hits
                else "没有可靠记忆命中；已保存证据边界与下一步建议，未生成科研结论。"
            ),
            now,
        )
        connection.execute(
            workflow_sql("query_project_research_memory_1"),
            ("research-memory", now, project_id),
        )

    return ResearchMemoryQueryResponse(
        question=answer.question,
        top_k=answer.top_k,
        answer=answer.answer,
        hits=[to_paper_memory_hit(hit) for hit in answer.hits],
        direction_memory=to_direction_memory_response(answer.direction_memory) if answer.direction_memory else None,
        total_memories=answer.total_memories,
        reliability_status=answer.reliability_status,
        reliability_reason=answer.reliability_reason,
        answer_summary=answer.answer_summary,
        claims=[claim.to_dict() for claim in answer.claims],
        unanswered_parts=answer.unanswered_parts,
        query_coverage=answer.query_coverage,
        artifact=Artifact.model_validate(artifact),
        warnings=answer.warnings,
        workflow_steps=[
            workflow_step_state(
                step_id="paper-memory",
                status=memory_step_status(len(answer.hits), answer.warnings),
                label="Paper Memory",
                summary=f"命中 {len(answer.hits)} 篇论文记忆；memory bank 总量 {answer.total_memories}。",
                warnings=answer.warnings,
                updated_at=now,
                artifacts=[artifact],
            ),
        ],
    )


@router.post("/agent/plan", response_model=AgentPlanResponse, status_code=201)
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
            diff="+ Created Research Workflow Run plan artifact",
            now=now,
        )
        connection.execute(
            workflow_sql("create_agent_plan_1"),
            (
                run_id,
                payload.project_id,
                session_id,
                payload.task,
                draft.provider,
                "workflow",
                "planned",
                json.dumps(plan, ensure_ascii=False, indent=2),
                plan_artifact["id"],
                None,
                0,
                now,
                now,
            ),
        )
        if draft.model_call is None:
            raise RuntimeError("ModelProvider returned a plan without a model-call audit.")
        insert_model_call_audit(
            connection,
            project_id=payload.project_id,
            run_id=run_id,
            audit=draft.model_call.to_dict(),
        )
        insert_tool_event(
            connection,
            session_id,
            "agent.create_plan",
            "done",
            "已生成 Research Workflow Run 计划，并等待用户确认执行。",
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
            workflow_sql("create_agent_plan_2"),
            ("workflow-run", now, payload.project_id),
        )

    return AgentPlanResponse(
        run_id=run_id,
        project_id=payload.project_id,
        session_id=session_id,
        task=payload.task,
        provider=draft.provider,
        model_call=draft.model_call.to_dict(),
        status="planned",
        rationale=plan["rationale"],
        steps=plan["steps"],
        artifact=Artifact.model_validate(plan_artifact),
    )


@router.get("/agent/runs/{run_id}", response_model=AgentRunStatusResponse)
def get_agent_run_status(run_id: str) -> AgentRunStatusResponse:
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        return agent_status_response_from_run(connection, run_dict)


@router.post("/agent/runs/{run_id}/cancel", response_model=AgentRunStatusResponse)
def cancel_agent_run(run_id: str) -> AgentRunStatusResponse:
    cancelled_at = utc_now()
    should_cancel_job = False
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        plan = parse_agent_plan(run_dict["plan_json"])
        status = str(run_dict["status"])
        if status in TERMINAL_AGENT_RUN_STATUSES:
            return agent_status_response_from_run(connection, run_dict)
        if status == "planned":
            mark_queued_agent_steps_cancelled(plan)
            persist_agent_run_progress(
                connection,
                run_id,
                plan,
                "cancelled",
                warnings=["Research Workflow Run cancelled before execution."],
                run_status_summary="cancelled: stopped before execution.",
            )
        else:
            should_cancel_job = True
            connection.execute(
                workflow_sql("cancel_agent_run_1"),
                (1, cancelled_at, run_id),
            )
            plan["warnings"] = unique_strings([*(plan.get("warnings", []) or []), "Cancellation requested; current tool will finish before stopping."])
            plan["run_status_summary"] = "running: cancellation requested; waiting for current tool to finish."
            plan["updated_at"] = cancelled_at
            connection.execute(
                workflow_sql("cancel_agent_run_2"),
                (json.dumps(plan, ensure_ascii=False, indent=2), cancelled_at, run_id),
            )
        insert_tool_event(
            connection,
            run_dict["session_id"],
            "agent.cancel",
            "running" if status == "running" else "cancelled",
            (
                "已请求取消 Research Workflow Run；当前 tool 结束后会停止后续步骤。"
                if status == "running"
                else "已取消尚未开始执行的 Research Workflow Run。"
            ),
            cancelled_at,
        )
        connection.commit()
    if should_cancel_job:
        cancelled_job = cancel_job(run_id)
        if cancelled_job is not None and cancelled_job.status == "cancelled":
            persist_durable_job_cancellation(cancelled_job)
    with get_connection() as connection:
        return agent_status_response_from_run(
            connection,
            fetch_agent_run_dict(connection, run_id),
        )


@router.post("/agent/runs/{run_id}/execute", response_model=AgentExecuteResponse)
def execute_agent_run(run_id: str, payload: AgentExecuteRequest) -> AgentExecuteResponse:
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Research Workflow Run execution requires confirmation")

    now = utc_now()
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        project = fetch_project_dict(connection, run_dict["project_id"])
        ensure_real_project_for_agent(project)
        if str(run_dict["status"]) in {"running", *TERMINAL_AGENT_RUN_STATUSES}:
            return execute_response_from_status(agent_status_response_from_run(connection, run_dict))

        plan = parse_agent_plan(run_dict["plan_json"])

        connection.execute(
            workflow_sql("execute_agent_run_1"),
            ("running", 0, now, run_id),
        )
        insert_tool_event(
            connection,
            run_dict["session_id"],
            "agent.execute",
            "running",
            "Research Workflow Run 已启动；前端将通过轮询刷新 tool timeline、artifact 和 workflow steps。",
            now,
        )
        persist_agent_run_progress(connection, run_id, plan, "running")
        enqueue_job(
            job_id=run_id,
            project_id=str(run_dict["project_id"]),
            session_id=str(run_dict["session_id"]),
            job_type="agent_run",
            payload={"run_id": run_id},
            dedupe_key=f"agent_run:{run_id}",
            connection=connection,
        )
        run_dict = fetch_agent_run_dict(connection, run_id)

    with get_connection() as connection:
        return execute_response_from_status(agent_status_response_from_run(connection, fetch_agent_run_dict(connection, run_id)))


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
        paper_ids = insert_paper_candidates(connection, context.project["id"], result.papers, now)
        papers = fetch_project_papers_by_ids(connection, context.project["id"], paper_ids)
        artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_literature_search_{context.run_id}.md",
            kind="markdown",
            content_markdown=render_paper_table_markdown(result),
            content_json=render_paper_table_json(result),
            diff="+ Workflow tool literature_search\n+ Retrieved and persisted real paper candidates",
            now=now,
        )
        return ToolResult(
            tool="literature_search",
            status="done",
            summary=(
                f"已检索真实论文候选 {len(result.papers)} 篇；"
                f"{result.relevance_coverage.get('candidate_count', len(result.papers))} candidates / "
                f"{result.relevance_coverage.get('eligible_count', result.relevance_coverage.get('returned_count', len(papers)))} eligible / "
                f"{result.relevance_coverage.get('returned_count', len(papers))} returned / "
                f"{result.relevance_coverage.get('truncated_count', 0)} truncated / "
                f"{result.relevance_coverage.get('off_topic_count', 0)} off-topic filtered。"
            ),
            summary_metrics={
                "paper_count": len(papers),
                "artifact_count": 1,
                **build_warning_summary_metrics(result.errors),
                "relevance_coverage": result.relevance_coverage,
            },
            data={
                "papers": papers,
                "artifact_id": artifact["id"],
                "artifact": artifact,
                "paper_count": len(papers),
                "errors": result.errors,
                "relevance_coverage": result.relevance_coverage,
            },
        )

    def direction_review_tool(context: ToolContext) -> ToolResult:
        direction = infer_agent_direction(context)
        round_index = next_agent_direction_round(connection, context.project["id"])
        previous_titles = fetch_read_paper_titles(connection, context.project["id"]) if round_index > 1 else []
        scope, candidate_pool, candidates, errors, relevance_coverage = retrieve_direction_candidate_pool(
            direction,
            round_index,
            previous_titles,
        )
        now = utc_now()
        paper_ids = insert_paper_candidates(connection, context.project["id"], candidates, now)
        paper_dicts = [fetch_paper_dict(connection, context.project["id"], paper_id) for paper_id in paper_ids]
        reading_context_map = build_baseline_map(direction, [], [])
        readings = build_direction_readings(paper_dicts, direction, reading_context_map)
        baseline_map = build_baseline_map(
            direction,
            [candidate.to_dict() for candidate in candidate_pool],
            build_baseline_papers_from_readings(readings),
        )
        refresh_direction_reading_research_sights(readings, direction, baseline_map)
        bundle = build_direction_review_bundle(
            direction,
            round_index,
            scope,
            baseline_map,
            readings,
            previous_read_count=len(previous_titles),
            errors=errors,
            relevance_coverage=relevance_coverage,
        )
        artifacts: list[dict] = []
        baseline_artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_baseline_map_round_{round_index}_{paper_slug(direction)}.md",
            kind="markdown",
            content_markdown=render_baseline_map_markdown(baseline_map),
            content_json=json.dumps(baseline_map.to_dict(), ensure_ascii=False, indent=2),
            diff="+ Workflow tool direction_review\n+ Generated BaselineMap",
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
            diff="+ Workflow tool direction_review\n+ Generated direction review",
            now=now,
        )
        artifacts.append(review_artifact)

        for reading in readings:
            card_artifact = insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_direction_round_{round_index}_paper_card_{paper_slug(reading.card.paper_title)}.md",
                kind="markdown",
                content_markdown=render_card_markdown(reading.card, reading.paper, reading.full_text),
                content_json=json.dumps(reading.to_dict(), ensure_ascii=False, indent=2),
                diff="+ Workflow tool direction_review\n+ Generated direction-review paper card",
                now=now,
            )
            artifacts.append(card_artifact)
            connection.execute(
                workflow_sql("direction_review_tool_1"),
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
            if reading.source_text and reading.paper.get("id"):
                index_paper_full_text(
                    connection,
                    project_id=context.project["id"],
                    paper_id=str(reading.paper["id"]),
                    text=reading.source_text,
                    source_origin=str(reading.full_text.get("source") or ""),
                    now=now,
                    evidence_verified=bool(
                        (
                            reading.full_text.get("evidence_qualification")
                            if isinstance(
                                reading.full_text.get("evidence_qualification"),
                                dict,
                            )
                            else {}
                        ).get("verified")
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
            diff="+ Workflow tool direction_review\n+ Updated paper memory bank",
            now=now,
        )
        artifacts.append(memory_artifact)
        return ToolResult(
            tool="direction_review",
            status="done",
            summary=(
                f"{bundle.review_status}：第 {round_index} 轮生成 {len(readings)} 张 Paper Card；"
                f"strong/medium={bundle.relevant_read_count}, off-topic filtered={bundle.off_topic_count}。"
            ),
            summary_metrics={
                "review_status": bundle.review_status,
                "round_read_count": len(readings),
                "relevant_read_count": bundle.relevant_read_count,
                "low_relevance_count": bundle.low_relevance_count,
                "off_topic_count": bundle.off_topic_count,
                "total_read_count": bundle.total_read_count,
                "artifact_count": len(artifacts),
                "relevance_coverage": bundle.relevance_coverage,
                **build_warning_summary_metrics(bundle.errors),
            },
            data={
                "papers": paper_dicts,
                "artifacts": artifacts,
                "artifact_id": review_artifact["id"],
                "round": round_index,
                "paper_count": len(readings),
                "review_status": bundle.review_status,
                "round_read_count": len(readings),
                "relevant_read_count": bundle.relevant_read_count,
                "low_relevance_count": bundle.low_relevance_count,
                "off_topic_count": bundle.off_topic_count,
                "total_read_count": bundle.total_read_count,
                "relevance_coverage": bundle.relevance_coverage,
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
            diff="+ Workflow tool research_memory_query\n+ Retrieved paper memories",
            now=now,
        )
        return ToolResult(
            tool="research_memory_query",
            status="done",
            summary=f"已从 Paper Memory Bank 检索 {len(answer.hits)} 篇相关论文记忆。",
            summary_metrics={
                "memory_hit_count": len(answer.hits),
                "artifact_count": 1,
                **build_warning_summary_metrics(answer.warnings),
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
                diff="+ Workflow tool research_decision\n+ Generated gap board",
                now=now,
            ),
            insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_idea_validation_{context.run_id}.md",
                kind="markdown",
                content_markdown=render_validation_markdown(bundle),
                content_json=bundle_json,
                diff="+ Workflow tool research_decision\n+ Generated idea validation report",
                now=now,
            ),
            insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_experiment_plan_{context.run_id}.md",
                kind="markdown",
                content_markdown=render_experiment_markdown(bundle),
                content_json=bundle_json,
                diff="+ Workflow tool research_decision\n+ Generated experiment plan",
                now=now,
            ),
        ]
        return ToolResult(
            tool="research_decision",
            status="done",
            summary=(
                f"{bundle.decision_status}：已生成 {len(bundle.gaps)} 个 gap、"
                f"idea validation 和 experiment plan。"
            ),
            summary_metrics={
                "gap_count": len(bundle.gaps),
                "artifact_count": len(artifacts),
                "experiment_status": bundle.experiment.status,
                "decision_status": bundle.decision_status,
                "gap_evidence_paper_count": bundle.evidence_quality.get("gap_evidence_paper_count", 0),
                **build_warning_summary_metrics(bundle.warnings),
            },
            data={
                "artifacts": artifacts,
                "artifact_id": artifacts[-1]["id"],
                "gap_count": len(bundle.gaps),
                "experiment_status": bundle.experiment.status,
                "decision_status": bundle.decision_status,
                "evidence_quality": bundle.evidence_quality,
                "warnings": bundle.warnings,
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
            summary="已完成本次 Research Workflow Run，并同步 session timeline。",
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
