from __future__ import annotations

import hashlib
import json
from typing import Any

from scholarflow_api.agent_core import (
    AgentBudgets,
    PlanRevision,
    PlanRevisionCandidate,
)
from scholarflow_api.database import new_id, utc_now


REMAINING_STEP_STATUSES = {"queued", "running"}


def remaining_plan_steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _step_snapshot(step)
        for step in plan.get("steps", []) or []
        if isinstance(step, dict)
        and str(step.get("status") or "queued") in REMAINING_STEP_STATUSES
    ]


def deterministic_revision_candidate(
    previous_remaining_steps: list[dict[str, Any]],
    *,
    reason: str,
    preferred_tool: str = "",
    source_tool: str = "",
    fallback_reason: str,
) -> PlanRevisionCandidate:
    step_ids = [str(step.get("id") or "") for step in previous_remaining_steps]
    step_ids = [step_id for step_id in step_ids if step_id]
    by_tool = {
        str(step.get("tool") or ""): str(step.get("id") or "")
        for step in previous_remaining_steps
    }
    preferred_id = by_tool.get(preferred_tool, "")
    source_id = by_tool.get(source_tool, "")
    revised = list(step_ids)
    if preferred_id and preferred_id in revised:
        revised.remove(preferred_id)
        revised.insert(0, preferred_id)
    if source_id and source_id in revised and len(revised) > 1:
        revised.remove(source_id)
        revised.append(source_id)
    if revised == step_ids and len(revised) > 1:
        revised = revised[1:] + revised[:1]
    return PlanRevisionCandidate(
        reason=reason[:1000],
        revised_remaining_step_ids=revised,
        retry_step_ids=[source_id] if source_id else [],
        deterministic_fallback_reason=fallback_reason,
    )


