from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scholarflow_api.agent_core import (
    AgentBudgets,
    ModelCallAudit,
    OpenAICompatibleProvider,
    PlanRevisionCandidate,
    validate_plan_revision_json,
)
from scholarflow_api.database import get_connection, init_db, utc_now
from scholarflow_api.repositories.agent_run_repository import update_agent_plan
from scholarflow_api.repositories.plan_revision_repository import (
    insert_plan_revision,
    list_plan_revisions,
)
from scholarflow_api.repositories.tool_event_repository import insert_tool_event
from scholarflow_api.schemas import AgentPlanRequest, ProjectCreate
from scholarflow_api.services.agent_run_service import (
    _bounded_state,
    restore_bounded_checkpoint,
)
from scholarflow_api.services.plan_revision_service import (
    apply_accepted_plan_revision,
    build_plan_revision,
    deterministic_revision_candidate,
    remaining_plan_steps,
)


REGISTERED = {
    "create_plan",
    "literature_search",
    "direction_review",
    "research_memory_query",
    "research_decision",
    "save_artifact",
    "update_timeline",
}


def sample_plan() -> dict:
    return {
        "steps": [
            {"id": "s0", "title": "Plan", "detail": "done", "tool": "create_plan", "status": "done"},
            {"id": "s1", "title": "Search", "detail": "search", "tool": "literature_search", "status": "queued"},
            {"id": "s2", "title": "Memory", "detail": "memory", "tool": "research_memory_query", "status": "queued"},
            {"id": "s3", "title": "Save", "detail": "save", "tool": "save_artifact", "status": "queued"},
        ],
        "bounded_agent": {
            "budgets": AgentBudgets(max_steps=8, max_replans=2, max_model_calls=8).to_dict(),
            "steps_executed": 1,
            "replans": 0,
            "plan_revision_count": 0,
            "active_revision_id": "",
            "revision_fingerprints": [],
        },
    }


