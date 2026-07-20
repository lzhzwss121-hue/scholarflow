from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import hashlib
import json
import re
import threading

from fastapi import Body, FastAPI, HTTPException
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


def make_artifact_refs(artifacts: list[dict]) -> list[ArtifactRef]:
    return [ArtifactRef.model_validate(artifact_ref(artifact)) for artifact in artifacts]


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
            detail="Demo project is read-only preview. Create a real project before running Agent tools.",
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
    return "blocked" if status == "blocked" else "complete"


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
                warnings=warnings if experiment_status == "blocked" else [],
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
    merged_warnings = unique_strings([*(warnings or []), *[str(item) for item in run_summary["warnings"]]])
    current_tool = current_agent_tool(plan)
    if run_status_summary is not None:
        summary_text = run_status_summary
    elif status == "running":
        summary_text = f"running: {current_tool or 'agent loop'}."
    elif status == "failed":
        summary_text = "failed: Agent Run stopped with an error."
    elif status == "cancelled":
        summary_text = "cancelled: Agent Run stopped by user request."
    else:
        summary_text = str(run_summary["summary"])
    summary_metrics = collect_agent_summary_metrics(plan, len(papers))
    summary_metrics["warning_count"] = len(merged_warnings)
    plan["summary_metrics"] = summary_metrics
    plan["warnings"] = merged_warnings
    plan["artifact_refs"] = serialize_artifact_refs(artifacts)
    plan["workflow_steps"] = serialize_workflow_steps(workflow_steps)
    plan["run_status_summary"] = summary_text
    plan["paper_count"] = len(papers)
    plan["current_tool"] = current_tool
    plan["updated_at"] = updated_at
    if outputs:
        plan["tool_outputs"] = output_summary(outputs)
    if papers:
        plan["papers"] = papers

    connection.execute(
        """
        UPDATE agent_runs
        SET status = ?, plan_json = ?, result_artifact_id = COALESCE(?, result_artifact_id), updated_at = ?
        WHERE id = ?
        """,
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
        "SELECT * FROM agent_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
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
        updated_at=str(run_dict.get("updated_at") or ""),
    )


def execute_response_from_status(status: AgentRunStatusResponse) -> AgentExecuteResponse:
    return AgentExecuteResponse(
        run_id=status.run_id,
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
        updated_at=status.updated_at,
    )


