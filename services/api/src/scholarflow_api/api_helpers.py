from __future__ import annotations

import hashlib
import json
import re

from fastapi import HTTPException

from scholarflow_api.agent_core import ToolContext
from scholarflow_api.database import get_connection, new_id, row_to_dict, utc_now
from scholarflow_api.schemas import (
    BaselineMap,
    DirectionMemory,
    Paper,
    PaperCardCreateRequest,
    PaperMemoryHit,
    ResearchSight,
)

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


def fetch_project_papers_by_ids(connection, project_id: str, paper_ids: list[str]) -> list[dict]:
    if not paper_ids:
        return []
    placeholders = ",".join("?" for _ in paper_ids)
    rows = connection.execute(
        f"""
        SELECT * FROM papers
        WHERE project_id = ? AND id IN ({placeholders})
        ORDER BY
            CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
            relevance_score DESC,
            year DESC
        """,
        (project_id, *paper_ids),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_project_paper_card_dicts(connection, project_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            pc.*,
            p.title AS paper_title,
            p.authors AS paper_authors,
            p.abstract AS paper_abstract,
            p.year AS paper_year,
            p.type AS paper_type,
            p.venue AS paper_venue,
            p.source AS paper_source,
            p.url AS paper_url,
            p.pdf_url AS paper_pdf_url,
            p.relation AS paper_relation,
            p.priority AS paper_priority,
            p.code AS paper_code,
            p.relevance_score AS paper_relevance_score,
            p.relevance_quality AS paper_relevance_quality,
            p.matched_terms_json AS paper_matched_terms_json,
            p.review_required AS paper_review_required,
            a.content_json AS artifact_content_json
        FROM paper_cards pc
        LEFT JOIN papers p ON p.id = pc.paper_id
        LEFT JOIN artifacts a ON a.id = pc.artifact_id
        WHERE pc.project_id = ?
        ORDER BY pc.created_at DESC, pc.rowid DESC
        """,
        (project_id,),
    ).fetchall()
    return [enrich_paper_card_row(dict(row)) for row in rows]


def enrich_paper_card_row(row: dict) -> dict:
    payload = parse_json_object(row.pop("artifact_content_json", "") or "")
    card_payload = payload.get("card") if isinstance(payload.get("card"), dict) else payload
    signals = card_payload.get("signals") if isinstance(card_payload.get("signals"), dict) else payload.get("signals")
    sections = card_payload.get("sections") if isinstance(card_payload.get("sections"), list) else payload.get("sections")
    if isinstance(signals, dict):
        row["signals"] = signals
        row["signals_json"] = json.dumps(signals, ensure_ascii=False)
    if isinstance(sections, list) and sections:
        row["sections_json"] = json.dumps(sections, ensure_ascii=False)
    row["evidence_level"] = normalize_card_evidence_level(card_payload.get("evidence_level") or payload.get("evidence_level"))
    row["artifact_id"] = row.get("artifact_id") or payload.get("artifact_id") or ""
    return row


def parse_json_object(value: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_card_evidence_level(value) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"metadata_only", "abstract_only", "full_text"}:
        return normalized
    return "metadata_only"


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
        title_score=float(getattr(hit, "title_score", 0.0)),
        keyword_score=float(getattr(hit, "keyword_score", 0.0)),
        section_score=float(getattr(hit, "section_score", 0.0)),
        priority_score=float(getattr(hit, "priority_score", 0.0)),
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
        "evidence_pack": {
            "evidence_level": "",
            "confidence": "",
            "snippets": [],
            "missing_evidence": [],
            "grounding_summary": "",
        },
        "critique_evidence": [],
    }
    for key, value in defaults.items():
        if key == "evidence_pack":
            if isinstance(parsed.get(key), dict):
                defaults[key] = parsed[key]
            continue
        if key == "critique_evidence":
            if isinstance(parsed.get(key), list):
                defaults[key] = parsed[key]
            continue
        defaults[key] = str(parsed.get(key, value))
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
        "pdf_url": "",
        "relation": "用户提供内容生成的 Deep Paper Card。",
        "priority": "High",
        "code": "unknown",
        "relevance_score": 1.0,
        "relevance_quality": "strong",
        "matched_terms_json": "[]",
        "review_required": False,
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


def fail_agent_run_step(
    connection,
    run_dict: dict,
    run_id: str,
    plan: dict,
    step: dict,
    tool_name: str,
    error: object,
) -> None:
    error_message = error.detail if isinstance(error, HTTPException) else str(error)
    error_message = error_message or error.__class__.__name__
    failed_at = utc_now()
    mark_plan_step_by_id(plan, step.get("id", ""), "failed")
    connection.execute(
        """
        UPDATE agent_runs
        SET status = ?, plan_json = ?, updated_at = ?
        WHERE id = ?
        """,
        ("failed", json.dumps(plan, ensure_ascii=False, indent=2), failed_at, run_id),
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


def artifact_ref(artifact: dict) -> dict[str, str]:
    return {
        "id": str(artifact.get("id", "")),
        "title": str(artifact.get("title", "")),
        "kind": str(artifact.get("kind", "")),
        "created_at": str(artifact.get("created_at", "")),
    }


def summarize_literature_output(data: dict | None) -> dict[str, object]:
    data = data or {}
    return {
        "paper_count": data.get("paper_count", 0),
        "artifact_id": data.get("artifact_id", ""),
        "errors_count": len(data.get("errors", [])),
        "demo_mode": bool(data.get("demo_mode", False)),
    }


def summarize_direction_output(data: dict | None) -> dict[str, object]:
    data = data or {}
    return {
        "round": data.get("round", 0),
        "paper_count": data.get("paper_count", 0),
        "artifact_id": data.get("artifact_id", ""),
        "artifact_count": len(data.get("artifacts", [])),
        "recommended_paper_ids": data.get("recommended_paper_ids", []),
        "errors_count": len(data.get("errors", [])),
    }


def summarize_memory_output(data: dict | None) -> dict[str, object]:
    data = data or {}
    return {
        "hit_count": data.get("hit_count", 0),
        "total_memories": data.get("total_memories", 0),
        "artifact_id": data.get("artifact_id", ""),
        "warnings": data.get("warnings", []),
    }


def summarize_decision_output(data: dict | None) -> dict[str, object]:
    data = data or {}
    return {
        "gap_count": data.get("gap_count", 0),
        "artifact_id": data.get("artifact_id", ""),
        "experiment_status": data.get("experiment_status", ""),
        "anchor_paper_title": data.get("anchor_paper_title", ""),
        "experiment_claim": data.get("experiment_claim", ""),
    }


def output_summary(outputs: dict) -> dict[str, object]:
    return {
        "literature_search": summarize_literature_output(outputs.get("literature_search")),
        "direction_review": summarize_direction_output(outputs.get("direction_review")),
        "research_memory_query": summarize_memory_output(outputs.get("research_memory_query")),
        "research_decision": summarize_decision_output(outputs.get("research_decision")),
        "search_mock_papers": summarize_literature_output(outputs.get("search_mock_papers")),
    }


def insert_paper_candidates(connection, project_id: str, papers: list, now: str) -> list[str]:
    paper_ids: list[str] = []
    for paper in papers:
        paper_id = build_paper_id(project_id, paper.source, paper.title)
        paper_ids.append(paper_id)
        connection.execute(
            """
            INSERT INTO papers (
                id, project_id, title, authors, abstract, year, type, venue, source, url, pdf_url,
                relation, priority, code, relevance_score, relevance_quality, matched_terms_json,
                review_required, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                abstract = excluded.abstract,
                year = excluded.year,
                type = excluded.type,
                venue = excluded.venue,
                source = excluded.source,
                url = excluded.url,
                pdf_url = excluded.pdf_url,
                relation = excluded.relation,
                priority = excluded.priority,
                code = excluded.code,
                relevance_score = excluded.relevance_score,
                relevance_quality = excluded.relevance_quality,
                matched_terms_json = excluded.matched_terms_json,
                review_required = excluded.review_required
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
                getattr(paper, "pdf_url", ""),
                paper.relation,
                paper.priority,
                paper.code,
                paper.relevance_score,
                getattr(paper, "relevance_quality", "medium"),
                json.dumps(getattr(paper, "matched_terms", []) or [], ensure_ascii=False),
                1 if getattr(paper, "review_required", False) else 0,
                now,
            ),
        )
    return paper_ids


def build_paper_id(project_id: str, source: str, title: str) -> str:
    digest = hashlib.sha1(f"{project_id}:{source}:{title.lower()}".encode("utf-8")).hexdigest()[:16]
    return f"paper_{digest}"

def infer_agent_direction(context: ToolContext) -> str:
    candidates = [
        context.project.get("keyword", ""),
        context.project.get("field", ""),
        context.project.get("title", ""),
        context.task,
    ]
    for value in candidates:
        normalized = " ".join(str(value or "").split())
        if normalized:
            return normalized[:500]
    return "AI research reliability"


def next_agent_direction_round(connection, project_id: str) -> int:
    rows = connection.execute(
        """
        SELECT title FROM artifacts
        WHERE project_id = ?
          AND (title LIKE 'direction_review_round_%' OR title LIKE 'agent_direction_review_round_%')
        """,
        (project_id,),
    ).fetchall()
    rounds: list[int] = []
    for row in rows:
        title = dict(row).get("title", "")
        match = re.search(r"round_(\d+)", title)
        if match:
            rounds.append(int(match.group(1)))
    return min(max(rounds or [0]) + 1, 3)


def mark_plan_step(plan: dict, tool_name: str, status: str) -> None:
    for step in plan["steps"]:
        if step["tool"] == tool_name:
            step["status"] = status


def mark_plan_step_by_id(plan: dict, step_id: str, status: str, metrics: dict[str, object] | None = None) -> None:
    for step in plan["steps"]:
        if step.get("id") == step_id:
            step["status"] = status
            if metrics is not None:
                step["metrics"] = metrics
            return


def completed_plan_snapshot(plan: dict) -> dict:
    snapshot = json.loads(json.dumps(plan, ensure_ascii=False))
    for step in snapshot["steps"]:
        step["status"] = "done"
    return snapshot


def infer_tool_summary_metrics(data: dict | None) -> dict[str, object]:
    data = data or {}
    metrics: dict[str, object] = {}
    if "paper_count" in data:
        metrics["paper_count"] = int(data.get("paper_count") or 0)
    if "artifacts" in data and isinstance(data.get("artifacts"), list):
        metrics["artifact_count"] = len(data["artifacts"])
    elif data.get("artifact") or data.get("artifact_id"):
        metrics["artifact_count"] = 1
    warning_count = len(data.get("warnings", [])) + len(data.get("errors", []))
    if warning_count:
        metrics["warning_count"] = warning_count
    if "hit_count" in data:
        metrics["memory_hit_count"] = int(data.get("hit_count") or 0)
    if "experiment_status" in data:
        metrics["experiment_status"] = str(data.get("experiment_status") or "")
    if "review_status" in data:
        metrics["review_status"] = str(data.get("review_status") or "")
    if "total_read_count" in data:
        metrics["total_read_count"] = int(data.get("total_read_count") or 0)
    if "artifact_id" in data:
        metrics["artifact_id"] = str(data.get("artifact_id") or "")
    return metrics


def infer_agent_paper_count(plan: dict, papers: list[dict]) -> int:
    if papers:
        return len(papers)
    for step in plan.get("steps", []):
        metrics = step.get("metrics") if isinstance(step, dict) else None
        if isinstance(metrics, dict) and int(metrics.get("paper_count") or 0) > 0:
            return int(metrics["paper_count"])
    return 0


def collect_agent_summary_metrics(plan: dict, paper_count: int) -> dict[str, object]:
    summary: dict[str, object] = {
        "paper_count": paper_count,
        "artifact_count": 0,
        "warning_count": 0,
    }
    for step in plan.get("steps", []):
        metrics = step.get("metrics") if isinstance(step, dict) else None
        if not isinstance(metrics, dict):
            continue
        tool = str(step.get("tool", ""))
        if tool:
            summary[f"{tool}_metrics"] = metrics
        summary["artifact_count"] = int(summary["artifact_count"]) + int(metrics.get("artifact_count") or 0)
        summary["warning_count"] = int(summary["warning_count"]) + int(metrics.get("warning_count") or 0)
        if tool == "literature_search" and int(metrics.get("paper_count") or 0) > 0:
            summary["paper_count"] = int(metrics["paper_count"])
        if tool == "research_memory_query" and "memory_hit_count" in metrics:
            summary["memory_hit_count"] = int(metrics.get("memory_hit_count") or 0)
        if tool == "research_decision" and metrics.get("experiment_status"):
            summary["experiment_status"] = str(metrics["experiment_status"])
        if tool == "direction_review" and metrics.get("review_status"):
            summary["review_status"] = str(metrics["review_status"])
    return summary