class PlanRevisionValidationTest(unittest.TestCase):
    def test_validated_model_candidate_changes_only_remaining_plan(self) -> None:
        plan = sample_plan()
        completed_before = json.loads(json.dumps(plan["steps"][0]))
        candidate = validate_plan_revision_json(
            {
                "reason": "memory is the viable alternative after search failure",
                "revised_remaining_step_ids": ["s2", "s3", "s1"],
                "skipped_step_ids": [],
                "retry_step_ids": ["s1"],
            },
            allowed_step_ids={"s1", "s2", "s3"},
        )
        revision = self._build(plan, candidate)
        apply_accepted_plan_revision(plan, revision)
        self.assertEqual(revision.validation_result["status"], "accepted")
        self.assertEqual(plan["steps"][0], completed_before)
        self.assertEqual(
            [step["id"] for step in plan["steps"][1:]],
            ["s2", "s3", "s1"],
        )

    def test_completed_step_cannot_be_reintroduced_or_modified(self) -> None:
        plan = sample_plan()
        candidate = PlanRevisionCandidate(
            reason="rewrite history",
            revised_remaining_step_ids=["s0", "s2", "s3"],
        )
        revision = self._build(plan, candidate)
        self.assertEqual(revision.validation_result["status"], "rejected")
        self.assertIn(
            "revision_must_account_for_exact_remaining_steps",
            revision.validation_result["reasons"],
        )
        self.assertEqual(plan["steps"][0]["status"], "done")

    def test_unregistered_tool_is_rejected(self) -> None:
        plan = sample_plan()
        plan["steps"][1]["tool"] = "shell"
        before = json.loads(json.dumps(plan))
        candidate = PlanRevisionCandidate(
            reason="try an unregistered tool",
            revised_remaining_step_ids=["s2", "s1", "s3"],
        )
        revision = self._build(plan, candidate)
        self.assertIn("unregistered_tool", revision.validation_result["reasons"])
        apply_accepted_plan_revision(plan, revision)
        self.assertEqual(plan, before)

    def test_revision_over_step_budget_is_rejected(self) -> None:
        plan = sample_plan()
        plan["bounded_agent"]["steps_executed"] = 1
        candidate = PlanRevisionCandidate(
            reason="add an extra step",
            revised_remaining_step_ids=["s2", "s3", "s1", "new-step"],
        )
        revision = self._build(
            plan,
            candidate,
            budgets=AgentBudgets(max_steps=1, max_replans=2, max_model_calls=8),
        )
        self.assertIn("revision_exceeds_step_budget", revision.validation_result["reasons"])

    def test_revision_cycle_is_rejected(self) -> None:
        plan = sample_plan()
        first = self._build(
            plan,
            PlanRevisionCandidate(
                reason="move memory first",
                revised_remaining_step_ids=["s2", "s1", "s3"],
            ),
        )
        apply_accepted_plan_revision(plan, first)
        fingerprint = plan["bounded_agent"]["revision_fingerprints"][0]
        repeated = self._build(
            plan,
            PlanRevisionCandidate(
                reason="repeat same revision",
                revised_remaining_step_ids=["s2", "s1", "s3"],
            ),
            fingerprints={fingerprint},
        )
        self.assertIn("revision_cycle_detected", repeated.validation_result["reasons"])

    def test_revision_diff_reports_reorder_skip_and_retry(self) -> None:
        plan = sample_plan()
        revision = self._build(
            plan,
            PlanRevisionCandidate(
                reason="use memory, skip search, then save",
                revised_remaining_step_ids=["s2", "s3"],
                skipped_step_ids=["s1"],
                retry_step_ids=["s2"],
            ),
        )
        self.assertEqual(revision.validation_result["status"], "accepted")
        self.assertEqual(revision.plan_diff["previous_order"], ["s1", "s2", "s3"])
        self.assertEqual(revision.plan_diff["revised_order"], ["s2", "s3"])
        self.assertEqual(revision.plan_diff["skipped_step_ids"], ["s1"])
        self.assertEqual(revision.plan_diff["retry_step_ids"], ["s2"])
        self.assertTrue(revision.reordered_steps)

    def test_revision_candidate_cannot_set_evidence_citation_or_status(self) -> None:
        with self.assertRaisesRegex(ValueError, "extra_fields"):
            validate_plan_revision_json(
                {
                    "reason": "tamper",
                    "revised_remaining_step_ids": ["s1"],
                    "skipped_step_ids": [],
                    "retry_step_ids": [],
                    "evidence_level": "full_text",
                    "citation_id": "invented",
                    "status": "completed",
                },
                allowed_step_ids={"s1"},
            )

    def test_invalid_model_json_requests_deterministic_fallback(self) -> None:
        provider = OpenAICompatibleProvider(
            model="mock-model",
            base_url="https://mock.invalid",
            api_key="fake-key",
            timeout_seconds=1,
        )
        audit = ModelCallAudit(
            provider="mock",
            model="mock-model",
            purpose="propose_plan_revision",
            prompt_version="test",
            request_timestamp=utc_now(),
            latency_ms=1,
            response_status="success",
        )
        with patch.object(
            provider,
            "_complete_json",
            return_value=({"not": "the revision schema"}, audit),
        ):
            candidate = provider.propose_plan_revision(
                {"last_tool_result": {"status": "retryable_error"}},
                remaining_plan_steps(sample_plan()),
                [],
                {"replans": 1},
            )
        self.assertEqual(candidate.deterministic_fallback_reason, "invalid_response")
        self.assertEqual(candidate.audit.response_status, "invalid_response")
        self.assertEqual(candidate.revised_remaining_step_ids, [])

    def test_legacy_replan_counter_is_conservatively_upgraded(self) -> None:
        plan = {"bounded_agent": {"replans": 1}, "steps": []}
        state = _bounded_state(plan)
        self.assertEqual(state["plan_revision_count"], 1)
        self.assertEqual(state["replans"], 1)
        self.assertEqual(state["active_revision_id"], "")

    def _build(
        self,
        plan: dict,
        candidate: PlanRevisionCandidate,
        *,
        budgets: AgentBudgets | None = None,
        fingerprints: set[str] | None = None,
    ):
        return build_plan_revision(
            run_id="run-contract",
            plan=plan,
            candidate=candidate,
            trigger="contract_test",
            source_tool_result_id=None,
            model_request_id=None,
            registered_tools=REGISTERED,
            budgets=budgets or AgentBudgets(max_steps=8, max_replans=2, max_model_calls=8),
            revision_attempts=0,
            previous_fingerprints=fingerprints or set(),
        )


class PlanRevisionPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.db_path = Path(self.tmpdir.name) / "plan-revisions.sqlite3"
        self.environment = patch.dict(
            os.environ,
            {
                "SCHOLARFLOW_DB_PATH": str(self.db_path),
                "SCHOLARFLOW_MODEL_PROVIDER": "local",
                "OPENROUTER_API_KEY": "",
                "DEEPSEEK_API_KEY": "",
            },
        )
        self.environment.start()
        init_db()
        from scholarflow_api.main import create_project
        from scholarflow_api.services.agent_plan_service import create_agent_plan

        project = create_project(ProjectCreate(title="Revision persistence"))
        self.response = create_agent_plan(
            AgentPlanRequest(project_id=project.id, task="Audit plan revision recovery")
        )

    def tearDown(self) -> None:
        self.environment.stop()
        self.tmpdir.cleanup()

    def test_revision_is_persisted_restored_and_idempotent(self) -> None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT session_id, plan_json FROM agent_runs WHERE id = ?",
                (self.response.run_id,),
            ).fetchone()
            plan = json.loads(row["plan_json"])
            previous = remaining_plan_steps(plan)
            candidate = deterministic_revision_candidate(
                previous,
                reason="recover from retryable tool result",
                preferred_tool="research_memory_query",
                source_tool="literature_search",
                fallback_reason="contract_test",
            )
            source_event_id = insert_tool_event(
                connection,
                row["session_id"],
                "literature_search",
                "partial",
                "retryable fixture",
                utc_now(),
            )
            revision = build_plan_revision(
                run_id=self.response.run_id,
                plan=plan,
                candidate=candidate,
                trigger="retryable_tool_result",
                source_tool_result_id=source_event_id,
                model_request_id=None,
                registered_tools=REGISTERED,
                budgets=AgentBudgets(max_steps=8, max_replans=2, max_model_calls=8),
                revision_attempts=0,
                previous_fingerprints=set(),
            )
            stored_first = insert_plan_revision(connection, revision)
            stored_second = insert_plan_revision(connection, revision)
            apply_accepted_plan_revision(plan, stored_first)
            state = _bounded_state(plan)
            state["plan_revision_count"] = 1
            state["replans"] = 1
            update_agent_plan(
                connection,
                run_id=self.response.run_id,
                plan=plan,
                updated_at=utc_now(),
            )

        self.assertEqual(stored_first.revision_id, stored_second.revision_id)
        with get_connection() as connection:
            revisions = list_plan_revisions(connection, self.response.run_id)
            persisted_plan = json.loads(
                connection.execute(
                    "SELECT plan_json FROM agent_runs WHERE id = ?",
                    (self.response.run_id,),
                ).fetchone()["plan_json"]
            )
        self.assertEqual(len(revisions), 1)
        self.assertEqual(
            revisions[0].source_tool_result_id,
            source_event_id,
        )
        self.assertEqual(
            persisted_plan["bounded_agent"]["active_revision_id"],
            revisions[0].revision_id,
        )

        legacy_plan = json.loads(json.dumps(persisted_plan))
        legacy_plan["bounded_agent"]["plan_revision_count"] = 0
        legacy_plan["bounded_agent"]["replans"] = 0
        legacy_plan["bounded_agent"]["active_revision_id"] = ""
        restore_bounded_checkpoint(
            legacy_plan,
            {"plan": persisted_plan, "bounded_agent": persisted_plan["bounded_agent"]},
        )
        self.assertEqual(
            legacy_plan["bounded_agent"]["active_revision_id"],
            revisions[0].revision_id,
        )
        self.assertEqual(legacy_plan["bounded_agent"]["plan_revision_count"], 1)


if __name__ == "__main__":
    unittest.main()
