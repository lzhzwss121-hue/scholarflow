from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scholarflow_api.agent_core import (
    AgentActionDecision,
    ModelCallAudit,
    ModelClaimReview,
    ModelSynthesisResult,
    PlanRevisionCandidate,
    build_default_plan,
)
from scholarflow_api.bounded_agent_live_smoke import (
    LiveSmokeConfig,
    REPORT_KIND,
    dry_run_report,
    run_live_smoke,
    validate_live_configuration,
    write_report,
)


class ScriptedExternalProvider:
    name = "deepseek"
    model = "deepseek-chat"
    api_key = "synthetic-test-secret"

    def _audit(self, purpose: str, *, tokens: int = 20) -> ModelCallAudit:
        return ModelCallAudit(
            provider=self.name,
            model=self.model,
            purpose=purpose,
            prompt_version="live-smoke-contract.v1",
            request_timestamp="2026-08-04T00:00:00+00:00",
            latency_ms=3,
            response_status="success",
            requested_provider=self.name,
            requested_model=self.model,
            external_data_sent=True,
            prompt_tokens=tokens - 5,
            completion_tokens=5,
            total_tokens=tokens,
        )

    def create_plan(self, task, project):
        draft = build_default_plan(task, project, f"{self.name}:{self.model}")
        draft.model_call = self._audit("create_plan")
        return draft

    def choose_next_action(self, observation, allowed_tools, _budgets):
        allowed = {item["name"] for item in allowed_tools}
        last = observation.get("last_tool_result") or {}
        tool = str(last.get("tool") or "")
        status = str(last.get("status") or "")
        if not tool:
            selected = "literature_search"
        elif tool == "literature_search":
            selected = "direction_review"
        elif tool == "direction_review" and status == "retryable_error":
            selected = "research_memory_query"
        elif tool == "research_memory_query":
            selected = "direction_review"
        elif tool == "direction_review":
            selected = "research_decision"
        elif tool == "research_decision":
            selected = "save_artifact"
        elif tool == "save_artifact":
            selected = "update_timeline"
        else:
            selected = sorted(allowed)[0]
        if selected not in allowed:
            selected = sorted(allowed)[0]
        return AgentActionDecision(
            action="tool",
            tool=selected,
            reasoning_summary=f"Fixture observation selects {selected}.",
            replan=False,
            audit=self._audit("choose_next_action"),
        )

    def propose_plan_revision(
        self,
        _observation,
        remaining_steps,
        _allowed_step_templates,
        _budgets,
    ):
        by_tool = {step["tool"]: step["id"] for step in remaining_steps}
        preferred = [
            "research_memory_query",
            "direction_review",
            "research_decision",
            "save_artifact",
            "update_timeline",
        ]
        ordered = [by_tool[tool] for tool in preferred if tool in by_tool]
        ordered.extend(
            step["id"] for step in remaining_steps if step["id"] not in ordered
        )
        return PlanRevisionCandidate(
            reason="Reroute through memory, then retry the failed review.",
            revised_remaining_step_ids=ordered,
            retry_step_ids=[by_tool["direction_review"]],
            audit=self._audit("propose_plan_revision"),
        )

    def synthesize_answer(self, _question, _evidence):
        return ModelSynthesisResult(
            answer=(
                "The synthetic fixture reports an 18% relative reduction, not "
                "elimination. Clinical outcomes are no_reliable_hit. Experiment "
                "remains blocked pending execution details."
            ),
            claim_drafts=["The fixture reports a conditional 18% relative reduction."],
            audit=self._audit("synthesize_answer", tokens=35),
        )

    def validate_claim_optional(self, _claim, _evidence):
        return ModelClaimReview(
            status="not_checked",
            reasons=["Not used by this smoke."],
            audit=self._audit("validate_claim_optional"),
        )


class BoundedAgentLiveSmokeContractTest(unittest.TestCase):
    def config(self, output: Path, *, confirm: bool) -> LiveSmokeConfig:
        return LiveSmokeConfig(
            provider="deepseek",
            model="deepseek-chat",
            max_model_calls=12,
            max_tokens=6000,
            timeout_seconds=20,
            output=output,
            confirm_live=confirm,
        )

    def test_dry_run_is_disabled_and_does_not_build_provider(self) -> None:
        output = Path("/private/tmp/bounded-agent-dry-run.json")
        config = self.config(output, confirm=False)
        called = False

        def builder(_config):
            nonlocal called
            called = True
            raise AssertionError("dry-run must not construct a provider")

        with patch.dict(
            os.environ,
            {"DEEPSEEK_BASE_URL": "", "DEEPSEEK_API_KEY": "host-secret"},
        ):
            report = run_live_smoke(config, provider_builder=builder)
        self.assertFalse(called)
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["status"], "not_started")
        self.assertFalse(report["scope"]["billable_provider_requests"])
        self.assertNotIn("host-secret", json.dumps(report))

    def test_model_and_endpoint_allowlists_fail_closed(self) -> None:
        output = Path("/private/tmp/bounded-agent-allowlist.json")
        with self.assertRaisesRegex(ValueError, "model_not_allowlisted"):
            validate_live_configuration(
                LiveSmokeConfig(
                    provider="deepseek",
                    model="unregistered-model",
                    max_model_calls=8,
                    max_tokens=1000,
                    timeout_seconds=20,
                    output=output,
                )
            )
        with patch.dict(
            os.environ,
            {"DEEPSEEK_BASE_URL": "http://127.0.0.1:9999"},
        ), self.assertRaisesRegex(ValueError, "live_endpoint_not_allowlisted"):
            validate_live_configuration(self.config(output, confirm=False))

    def test_missing_real_key_is_explicitly_skipped(self) -> None:
        output = Path("/private/tmp/bounded-agent-no-key.json")
        with patch.dict(
            os.environ,
            {"DEEPSEEK_BASE_URL": "", "DEEPSEEK_API_KEY": ""},
        ):
            report = run_live_smoke(self.config(output, confirm=True))
        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["blocked_reason"], "provider_api_key_missing")

    def test_mocked_provider_runs_real_control_loop_revision_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            output = Path(tmpdir) / "live-smoke.json"
            secret = ScriptedExternalProvider.api_key
            with patch.dict(
                os.environ,
                {
                    "DEEPSEEK_BASE_URL": "",
                    "DEEPSEEK_API_KEY": secret,
                    "OPENROUTER_API_KEY": "unused-openrouter-secret",
                },
            ):
                report = run_live_smoke(
                    self.config(output, confirm=True),
                    provider_builder=lambda _config: ScriptedExternalProvider(),
                )
                write_report(output, report)
                report_text = output.read_text(encoding="utf-8")
                database_text = Path(
                    report["runtime"]["temporary_database"]
                ).read_bytes()

        self.assertEqual(report["run_kind"], REPORT_KIND)
        self.assertEqual(report["verification_status"], "passed")
        self.assertTrue(report["recovered_from_checkpoint"])
        self.assertGreaterEqual(report["revision_count"], 1)
        self.assertTrue(report["checks"]["multi_step_model_actions"])
        self.assertTrue(report["checks"]["model_plan_revision"])
        self.assertTrue(report["checks"]["model_final_synthesis"])
        self.assertTrue(report["checks"]["experiment_remained_blocked"])
        self.assertTrue(report["checks"]["no_reliable_hit_preserved"])
        self.assertEqual(report["secret_scan"]["status"], "passed")
        self.assertGreater(report["token_usage"]["total_tokens"], 0)
        self.assertNotIn(secret, report_text)
        self.assertNotIn(secret.encode(), database_text)


if __name__ == "__main__":
    unittest.main()
