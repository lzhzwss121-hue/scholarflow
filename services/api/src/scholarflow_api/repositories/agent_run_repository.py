from __future__ import annotations

import json
from typing import Any

from scholarflow_api.database import new_id, utc_now


def insert_agent_run(
    connection: Any,
    *,
    run_id: str,
    project_id: str,
    session_id: str,
    task: str,
    provider: str,
    plan: dict[str, Any],
    plan_artifact_id: str,
    now: str,
) -> None:
    connection.execute(
        """
        INSERT INTO agent_runs (
            id, project_id, session_id, task, provider, mode, status,
            plan_json, plan_artifact_id, result_artifact_id,
            cancellation_requested, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            project_id,
            session_id,
            task,
            provider,
            "workflow",
            "planned",
            json.dumps(plan, ensure_ascii=False, indent=2),
            plan_artifact_id,
            None,
            0,
            now,
            now,
        ),
    )


def fetch_agent_run(connection: Any, run_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM agent_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def update_agent_run_progress(
    connection: Any,
    *,
    run_id: str,
    status: str,
    plan: dict[str, Any],
    result_artifact_id: str | None,
    updated_at: str,
) -> None:
    connection.execute(
        """
        UPDATE agent_runs
        SET status = ?, plan_json = ?,
            result_artifact_id = COALESCE(?, result_artifact_id),
            updated_at = ?
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


def agent_cancellation_requested(connection: Any, run_id: str) -> bool:
    row = connection.execute(
        "SELECT cancellation_requested FROM agent_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    return bool(row and int(row["cancellation_requested"] or 0))


def request_agent_cancellation(
    connection: Any,
    *,
    run_id: str,
    requested_at: str,
) -> None:
    connection.execute(
        """
        UPDATE agent_runs
        SET cancellation_requested = 1, updated_at = ?
        WHERE id = ?
        """,
        (requested_at, run_id),
    )


def update_agent_plan(
    connection: Any,
    *,
    run_id: str,
    plan: dict[str, Any],
    updated_at: str,
) -> None:
    connection.execute(
        """
        UPDATE agent_runs
        SET plan_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            json.dumps(plan, ensure_ascii=False, indent=2),
            updated_at,
            run_id,
        ),
    )


def mark_agent_run_running(
    connection: Any,
    *,
    run_id: str,
    started_at: str,
) -> None:
    connection.execute(
        """
        UPDATE agent_runs
        SET status = 'running', cancellation_requested = 0, updated_at = ?
        WHERE id = ?
        """,
        (started_at, run_id),
    )


def update_project_stage(
    connection: Any,
    *,
    project_id: str,
    stage: str,
    updated_at: str,
) -> None:
    connection.execute(
        "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
        (stage, updated_at, project_id),
    )


def insert_model_call_audit(
    connection: Any,
    *,
    project_id: str,
    run_id: str,
    audit: dict[str, Any],
) -> str:
    safe_fields = {
        "provider": str(audit.get("provider") or "local"),
        "model": str(audit.get("model") or ""),
        "purpose": str(audit.get("purpose") or ""),
        "prompt_version": str(audit.get("prompt_version") or ""),
        "request_timestamp": str(
            audit.get("request_timestamp") or utc_now()
        ),
        "latency_ms": max(0, int(audit.get("latency_ms") or 0)),
        "response_status": str(audit.get("response_status") or "unknown"),
        "fallback_reason": str(audit.get("fallback_reason") or ""),
        "requested_provider": str(audit.get("requested_provider") or ""),
        "requested_model": str(audit.get("requested_model") or ""),
        "external_data_sent": int(bool(audit.get("external_data_sent"))),
        "prompt_tokens": max(0, int(audit.get("prompt_tokens") or 0)),
        "completion_tokens": max(0, int(audit.get("completion_tokens") or 0)),
        "total_tokens": max(0, int(audit.get("total_tokens") or 0)),
    }
    audit_id = new_id("model_call")
    connection.execute(
        """
        INSERT INTO model_call_audits (
            id, project_id, run_id, provider, model, purpose, prompt_version,
            request_timestamp, latency_ms, response_status, fallback_reason,
            requested_provider, requested_model, external_data_sent,
            prompt_tokens, completion_tokens, total_tokens, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit_id,
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
            safe_fields["prompt_tokens"],
            safe_fields["completion_tokens"],
            safe_fields["total_tokens"],
            utc_now(),
        ),
    )
    return audit_id


def insert_direction_review_paper_card(
    connection: Any,
    *,
    card_id: str,
    project_id: str,
    paper_id: str | None,
    artifact_id: str,
    sections_json: str,
    weakest_assumption: str,
    minimal_reproduction: str,
    research_sight_json: str,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO paper_cards (
            id, project_id, paper_id, artifact_id, sections_json,
            weakest_assumption, minimal_reproduction,
            research_sight_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            card_id,
            project_id,
            paper_id,
            artifact_id,
            sections_json,
            weakest_assumption,
            minimal_reproduction,
            research_sight_json,
            created_at,
        ),
    )
