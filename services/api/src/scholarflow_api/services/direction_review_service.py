from __future__ import annotations

import json
from typing import Callable

from scholarflow_api.api_helpers import (
    ensure_active_session,
    ensure_project_exists,
    fetch_paper_dict,
    fetch_project_dict,
    fetch_read_paper_titles,
    insert_artifact_row,
    insert_paper_candidates,
)
from scholarflow_api.baseline_map import build_baseline_map, render_baseline_map_markdown
from scholarflow_api.database import get_connection, new_id, utc_now
from scholarflow_api.direction_review import (
    build_baseline_papers_from_readings,
    build_direction_readings,
    build_direction_review_bundle,
    refresh_direction_reading_research_sights,
    render_direction_review_json,
    render_direction_review_markdown,
    retrieve_direction_candidate_pool,
)
from scholarflow_api.jobs.models import DurableJob, JobCancelled
from scholarflow_api.jobs.repository import cancel_job, enqueue_job
from scholarflow_api.paper_card import (
    generate_deep_paper_card,
    paper_slug,
    render_card_json,
    render_card_markdown,
)
from scholarflow_api.research_memory import (
    upsert_direction_memory_snapshot,
    upsert_direction_reading_memories,
)
from scholarflow_api.rag_index import index_paper_full_text
from scholarflow_api.repositories.tool_event_repository import insert_tool_event
from scholarflow_api.repositories.direction_review_repository import (
    fetch_latest_run,
    fetch_run,
    fetch_run_notices,
    find_active_run,
    insert_direction_paper_card,
    insert_run,
    mark_direction_reviewed,
    update_run,
)
from scholarflow_api.schemas import (
    DirectionReviewRequest,
    DirectionReviewResponse,
    DirectionReviewRunStatusResponse,
)
from scholarflow_api.services.agent_plan_service import is_demo_project_dict
from scholarflow_api.services.errors import ServiceError
from scholarflow_api.services.workflow_response import (
    direction_step_status,
    make_artifact_refs,
    unique_strings,
    workflow_step_state,
)


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
            insert_direction_paper_card(
                connection,
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
        mark_direction_reviewed(connection, project_id, completed_at)

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
    row = fetch_run(connection, project_id, run_id)
    if row is None:
        raise ServiceError(status_code=404, detail="Direction Review run not found")
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
        row = fetch_run_notices(connection, run_id)
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
        update_run(
            connection,
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


def persist_direction_review_job_cancellation(job: DurableJob) -> None:
    with get_connection() as connection:
        run = fetch_direction_review_run_dict(
            connection,
            job.project_id,
            job.id,
        )
    persist_direction_review_run(
        job.id,
        status="cancelled",
        stage="cancelled",
        progress=int(run.get("progress") or 0),
        message="Direction Review 已取消；未执行后续工具阶段。",
        completed=True,
    )


def run_direction_review_background(run_id: str, project_id: str) -> None:
    """Synchronous compatibility helper; API requests never start this in a thread."""

    try:
        execute_direction_review_run(run_id, project_id)
    except Exception as error:  # noqa: BLE001 - compatibility calls expose failures.
        if isinstance(error, JobCancelled):
            raise
        persist_direction_review_failure(run_id, project_id, error)


def start_project_direction_review_run(
    project_id: str,
    payload: DirectionReviewRequest,
) -> DirectionReviewRunStatusResponse:
    now = utc_now()
    with get_connection() as connection:
        project = fetch_project_dict(connection, project_id)
        if is_demo_project_dict(project):
            raise ServiceError(status_code=400, detail="Demo project cannot run Direction Review")
        active = find_active_run(connection, project_id)
        if active is not None:
            active_dict = dict(active)
            if (
                str(active_dict["direction"]).strip() == payload.direction.strip()
                and int(active_dict["round_index"]) == payload.round
            ):
                return direction_review_run_response(active_dict)
            raise ServiceError(
                status_code=409,
                detail=(
                    "This project already has an active Direction Review run "
                    f"({active_dict['id']}, round {active_dict['round_index']})."
                ),
            )
        session_id = ensure_active_session(connection, project, now)
        run_id = new_id("direction_run")
        message = f"Direction Review 第 {payload.round} 轮已进入后端队列。"
        insert_run(
            connection,
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


def get_latest_project_direction_review_run(project_id: str) -> DirectionReviewRunStatusResponse | None:
    ensure_project_exists(project_id)
    with get_connection() as connection:
        row = fetch_latest_run(connection, project_id)
    return direction_review_run_response(dict(row)) if row is not None else None


def get_project_direction_review_run(
    project_id: str,
    run_id: str,
) -> DirectionReviewRunStatusResponse:
    with get_connection() as connection:
        return direction_review_run_response(fetch_direction_review_run_dict(connection, project_id, run_id))


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
        raise ServiceError(status_code=409, detail="Direction Review job is missing")
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