def is_agent_cancellation_requested(connection, run_id: str) -> bool:
    row = connection.execute(
        "SELECT cancellation_requested FROM agent_runs WHERE id = ?",
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
                    warnings=[f"Agent Run failed: {error}"],
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


def run_agent_loop(run_id: str) -> None:
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        project = fetch_project_dict(connection, run_dict["project_id"])
        ensure_real_project_for_agent(project)
        plan = parse_agent_plan(run_dict["plan_json"])
        context = ToolContext(run_id=run_id, project=project, task=run_dict["task"], plan=plan)
        registry = build_agent_tool_registry(connection)

        for step in plan.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool", ""))
            if tool_name == "create_plan":
                step["status"] = "done"
                persist_agent_run_progress(connection, run_id, plan, "running")
                continue
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
                    warnings=["Agent Run cancelled by user request."],
                    run_status_summary="cancelled: stopped before the next tool step.",
                )
                insert_tool_event(
                    connection,
                    run_dict["session_id"],
                    "agent.cancel",
                    "cancelled",
                    "用户已取消 Agent Run，后续 tool step 已停止。",
                    cancelled_at,
                )
                connection.commit()
                return
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
                return

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
            except Exception as error:  # noqa: BLE001 - persist failed step for polling clients.
                fail_agent_run_step(connection, run_dict, run_id, plan, step, tool_name, error)
                return

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
                warnings=["Agent run completed without a result artifact."],
                run_status_summary="failed: completed without a result artifact.",
            )
            return

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
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            ("agent-loop", completed_at, run_dict["project_id"]),
        )
        connection.commit()

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
            ORDER BY CASE WHEN id = 'local-bootstrap' OR workflow = 'demo-preview' OR stage IN ('seed', 'demo') THEN 1 ELSE 0 END,
                     updated_at DESC,
                     created_at DESC
            """
        ).fetchall()
    return [Project.model_validate(project_response_dict(dict(row))) for row in rows]


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
    return Project.model_validate(project_response_dict(dict(row)))


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
    return Project.model_validate(project_response_dict(project))


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


@app.get("/projects/{project_id}/paper-cards", response_model=list[PaperCard])
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


@app.post("/projects/{project_id}/paper-cards", response_model=PaperCardResponse, status_code=201)
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
        card_text = payload.paper_text or (full_text.text if full_text.is_extracted else "")
        card = generate_deep_paper_card(paper, card_text)
        provenance = full_text.to_provenance()
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
        if payload.paper_id and full_text.is_extracted:
            index_paper_full_text(
                connection,
                project_id=project_id,
                paper_id=payload.paper_id,
                text=full_text.text,
                source_origin=full_text.source,
                now=now,
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
            paper_title=card.paper_title,
            artifact_id=artifact["id"],
            source_artifact_title=artifact["title"],
            card_source="paper_table" if payload.paper_id else "manual_unbound",
            evidence_level=card.evidence_level,
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


@app.post(
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
    generated = (
        persist_project_paper_card(
            project_id,
            PaperCardCreateRequest(paper_id=paper_id),
            result,
        )
        if result.is_extracted
        else None
    )
    updated_at = generated.card.updated_at if generated else utc_now()
    evidence_level = "full_text" if result.is_extracted else ("abstract_only" if paper.get("abstract") else "metadata_only")
    return PaperFullTextExtractResponse(
        paper_id=paper_id,
        text=result.text if result.is_extracted else "",
        evidence_level=evidence_level,
        evidence_quality=evidence_level,
        source=result.source,
        page_count=result.page_count,
        char_count=result.character_count,
        updated_at=updated_at,
        full_text=result.to_provenance(),
        card=generated.card if generated else None,
        artifact=generated.artifact if generated else None,
    )


@app.get("/projects/{project_id}/rag-index", response_model=ProjectRagIndexStatus)
def get_project_rag_index_status(project_id: str) -> ProjectRagIndexStatus:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        status = project_index_status(connection, project_id)
    return ProjectRagIndexStatus.model_validate(status)


@app.post(
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


@app.post(
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


@app.post(
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
            "schema_version": "rag_answer.v2",
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
                "+ Validated claim citation IDs\n"
                "+ Saved evidence-grounded RAG answer"
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
                f"生成 {len(answer['claims'])} 条通过引用校验的主张；"
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


@app.get(
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
            "SELECT COUNT(*) AS total FROM rag_evaluations WHERE project_id = ?",
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


@app.get(
    "/projects/{project_id}/papers/{paper_id}/rag-index",
    response_model=PaperChunkIndexStatus,
)
def get_paper_rag_index_status(project_id: str, paper_id: str) -> PaperChunkIndexStatus:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
        status = paper_index_status(connection, project_id, paper_id)
    return PaperChunkIndexStatus.model_validate(status)


@app.post(
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


@app.get(
    "/projects/{project_id}/papers/{paper_id}/chunks",
    response_model=list[PaperChunk],
)
def list_project_paper_chunks(project_id: str, paper_id: str) -> list[PaperChunk]:
    with get_connection() as connection:
        fetch_paper_dict(connection, project_id, paper_id)
        chunks = fetch_paper_chunks(connection, project_id, paper_id)
    return [PaperChunk.model_validate(chunk) for chunk in chunks]


@app.post(
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
        with get_connection() as connection:
            status = paper_index_status(
                connection,
                project_id,
                paper_id,
                message=(
                    f"全文索引未重建：{result.error or '输入文本没有达到全文证据阈值'} "
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
        )
        status = paper_index_status(
            connection,
            project_id,
            paper_id,
            message="已从真实全文重建可追溯 chunk；embedding 尚未执行。",
        )
    return PaperChunkIndexStatus.model_validate(status)


@app.delete(
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

    scope, candidate_pool, candidates, errors, relevance_coverage = retrieve_direction_candidate_pool(
        payload.direction,
        payload.round,
        previous_titles,
    )
    completed_at = utc_now()
    artifacts: list[dict] = []
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        session_id = ensure_active_session(connection, project, completed_at)
        paper_ids = insert_paper_candidates(connection, project_id, candidates, completed_at)
        paper_dicts = [fetch_paper_dict(connection, project_id, paper_id) for paper_id in paper_ids]
        reading_context_map = build_baseline_map(payload.direction, [], [])
        readings = build_direction_readings(paper_dicts, payload.direction, reading_context_map)
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
            if reading.source_text and reading.paper.get("id"):
                index_paper_full_text(
                    connection,
                    project_id=project_id,
                    paper_id=str(reading.paper["id"]),
                    text=reading.source_text,
                    source_origin=str(reading.full_text.get("source") or ""),
                    now=completed_at,
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
            "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
            ("direction-review", completed_at, project_id),
        )

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
            "done" if bundle.experiment.status == "ready" else "blocked",
            (
                "已生成包含目标对齐、baseline、dataset、metric、ablation 与资源就绪检查的实验计划。"
                if bundle.experiment.status == "ready"
                else "实验计划被阻塞：缺少满足目标约束的全文级可复现 anchor。"
            ),
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
                    else f"实验 anchor：{bundle.experiment.anchor_paper_title or 'N/A'}。"
                ),
                warnings=bundle.experiment.unblock_suggestions,
                updated_at=now,
                artifacts=artifacts[2:],
            ),
        ],
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
            "done" if answer.hits else "queued",
            (
                f"已生成基于 {len(answer.hits)} 篇论文记忆的回答 artifact。"
                if answer.hits
                else "没有可靠记忆命中；已保存证据边界与下一步建议，未生成科研结论。"
            ),
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


@app.get("/projects/{project_id}/artifacts", response_model=list[Artifact])
def list_project_artifacts(project_id: str) -> list[Artifact]:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM artifacts WHERE project_id = ? ORDER BY updated_at DESC, rowid DESC",
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
            ORDER BY updated_at DESC, rowid DESC
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
        ensure_real_project_for_agent(project)
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
                plan_json, plan_artifact_id, result_artifact_id, cancellation_requested, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                0,
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


@app.get("/agent/runs/{run_id}", response_model=AgentRunStatusResponse)
def get_agent_run_status(run_id: str) -> AgentRunStatusResponse:
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        return agent_status_response_from_run(connection, run_dict)


@app.post("/agent/runs/{run_id}/cancel", response_model=AgentRunStatusResponse)
def cancel_agent_run(run_id: str) -> AgentRunStatusResponse:
    cancelled_at = utc_now()
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
                warnings=["Agent Run cancelled before execution."],
                run_status_summary="cancelled: stopped before execution.",
            )
        else:
            connection.execute(
                "UPDATE agent_runs SET cancellation_requested = ?, updated_at = ? WHERE id = ?",
                (1, cancelled_at, run_id),
            )
            plan["warnings"] = unique_strings([*(plan.get("warnings", []) or []), "Cancellation requested; current tool will finish before stopping."])
            plan["run_status_summary"] = "running: cancellation requested; waiting for current tool to finish."
            plan["updated_at"] = cancelled_at
            connection.execute(
                "UPDATE agent_runs SET plan_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(plan, ensure_ascii=False, indent=2), cancelled_at, run_id),
            )
        insert_tool_event(
            connection,
            run_dict["session_id"],
            "agent.cancel",
            "running" if status == "running" else "cancelled",
            (
                "已请求取消 Agent Run；当前 tool 结束后会停止后续步骤。"
                if status == "running"
                else "已取消尚未开始执行的 Agent Run。"
            ),
            cancelled_at,
        )
        connection.commit()
        return agent_status_response_from_run(connection, fetch_agent_run_dict(connection, run_id))


@app.post("/agent/runs/{run_id}/execute", response_model=AgentExecuteResponse)
def execute_agent_run(run_id: str, payload: AgentExecuteRequest) -> AgentExecuteResponse:
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Agent run execution requires confirmation")

    now = utc_now()
    with get_connection() as connection:
        run_dict = fetch_agent_run_dict(connection, run_id)
        project = fetch_project_dict(connection, run_dict["project_id"])
        ensure_real_project_for_agent(project)
        if str(run_dict["status"]) in {"running", *TERMINAL_AGENT_RUN_STATUSES}:
            return execute_response_from_status(agent_status_response_from_run(connection, run_dict))

        plan = parse_agent_plan(run_dict["plan_json"])

        connection.execute(
            "UPDATE agent_runs SET status = ?, cancellation_requested = ?, updated_at = ? WHERE id = ?",
            ("running", 0, now, run_id),
        )
        insert_tool_event(
            connection,
            run_dict["session_id"],
            "agent.execute",
            "running",
            "Agent Run 已启动；前端将通过轮询刷新 tool timeline、artifact 和 workflow steps。",
            now,
        )
        persist_agent_run_progress(connection, run_id, plan, "running")
        run_dict = fetch_agent_run_dict(connection, run_id)

    threading.Thread(target=run_agent_loop_background, args=(run_id,), daemon=True).start()
    with get_connection() as connection:
        return execute_response_from_status(agent_status_response_from_run(connection, fetch_agent_run_dict(connection, run_id)))


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
                "warning_count": len(result.errors),
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
                content_markdown=render_card_markdown(reading.card, reading.paper, reading.full_text),
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
            if reading.source_text and reading.paper.get("id"):
                index_paper_full_text(
                    connection,
                    project_id=context.project["id"],
                    paper_id=str(reading.paper["id"]),
                    text=reading.source_text,
                    source_origin=str(reading.full_text.get("source") or ""),
                    now=now,
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
                "warning_count": len(bundle.warnings),
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
