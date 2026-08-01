from __future__ import annotations

import json
from typing import Any

from scholarflow_api.agent_core import (
    ToolContext,
    ToolRegistry,
    ToolResult,
    build_mock_papers,
    render_execution_markdown,
)
from scholarflow_api.api_helpers import (
    artifact_ref,
    build_warning_summary_metrics,
    completed_plan_snapshot,
    fetch_paper_dict,
    fetch_project_paper_card_dicts,
    fetch_project_paper_dicts,
    fetch_project_papers_by_ids,
    fetch_read_paper_titles,
    infer_agent_direction,
    insert_artifact_row,
    insert_paper_candidates,
    next_agent_direction_round,
    output_summary,
)
from scholarflow_api.baseline_map import (
    build_baseline_map,
    render_baseline_map_markdown,
)
from scholarflow_api.database import new_id, utc_now
from scholarflow_api.direction_review import (
    build_baseline_papers_from_readings,
    build_direction_readings,
    build_direction_review_bundle,
    refresh_direction_reading_research_sights,
    render_direction_review_json,
    render_direction_review_markdown,
    retrieve_direction_candidate_pool,
)
from scholarflow_api.literature import (
    render_paper_table_json,
    render_paper_table_markdown,
    search_literature,
)
from scholarflow_api.paper_card import paper_slug, render_card_markdown
from scholarflow_api.rag_index import index_paper_full_text
from scholarflow_api.repositories.agent_run_repository import (
    insert_direction_review_paper_card,
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


def build_agent_tool_registry(connection: Any) -> ToolRegistry:
    registry = ToolRegistry()

    def create_plan_tool(context: ToolContext) -> ToolResult:
        return ToolResult(
            tool="create_plan",
            status="success",
            summary="Research Plan 已存在，继续等待或执行后续工具。",
        )

    def literature_search_tool(context: ToolContext) -> ToolResult:
        direction = infer_agent_direction(context)
        result = search_literature(
            direction,
            max_results=12,
            sources=["arxiv", "openalex"],
        )
        now = utc_now()
        paper_ids = insert_paper_candidates(
            connection,
            context.project["id"],
            result.papers,
            now,
        )
        papers = fetch_project_papers_by_ids(
            connection,
            context.project["id"],
            paper_ids,
        )
        artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_literature_search_{context.run_id}.md",
            kind="markdown",
            content_markdown=render_paper_table_markdown(result),
            content_json=render_paper_table_json(result),
            diff=(
                "+ Workflow tool literature_search\n"
                "+ Retrieved and persisted real paper candidates"
            ),
            now=now,
        )
        return ToolResult(
            tool="literature_search",
            status="success",
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
        round_index = next_agent_direction_round(
            connection,
            context.project["id"],
        )
        previous_titles = (
            fetch_read_paper_titles(connection, context.project["id"])
            if round_index > 1
            else []
        )
        (
            scope,
            candidate_pool,
            candidates,
            errors,
            relevance_coverage,
        ) = retrieve_direction_candidate_pool(
            direction,
            round_index,
            previous_titles,
        )
        now = utc_now()
        paper_ids = insert_paper_candidates(
            connection,
            context.project["id"],
            candidates,
            now,
        )
        paper_dicts = [
            fetch_paper_dict(
                connection,
                context.project["id"],
                paper_id,
            )
            for paper_id in paper_ids
        ]
        reading_context_map = build_baseline_map(direction, [], [])
        readings = build_direction_readings(
            paper_dicts,
            direction,
            reading_context_map,
        )
        baseline_map = build_baseline_map(
            direction,
            [candidate.to_dict() for candidate in candidate_pool],
            build_baseline_papers_from_readings(readings),
        )
        refresh_direction_reading_research_sights(
            readings,
            direction,
            baseline_map,
        )
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
            title=(
                f"agent_baseline_map_round_{round_index}_"
                f"{paper_slug(direction)}.md"
            ),
            kind="markdown",
            content_markdown=render_baseline_map_markdown(baseline_map),
            content_json=json.dumps(
                baseline_map.to_dict(),
                ensure_ascii=False,
                indent=2,
            ),
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
                title=(
                    f"agent_direction_round_{round_index}_paper_card_"
                    f"{paper_slug(reading.card.paper_title)}.md"
                ),
                kind="markdown",
                content_markdown=render_card_markdown(
                    reading.card,
                    reading.paper,
                    reading.full_text,
                ),
                content_json=json.dumps(
                    reading.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                ),
                diff=(
                    "+ Workflow tool direction_review\n"
                    "+ Generated direction-review paper card"
                ),
                now=now,
            )
            artifacts.append(card_artifact)
            insert_direction_review_paper_card(
                connection,
                card_id=new_id("paper_card"),
                project_id=context.project["id"],
                paper_id=reading.paper.get("id"),
                artifact_id=card_artifact["id"],
                sections_json=json.dumps(
                    [
                        section.to_dict()
                        for section in reading.card.sections
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                weakest_assumption=reading.card.weakest_assumption,
                minimal_reproduction=reading.card.minimal_reproduction,
                research_sight_json=json.dumps(
                    reading.research_sight.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                ),
                created_at=now,
            )
            if reading.source_text and reading.paper.get("id"):
                qualification = (
                    reading.full_text.get("evidence_qualification")
                    if isinstance(
                        reading.full_text.get("evidence_qualification"),
                        dict,
                    )
                    else {}
                )
                index_paper_full_text(
                    connection,
                    project_id=context.project["id"],
                    paper_id=str(reading.paper["id"]),
                    text=reading.source_text,
                    source_origin=str(
                        reading.full_text.get("source") or ""
                    ),
                    now=now,
                    evidence_verified=bool(
                        qualification.get("verified")
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
            content_json=json.dumps(
                direction_memory.to_dict(),
                ensure_ascii=False,
                indent=2,
            ),
            diff=(
                "+ Workflow tool direction_review\n"
                "+ Updated paper memory bank"
            ),
            now=now,
        )
        artifacts.append(memory_artifact)
        return ToolResult(
            tool="direction_review",
            status="success",
            summary=(
                f"{bundle.review_status}：第 {round_index} 轮生成 "
                f"{len(readings)} 张 Paper Card；"
                f"strong/medium={bundle.relevant_read_count}, "
                f"off-topic filtered={bundle.off_topic_count}。"
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
        artifact = insert_artifact_row(
            connection=connection,
            project_id=context.project["id"],
            title=f"agent_research_memory_answer_{context.run_id}.md",
            kind="markdown",
            content_markdown=render_research_memory_answer_markdown(answer),
            content_json=json.dumps(
                answer.to_dict(),
                ensure_ascii=False,
                indent=2,
            ),
            diff=(
                "+ Workflow tool research_memory_query\n"
                "+ Retrieved paper memories"
            ),
            now=now,
        )
        return ToolResult(
            tool="research_memory_query",
            status="success",
            summary=(
                "已从 Paper Memory Bank 检索 "
                f"{len(answer.hits)} 篇相关论文记忆。"
            ),
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
                "reliability_status": answer.reliability_status,
                "warnings": answer.warnings,
            },
        )

    def research_decision_tool(context: ToolContext) -> ToolResult:
        now = utc_now()
        papers = fetch_project_paper_dicts(
            connection,
            context.project["id"],
        )
        paper_cards = fetch_project_paper_card_dicts(
            connection,
            context.project["id"],
        )
        bundle = generate_research_decisions(
            context.project,
            papers,
            paper_cards,
            context.task,
        )
        bundle_json = render_decision_json(bundle)
        artifacts = [
            insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_gap_board_{context.run_id}.md",
                kind="markdown",
                content_markdown=render_gap_board_markdown(bundle),
                content_json=bundle_json,
                diff=(
                    "+ Workflow tool research_decision\n"
                    "+ Generated gap board"
                ),
                now=now,
            ),
            insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_idea_validation_{context.run_id}.md",
                kind="markdown",
                content_markdown=render_validation_markdown(bundle),
                content_json=bundle_json,
                diff=(
                    "+ Workflow tool research_decision\n"
                    "+ Generated idea validation report"
                ),
                now=now,
            ),
            insert_artifact_row(
                connection=connection,
                project_id=context.project["id"],
                title=f"agent_experiment_plan_{context.run_id}.md",
                kind="markdown",
                content_markdown=render_experiment_markdown(bundle),
                content_json=bundle_json,
                diff=(
                    "+ Workflow tool research_decision\n"
                    "+ Generated experiment plan"
                ),
                now=now,
            ),
        ]
        return ToolResult(
            tool="research_decision",
            status="success",
            summary=(
                f"{bundle.decision_status}：已生成 {len(bundle.gaps)} 个 "
                "gap、idea validation 和 experiment plan。"
            ),
            summary_metrics={
                "gap_count": len(bundle.gaps),
                "artifact_count": len(artifacts),
                "experiment_status": bundle.experiment.status,
                "decision_status": bundle.decision_status,
                "gap_evidence_paper_count": bundle.evidence_quality.get(
                    "gap_evidence_paper_count",
                    0,
                ),
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
            status="success",
            summary=f"已生成 {len(papers)} 条 mock paper candidates。",
            summary_metrics={
                "paper_count": len(papers),
                "demo_mode": True,
            },
            data={
                "papers": papers,
                "paper_count": len(papers),
                "demo_mode": True,
            },
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
                    "artifact_refs": [
                        artifact_ref(item)
                        for item in context.artifacts
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            diff=(
                "+ Executed registered research tools\n"
                "+ Saved agent run artifact"
            ),
            now=utc_now(),
        )
        return ToolResult(
            tool="save_artifact",
            status="success",
            summary=(
                "已保存 agent run artifact: "
                f"{artifact['title']}。"
            ),
            summary_metrics={
                "artifact_id": artifact["id"],
                "artifact_count": 1,
            },
            data={
                "artifact_id": artifact["id"],
                "artifact": artifact,
            },
        )

    def update_timeline_tool(context: ToolContext) -> ToolResult:
        return ToolResult(
            tool="update_timeline",
            status="success",
            summary=(
                "已完成本次 Bounded Research Agent，"
                "并同步 session timeline。"
            ),
            summary_metrics={
                "artifact_id": context.artifact_id or "",
            },
            data={"artifact_id": context.artifact_id},
        )

    registry.register(
        "create_plan",
        create_plan_tool,
        "Generate the confirmed research plan.",
    )
    registry.register(
        "literature_search",
        literature_search_tool,
        "Retrieve real paper candidates from literature sources.",
    )
    registry.register(
        "direction_review",
        direction_review_tool,
        "Run direction review, paper cards, baseline map, and memory writes.",
    )
    registry.register(
        "research_memory_query",
        research_memory_query_tool,
        "Retrieve relevant memories from Paper Memory Bank.",
    )
    registry.register(
        "research_decision",
        research_decision_tool,
        "Generate gap board, novelty validation, and experiment plan.",
    )
    registry.register(
        "search_mock_papers",
        search_mock_papers_tool,
        "Demo Mode: return local mock papers without external retrieval.",
    )
    registry.register(
        "save_artifact",
        save_artifact_tool,
        "Persist the agent output as Markdown and JSON.",
    )
    registry.register(
        "update_timeline",
        update_timeline_tool,
        "Finalize visible tool timeline state.",
    )
    return registry
