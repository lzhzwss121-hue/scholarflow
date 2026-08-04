from __future__ import annotations

import json

from scholarflow_api.api_helpers import (
    ensure_active_session,
    fetch_project_dict,
    fetch_project_paper_card_dicts,
    fetch_project_paper_dicts,
    insert_artifact_row,
    to_direction_memory_response,
    to_paper_memory_hit,
)
from scholarflow_api.database import get_connection, utc_now
from scholarflow_api.paper_card import paper_slug
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
)
from scholarflow_api.repositories.research_decision_repository import update_project_stage
from scholarflow_api.repositories.tool_event_repository import insert_tool_event
from scholarflow_api.schemas import (
    Artifact,
    ResearchDecisionRequest,
    ResearchDecisionResponse,
    ResearchMemoryQueryRequest,
    ResearchMemoryQueryResponse,
)
from scholarflow_api.services.workflow_response import (
    experiment_step_status,
    memory_step_status,
    workflow_step_state,
)


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
        update_project_stage(connection, project_id, "experiment-planning", now)

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
        update_project_stage(connection, project_id, "research-memory", now)

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