def build_plan_revision(
    *,
    run_id: str,
    plan: dict[str, Any],
    candidate: PlanRevisionCandidate,
    trigger: str,
    source_tool_result_id: str | None,
    model_request_id: str | None,
    registered_tools: set[str],
    budgets: AgentBudgets,
    revision_attempts: int,
    previous_fingerprints: set[str],
) -> PlanRevision:
    previous = remaining_plan_steps(plan)
    by_id = {str(step.get("id") or ""): step for step in previous}
    previous_ids = list(by_id)
    revised_ids = list(candidate.revised_remaining_step_ids)
    skipped_ids = list(candidate.skipped_step_ids)
    retry_ids = list(candidate.retry_step_ids)
    reasons: list[str] = []

    if revision_attempts >= budgets.max_replans:
        reasons.append("max_plan_revisions_budget_reached")
    if not previous_ids:
        reasons.append("no_remaining_steps")
    supplied_ids = revised_ids + skipped_ids
    if len(supplied_ids) != len(set(supplied_ids)):
        reasons.append("duplicate_step_id")
    if set(supplied_ids) != set(previous_ids):
        reasons.append("revision_must_account_for_exact_remaining_steps")
    if not set(retry_ids).issubset(set(revised_ids)):
        reasons.append("retry_steps_must_remain_in_plan")
    if any(str(by_id.get(step_id, {}).get("tool") or "") not in registered_tools for step_id in revised_ids):
        reasons.append("unregistered_tool")
    steps_remaining = max(0, budgets.max_steps - _steps_executed(plan))
    added_steps = max(0, len(supplied_ids) - len(previous_ids))
    if added_steps > steps_remaining:
        reasons.append("revision_exceeds_step_budget")

    revised_fingerprint = _fingerprint(revised_ids, skipped_ids, retry_ids)
    current_fingerprint = _fingerprint(previous_ids, [], [])
    if revised_fingerprint == current_fingerprint:
        reasons.append("revision_has_no_effect")
    if revised_fingerprint in previous_fingerprints:
        reasons.append("revision_cycle_detected")

    revised_steps = [by_id[step_id] for step_id in revised_ids if step_id in by_id]
    skipped_steps = [by_id[step_id] for step_id in skipped_ids if step_id in by_id]
    retry_steps = [by_id[step_id] for step_id in retry_ids if step_id in by_id]
    previous_positions = {step_id: index for index, step_id in enumerate(previous_ids)}
    reordered = [
        {
            "step_id": step_id,
            "tool": str(by_id[step_id].get("tool") or ""),
            "from_index": previous_positions[step_id],
            "to_index": index,
        }
        for index, step_id in enumerate(revised_ids)
        if step_id in previous_positions and previous_positions[step_id] != index
    ]
    status = "rejected" if reasons else "accepted"
    validation_result = {
        "status": status,
        "reasons": reasons,
        "validator": "deterministic-plan-revision.v1",
    }
    plan_diff = {
        "previous_order": previous_ids,
        "revised_order": revised_ids,
        "skipped_step_ids": skipped_ids,
        "retry_step_ids": retry_ids,
        "reordered_steps": reordered,
    }
    parent_revision_id = str(
        (plan.get("bounded_agent") or {}).get("active_revision_id") or ""
    ) or None
    idempotency_key = hashlib.sha256(
        json.dumps(
            {
                "run_id": run_id,
                "parent_revision_id": parent_revision_id,
                "trigger": trigger,
                "source_tool_result_id": source_tool_result_id,
                "candidate": candidate.to_dict() | {"audit": None},
                "validation": validation_result,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return PlanRevision(
        revision_id=new_id("revision"),
        parent_revision_id=parent_revision_id,
        run_id=run_id,
        trigger=trigger[:200],
        reason=candidate.reason[:1000],
        source_tool_result_id=source_tool_result_id,
        previous_remaining_steps=previous,
        revised_remaining_steps=revised_steps,
        skipped_steps=skipped_steps,
        reordered_steps=reordered,
        retry_steps=retry_steps,
        created_at=utc_now(),
        validation_result=validation_result,
        model_request_id=model_request_id,
        deterministic_fallback_reason=candidate.deterministic_fallback_reason[:500],
        plan_diff=plan_diff,
        idempotency_key=idempotency_key,
    )


def apply_accepted_plan_revision(
    plan: dict[str, Any],
    revision: PlanRevision,
) -> None:
    if revision.validation_result.get("status") != "accepted":
        return
    steps = [step for step in plan.get("steps", []) or [] if isinstance(step, dict)]
    previous_ids = {
        str(step.get("id") or "") for step in revision.previous_remaining_steps
    }
    historical_steps = [
        step for step in steps if str(step.get("id") or "") not in previous_ids
    ]
    current_by_id = {str(step.get("id") or ""): step for step in steps}
    revised_steps = [
        current_by_id[str(snapshot.get("id") or "")]
        for snapshot in revision.revised_remaining_steps
        if str(snapshot.get("id") or "") in current_by_id
    ]
    plan["steps"] = historical_steps + revised_steps
    state = plan.setdefault("bounded_agent", {})
    state["active_revision_id"] = revision.revision_id
    state["latest_plan_diff"] = revision.plan_diff
    state.setdefault("retired_steps", []).extend(revision.skipped_steps)
    fingerprints = state.setdefault("revision_fingerprints", [])
    fingerprint = _fingerprint(
        revision.plan_diff.get("revised_order", []),
        revision.plan_diff.get("skipped_step_ids", []),
        revision.plan_diff.get("retry_step_ids", []),
    )
    if fingerprint not in fingerprints:
        fingerprints.append(fingerprint)


def _step_snapshot(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(step.get("id") or ""),
        "title": str(step.get("title") or "")[:300],
        "detail": str(step.get("detail") or "")[:1000],
        "tool": str(step.get("tool") or ""),
        "status": str(step.get("status") or "queued"),
    }


def _steps_executed(plan: dict[str, Any]) -> int:
    state = plan.get("bounded_agent")
    return int(state.get("steps_executed") or 0) if isinstance(state, dict) else 0


def _fingerprint(
    revised_ids: list[str],
    skipped_ids: list[str],
    retry_ids: list[str],
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "revised": revised_ids,
                "skipped": sorted(skipped_ids),
                "retry": sorted(retry_ids),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
