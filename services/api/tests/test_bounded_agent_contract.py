from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from scholarflow_api.agent_core import (
    AgentActionDecision,
    AgentPlanDraft,
    ModelCallAudit,
    ToolRegistry,
    ToolResult,
    build_default_plan,
    validate_agent_action_json,
)
from scholarflow_api.api_helpers import insert_artifact_row
from scholarflow_api.database import get_connection, init_db, utc_now
from scholarflow_api.jobs.models import DurableJob
from scholarflow_api.schemas import AgentExecuteRequest, AgentPlanRequest, ProjectCreate


class ScriptedProvider:
    name = "scripted"
    model = "scripted-bounded-v1"

    def __init__(self, chooser) -> None:
        self.chooser = chooser
        self.observations: list[dict] = []

    def create_plan(self, task: str, project: dict) -> AgentPlanDraft:
        draft = build_default_plan(task, project, provider="scripted:bounded-v1")
        draft.model_call = self._audit("create_plan")
        return draft

    def choose_next_action(self, observation, allowed_tools, budgets):
        self.observations.append(observation)
        decision = self.chooser(observation, allowed_tools, budgets)
        return AgentActionDecision(
            action=decision.action,
            tool=decision.tool,
            arguments=decision.arguments,
            reasoning_summary=decision.reasoning_summary,
            replan=decision.replan,
            audit=self._audit("choose_next_action"),
        )

    def _audit(self, purpose: str) -> ModelCallAudit:
        return ModelCallAudit(
            provider=self.name,
            model=self.model,
            purpose=purpose,
            prompt_version="bounded-test.v1",
            request_timestamp=utc_now(),
            latency_ms=1,
            response_status="success",
            requested_provider=self.name,
            requested_model=self.model,
            external_data_sent=False,
        )


class FakeExecution:
    def __init__(self) -> None:
        self.checkpoints: list[dict] = []

    def raise_if_cancelled(self) -> None:
        return

    def checkpoint(self, stage: str, progress: int, checkpoint: dict) -> None:
        self.checkpoints.append(
            {"stage": stage, "progress": progress, "checkpoint": checkpoint}
        )


class BoundedAgentContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.db_path = Path(self.tmpdir.name) / "bounded-agent.sqlite3"
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

        self.project = create_project(
            ProjectCreate(title="Bounded Agent Contract", keyword="evidence RAG")
        )

    def tearDown(self) -> None:
        self.environment.stop()
        self.tmpdir.cleanup()

    def _create_plan(self, provider: ScriptedProvider, *, max_steps: int = 8):
        with patch.dict(
            os.environ,
            {
                "SCHOLARFLOW_AGENT_MAX_STEPS": str(max_steps),
                "SCHOLARFLOW_AGENT_MAX_REPLANS": "2",
                "SCHOLARFLOW_AGENT_MAX_MODEL_CALLS": "12",
            },
        ), patch(
            "scholarflow_api.services.agent_plan_service.get_model_provider",
            return_value=provider,
        ):
            from scholarflow_api.services.agent_plan_service import create_agent_plan

            return create_agent_plan(
                AgentPlanRequest(
                    project_id=self.project.id,
                    task="Find evidence and stop safely when it is insufficient.",
                )
            )

    def _registry_builder(
        self,
        calls: list[str],
        *,
        literature_status: str = "partial",
        literature_raises: bool = False,
        memory_hits: int = 1,
    ):
        def build(connection):
            registry = ToolRegistry()

            def create_plan(_context):
                return ToolResult("create_plan", "success", "plan exists")

            def literature(_context):
                calls.append("literature_search")
                if literature_raises:
                    raise RuntimeError("temporary literature failure")
                papers = (
                    [{"id": "paper-contract", "title": "Contract Paper"}]
                    if literature_status != "blocked"
                    else []
                )
                return ToolResult(
                    "literature_search",
                    literature_status,
                    "literature observation",
                    data={
                        "papers": papers,
                        "paper_count": len(papers),
                        "errors": ["partial fixture"] if literature_status == "partial" else [],
                        "relevance_coverage": {"returned_count": len(papers)},
                    },
                )

            def memory(_context):
                calls.append("research_memory_query")
                return ToolResult(
                    "research_memory_query",
                    "success" if memory_hits else "blocked",
                    "memory observation",
                    data={
                        "hit_count": memory_hits,
                        "memory_hit_count": memory_hits,
                        "reliability_status": (
                            "reliable" if memory_hits else "no_reliable_hit"
                        ),
                    },
                )

            def save(context):
                calls.append("save_artifact")
                artifact = insert_artifact_row(
                    connection=connection,
                    project_id=context.project["id"],
                    title=f"agent_run_{context.run_id}.md",
                    kind="markdown",
                    content_markdown="# Bounded result",
                    content_json=json.dumps({"run_id": context.run_id}),
                    diff="+ bounded agent contract artifact",
                    now=utc_now(),
                )
                return ToolResult(
                    "save_artifact",
                    "success",
                    "saved",
                    data={"artifact_id": artifact["id"], "artifact": artifact},
                )

            def timeline(context):
                calls.append("update_timeline")
                return ToolResult(
                    "update_timeline",
                    "success",
                    "timeline updated",
                    data={"artifact_id": context.artifact_id},
                )

            registry.register("create_plan", create_plan, "create plan")
            registry.register("literature_search", literature, "search literature")
            registry.register(
                "direction_review",
                lambda _context: ToolResult("direction_review", "blocked", "not selected"),
                "review direction",
            )
            registry.register("research_memory_query", memory, "query memory")
            registry.register(
                "research_decision",
                lambda _context: ToolResult("research_decision", "blocked", "not selected"),
                "research decision",
            )
            registry.register("save_artifact", save, "save result")
            registry.register("update_timeline", timeline, "update timeline")
            return registry

        return build

    def test_tool_result_changes_the_next_model_selected_tool(self) -> None:
        calls: list[str] = []

        def chooser(observation, _allowed, _budgets):
            last = observation.get("last_tool_result") or {}
            tool = str(last.get("tool") or "")
            status = str(last.get("status") or "")
            if not tool:
                return AgentActionDecision("tool", "literature_search", reasoning_summary="observe papers")
            if tool == "literature_search" and status == "partial":
                return AgentActionDecision("tool", "research_memory_query", reasoning_summary="partial search requires memory")
            if tool == "research_memory_query":
                return AgentActionDecision("tool", "save_artifact", reasoning_summary="save bounded result")
            return AgentActionDecision("tool", "update_timeline", reasoning_summary="finish timeline")

        provider = ScriptedProvider(chooser)
        plan = self._create_plan(provider)
        self.assertEqual(plan.execution_mode, "bounded_observe_reason_act")

        with patch(
            "scholarflow_api.services.agent_run_service.get_model_provider",
            return_value=provider,
        ), patch(
            "scholarflow_api.services.agent_run_service.build_agent_tool_registry",
            side_effect=self._registry_builder(calls),
        ):
            from scholarflow_api.services.agent_run_service import execute_agent_run, run_agent_loop

            execute_agent_run(plan.run_id, AgentExecuteRequest(confirmed=True))
            result = run_agent_loop(plan.run_id, execution=FakeExecution())

        self.assertEqual(
            calls,
            [
                "literature_search",
                "research_memory_query",
                "save_artifact",
                "update_timeline",
            ],
        )
        self.assertEqual(
            provider.observations[1]["last_tool_result"]["status"],
            "partial",
        )
        self.assertEqual(result["status"], "partial")
        with get_connection() as connection:
            row = connection.execute(
                "SELECT plan_json FROM agent_runs WHERE id = ?", (plan.run_id,)
            ).fetchone()
            artifact_row = connection.execute(
                "SELECT content_json FROM artifacts WHERE title = ?",
                (f"agent_run_{plan.run_id}.md",),
            ).fetchone()
        stored = json.loads(row["plan_json"])
        self.assertEqual(len(stored["bounded_agent"]["trace"]), 4)
        artifact_payload = json.loads(artifact_row["content_json"])
        self.assertEqual(
            len(artifact_payload["bounded_agent"]["trace"]),
            4,
        )

    def test_retryable_failure_allows_one_bounded_replan(self) -> None:
        calls: list[str] = []

        def chooser(observation, _allowed, _budgets):
            last = observation.get("last_tool_result") or {}
            if last.get("status") == "retryable_error":
                return AgentActionDecision(
                    "tool",
                    "research_memory_query",
                    reasoning_summary="use memory after transient failure",
                    replan=True,
                )
            return AgentActionDecision(
                "tool",
                "literature_search",
                reasoning_summary="try literature first",
            )

        provider = ScriptedProvider(chooser)
        plan = self._create_plan(provider, max_steps=2)
        with patch(
            "scholarflow_api.services.agent_run_service.get_model_provider",
            return_value=provider,
        ), patch(
            "scholarflow_api.services.agent_run_service.build_agent_tool_registry",
            side_effect=self._registry_builder(calls, literature_raises=True),
        ):
            from scholarflow_api.services.agent_run_service import execute_agent_run, run_agent_loop

            execute_agent_run(plan.run_id, AgentExecuteRequest(confirmed=True))
            result = run_agent_loop(plan.run_id, execution=FakeExecution())

        self.assertEqual(calls, ["literature_search", "research_memory_query"])
        self.assertEqual(result["status"], "partial")
        with get_connection() as connection:
            stored = json.loads(
                connection.execute(
                    "SELECT plan_json FROM agent_runs WHERE id = ?", (plan.run_id,)
                ).fetchone()["plan_json"]
            )
        self.assertEqual(stored["bounded_agent"]["replans"], 1)
        self.assertEqual(stored["bounded_agent"]["stop_reason"], "max_steps budget reached")

    def test_unregistered_tool_and_evidence_tampering_are_rejected(self) -> None:
        base = {
            "action": "tool",
            "tool": "shell",
            "arguments": {},
            "reasoning_summary": "attempt unregistered tool",
            "replan": False,
        }
        with self.assertRaisesRegex(ValueError, "tool_not_allowed"):
            validate_agent_action_json(base, allowed_tools={"literature_search"})

        tampered = {
            **base,
            "tool": "literature_search",
            "arguments": {"evidence_level": "full_text", "page": 7},
        }
        with self.assertRaisesRegex(ValueError, "forbidden_control_fields"):
            validate_agent_action_json(
                tampered,
                allowed_tools={"literature_search"},
            )

        forced_complete = {
            **base,
            "tool": "literature_search",
            "status": "complete",
        }
        with self.assertRaisesRegex(ValueError, "extra_fields"):
            validate_agent_action_json(
                forced_complete,
                allowed_tools={"literature_search"},
            )

    def test_tool_result_status_vocabulary_is_closed(self) -> None:
        for status in (
            "success",
            "partial",
            "blocked",
            "retryable_error",
            "fatal_error",
        ):
            self.assertEqual(
                ToolResult("literature_search", status, "contract").status,
                status,
            )
        with self.assertRaisesRegex(ValueError, "Invalid ToolResult status"):
            ToolResult("literature_search", "complete", "model tried completion")

    def test_max_steps_stops_without_claiming_completion(self) -> None:
        calls: list[str] = []
        provider = ScriptedProvider(
            lambda _observation, _allowed, _budgets: AgentActionDecision(
                "tool", "literature_search", reasoning_summary="one allowed step"
            )
        )
        plan = self._create_plan(provider, max_steps=1)
        with patch(
            "scholarflow_api.services.agent_run_service.get_model_provider",
            return_value=provider,
        ), patch(
            "scholarflow_api.services.agent_run_service.build_agent_tool_registry",
            side_effect=self._registry_builder(calls),
        ):
            from scholarflow_api.services.agent_run_service import execute_agent_run, run_agent_loop

            execute_agent_run(plan.run_id, AgentExecuteRequest(confirmed=True))
            result = run_agent_loop(plan.run_id, execution=FakeExecution())

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["reason"], "max_steps budget reached")
        self.assertEqual(calls, ["literature_search"])

    def test_job_checkpoint_restores_completed_bounded_progress(self) -> None:
        calls: list[str] = []
        provider = ScriptedProvider(
            lambda _observation, _allowed, _budgets: AgentActionDecision(
                "finish", reasoning_summary="checkpoint is complete"
            )
        )
        response = self._create_plan(provider, max_steps=1)
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE id = ?", (response.run_id,)
            ).fetchone()
            db_plan = json.loads(row["plan_json"])
            db_plan["user_confirmed"] = True
            connection.execute(
                "UPDATE agent_runs SET status = 'running', plan_json = ? WHERE id = ?",
                (json.dumps(db_plan), response.run_id),
            )
        checkpoint_plan = json.loads(json.dumps(db_plan))
        checkpoint_plan["bounded_agent"]["steps_executed"] = 1
        checkpoint_plan["bounded_agent"]["trace"] = [
            {"index": 1, "result": {"tool": "literature_search", "status": "success"}}
        ]
        checkpoint_plan["tool_outputs"] = {
            "literature_search": {"paper_count": 1, "artifact_id": ""}
        }
        for step in checkpoint_plan["steps"]:
            if step["tool"] == "literature_search":
                step["status"] = "done"
        job = DurableJob(
            id=response.run_id,
            project_id=self.project.id,
            session_id=response.session_id,
            job_type="agent_run",
            payload={"run_id": response.run_id},
            status="running",
            stage="literature_search",
            progress=30,
            attempts=2,
            max_attempts=3,
            lease_owner="worker-restarted",
            lease_until=None,
            heartbeat_at=None,
            cancellation_requested=False,
            checkpoint={"plan": checkpoint_plan, "bounded_agent": checkpoint_plan["bounded_agent"]},
            result=None,
            error="",
            next_attempt_at=None,
            dedupe_key=f"agent_run:{response.run_id}",
            created_at=utc_now(),
            updated_at=utc_now(),
            completed_at=None,
        )
        with patch(
            "scholarflow_api.services.agent_run_service.get_model_provider",
            return_value=provider,
        ), patch(
            "scholarflow_api.services.agent_run_service.build_agent_tool_registry",
            side_effect=self._registry_builder(calls),
        ):
            from scholarflow_api.services.agent_run_service import run_agent_job

            result = run_agent_job(job, FakeExecution())

        self.assertEqual(result["status"], "partial")
        self.assertEqual(calls, [])
        with get_connection() as connection:
            restored = json.loads(
                connection.execute(
                    "SELECT plan_json FROM agent_runs WHERE id = ?", (response.run_id,)
                ).fetchone()["plan_json"]
            )
        self.assertEqual(restored["bounded_agent"]["steps_executed"], 1)
        self.assertEqual(len(restored["bounded_agent"]["trace"]), 1)

    def test_no_reliable_evidence_finishes_partial_with_no_reliable_hit(self) -> None:
        calls: list[str] = []

        def chooser(observation, _allowed, _budgets):
            tool = str((observation.get("last_tool_result") or {}).get("tool") or "")
            if not tool:
                return AgentActionDecision("tool", "literature_search", reasoning_summary="search")
            if tool == "literature_search":
                return AgentActionDecision("tool", "save_artifact", reasoning_summary="save refusal")
            return AgentActionDecision("tool", "update_timeline", reasoning_summary="record refusal")

        provider = ScriptedProvider(chooser)
        response = self._create_plan(provider)
        with patch(
            "scholarflow_api.services.agent_run_service.get_model_provider",
            return_value=provider,
        ), patch(
            "scholarflow_api.services.agent_run_service.build_agent_tool_registry",
            side_effect=self._registry_builder(
                calls,
                literature_status="blocked",
                memory_hits=0,
            ),
        ):
            from scholarflow_api.services.agent_run_service import execute_agent_run, run_agent_loop

            execute_agent_run(response.run_id, AgentExecuteRequest(confirmed=True))
            result = run_agent_loop(response.run_id, execution=FakeExecution())

        self.assertEqual(result["status"], "partial")
        with get_connection() as connection:
            row = connection.execute(
                "SELECT status, plan_json FROM agent_runs WHERE id = ?", (response.run_id,)
            ).fetchone()
        self.assertEqual(row["status"], "partial")
        self.assertIn("no_reliable_hit", json.loads(row["plan_json"])["run_status_summary"])

    def test_local_provider_dispatches_to_deterministic_fallback(self) -> None:
        from scholarflow_api.services.agent_plan_service import create_agent_plan
        from scholarflow_api.services.agent_run_service import run_agent_loop

        response = create_agent_plan(
            AgentPlanRequest(project_id=self.project.id, task="Local bounded fallback")
        )
        self.assertEqual(response.execution_mode, "deterministic_tool_graph")
        with patch(
            "scholarflow_api.services.agent_run_service.run_deterministic_agent_loop",
            return_value={"run_id": response.run_id, "status": "partial"},
        ) as fallback:
            result = run_agent_loop(response.run_id)
        fallback.assert_called_once_with(response.run_id, execution=None)
        self.assertEqual(result["status"], "partial")

    def test_external_and_tool_actions_require_user_confirmation(self) -> None:
        provider = ScriptedProvider(
            lambda _observation, _allowed, _budgets: AgentActionDecision(
                "tool", "literature_search", reasoning_summary="search"
            )
        )
        response = self._create_plan(provider)
        from scholarflow_api.services.agent_run_service import execute_agent_run

        with self.assertRaisesRegex(HTTPException, "requires confirmation"):
            execute_agent_run(
                response.run_id,
                AgentExecuteRequest(confirmed=False),
            )
        with get_connection() as connection:
            row = connection.execute(
                "SELECT status, plan_json FROM agent_runs WHERE id = ?",
                (response.run_id,),
            ).fetchone()
        self.assertEqual(row["status"], "planned")
        self.assertFalse(json.loads(row["plan_json"])["user_confirmed"])

    def test_repeated_execute_does_not_duplicate_bounded_result_artifact(self) -> None:
        calls: list[str] = []

        def chooser(observation, _allowed, _budgets):
            tool = str((observation.get("last_tool_result") or {}).get("tool") or "")
            if not tool:
                return AgentActionDecision("tool", "literature_search", reasoning_summary="search")
            if tool == "literature_search":
                return AgentActionDecision("tool", "research_memory_query", reasoning_summary="memory")
            if tool == "research_memory_query":
                return AgentActionDecision("tool", "save_artifact", reasoning_summary="save")
            return AgentActionDecision("tool", "update_timeline", reasoning_summary="timeline")

        provider = ScriptedProvider(chooser)
        response = self._create_plan(provider)
        with patch(
            "scholarflow_api.services.agent_run_service.get_model_provider",
            return_value=provider,
        ), patch(
            "scholarflow_api.services.agent_run_service.build_agent_tool_registry",
            side_effect=self._registry_builder(calls),
        ):
            from scholarflow_api.services.agent_run_service import execute_agent_run, run_agent_loop

            execute_agent_run(response.run_id, AgentExecuteRequest(confirmed=True))
            run_agent_loop(response.run_id, execution=FakeExecution())
            repeated = execute_agent_run(
                response.run_id,
                AgentExecuteRequest(confirmed=True),
            )

        with get_connection() as connection:
            artifact_count = connection.execute(
                "SELECT COUNT(*) AS count FROM artifacts WHERE title = ?",
                (f"agent_run_{response.run_id}.md",),
            ).fetchone()["count"]
            job_count = connection.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE id = ?",
                (response.run_id,),
            ).fetchone()["count"]
        self.assertEqual(repeated.status, "partial")
        self.assertEqual(artifact_count, 1)
        self.assertEqual(job_count, 1)


if __name__ == "__main__":
    unittest.main()
