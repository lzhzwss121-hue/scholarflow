from __future__ import annotations

import json
from typing import Any

from scholarflow_api.agent_core import PlanRevision


def insert_plan_revision(connection: Any, revision: PlanRevision) -> PlanRevision:
    connection.execute(
        """
        INSERT INTO plan_revisions (
            id, parent_revision_id, run_id, trigger, reason,
            source_tool_result_id, previous_remaining_steps_json,
            revised_remaining_steps_json, skipped_steps_json,
            reordered_steps_json, retry_steps_json, plan_diff_json,
            validation_result_json, model_request_id,
            deterministic_fallback_reason, idempotency_key, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(idempotency_key) DO NOTHING
        """,
        (
            revision.revision_id,
            revision.parent_revision_id,
            revision.run_id,
            revision.trigger,
            revision.reason,
            revision.source_tool_result_id,
            _json(revision.previous_remaining_steps),
            _json(revision.revised_remaining_steps),
            _json(revision.skipped_steps),
            _json(revision.reordered_steps),
            _json(revision.retry_steps),
            _json(revision.plan_diff),
            _json(revision.validation_result),
            revision.model_request_id,
            revision.deterministic_fallback_reason,
            revision.idempotency_key,
            revision.created_at,
        ),
    )
    row = connection.execute(
        "SELECT * FROM plan_revisions WHERE idempotency_key = ?",
        (revision.idempotency_key,),
    ).fetchone()
    if row is None:
        raise RuntimeError("plan_revision_persistence_failed")
    return plan_revision_from_row(row)


def list_plan_revisions(connection: Any, run_id: str) -> list[PlanRevision]:
    rows = connection.execute(
        """
        SELECT * FROM plan_revisions
        WHERE run_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (run_id,),
    ).fetchall()
    return [plan_revision_from_row(row) for row in rows]


def latest_accepted_plan_revision(
    connection: Any,
    run_id: str,
) -> PlanRevision | None:
    rows = connection.execute(
        """
        SELECT * FROM plan_revisions
        WHERE run_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (run_id,),
    ).fetchall()
    for row in rows:
        revision = plan_revision_from_row(row)
        if revision.validation_result.get("status") == "accepted":
            return revision
    return None


def plan_revision_from_row(row: Any) -> PlanRevision:
    return PlanRevision(
        revision_id=str(row["id"]),
        parent_revision_id=(
            str(row["parent_revision_id"])
            if row["parent_revision_id"] is not None
            else None
        ),
        run_id=str(row["run_id"]),
        trigger=str(row["trigger"]),
        reason=str(row["reason"]),
        source_tool_result_id=(
            str(row["source_tool_result_id"])
            if row["source_tool_result_id"] is not None
            else None
        ),
        previous_remaining_steps=_json_list(row["previous_remaining_steps_json"]),
        revised_remaining_steps=_json_list(row["revised_remaining_steps_json"]),
        skipped_steps=_json_list(row["skipped_steps_json"]),
        reordered_steps=_json_list(row["reordered_steps_json"]),
        retry_steps=_json_list(row["retry_steps_json"]),
        created_at=str(row["created_at"]),
        validation_result=_json_object(row["validation_result_json"]),
        model_request_id=(
            str(row["model_request_id"])
            if row["model_request_id"] is not None
            else None
        ),
        deterministic_fallback_reason=str(
            row["deterministic_fallback_reason"] or ""
        ),
        plan_diff=_json_object(row["plan_diff_json"]),
        idempotency_key=str(row["idempotency_key"]),
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_list(value: object) -> list[dict[str, Any]]:
    parsed = json.loads(str(value or "[]"))
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _json_object(value: object) -> dict[str, Any]:
    parsed = json.loads(str(value or "{}"))
    return parsed if isinstance(parsed, dict) else {}
