from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Callable, Iterator
from urllib.parse import urlparse
from uuid import uuid4

from scholarflow_api.agent_core import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENROUTER_BASE_URL,
    DEFAULT_OPENROUTER_MODEL,
    AgentPlanDraft,
    DeepSeekProvider,
    ModelCallAudit,
    ModelClaimReview,
    ModelProvider,
    ModelSynthesisResult,
    OpenRouterProvider,
    PlanRevisionCandidate,
    ToolContext,
    ToolRegistry,
    ToolResult,
)
from scholarflow_api.api_helpers import insert_artifact_row
from scholarflow_api.database import init_db, utc_now
from scholarflow_api.jobs.context import job_artifact_scope
from scholarflow_api.jobs.repository import (
    complete_job,
    fail_job,
    lease_next_job,
)
from scholarflow_api.jobs.worker import JobExecution
from scholarflow_api.repositories.agent_run_repository import insert_model_call_audit
from scholarflow_api.schemas import AgentExecuteRequest, AgentPlanRequest, ProjectCreate
from scholarflow_api.services.agent_plan_service import create_agent_plan
from scholarflow_api.services.agent_run_service import (
    execute_agent_run,
    get_agent_run_status,
    run_agent_loop,
)
from scholarflow_api.services.workflow_runtime import create_project


REPORT_KIND = "live_provider_fixture_tools"
REPORT_SCHEMA_VERSION = "bounded_agent_live_smoke.v1"
ALLOWED_MODELS = {
    "deepseek": frozenset({"deepseek-chat", "deepseek-reasoner"}),
    "openrouter": frozenset({DEFAULT_OPENROUTER_MODEL}),
}
EXPECTED_ENDPOINT_HOSTS = {
    "deepseek": "api.deepseek.com",
    "openrouter": "openrouter.ai",
}
SYNTHETIC_TASK = (
    "Use only the supplied synthetic fixture literature to assess whether "
    "bounded decoding reduces unsupported claims, refuse the unrelated clinical "
    "outcomes question, recover from the injected direction-review failure, and "
    "keep the experiment blocked until execution details exist."
)


@dataclass(frozen=True)
class LiveSmokeConfig:
    provider: str
    model: str
    max_model_calls: int
    max_tokens: int
    timeout_seconds: float
    output: Path
    confirm_live: bool = False


class SimulatedWorkerCrash(RuntimeError):
    """A controlled crash raised only after a durable checkpoint is written."""


class CrashAfterFirstCompletedTool(JobExecution):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._stage_counts: dict[str, int] = {}
        self.crashed = False

    def checkpoint(
        self,
        stage: str,
        progress: int,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        super().checkpoint(stage, progress, checkpoint)
        self._stage_counts[stage] = self._stage_counts.get(stage, 0) + 1
        if (
            not self.crashed
            and stage == "literature_search"
            and self._stage_counts[stage] >= 2
        ):
            self.crashed = True
            raise SimulatedWorkerCrash(
                "controlled live-smoke worker interruption after checkpoint"
            )


class RecordingProvider:
    """Records non-secret model audits while delegating every model decision."""

    def __init__(self, delegate: ModelProvider) -> None:
        self.delegate = delegate
        self.name = str(getattr(delegate, "name", ""))
        self.model = str(getattr(delegate, "model", ""))
        self.api_key = str(getattr(delegate, "api_key", ""))
        self.audits: list[ModelCallAudit] = []

    def _record(self, result: Any) -> Any:
        audit = getattr(result, "audit", None) or getattr(result, "model_call", None)
        if isinstance(audit, ModelCallAudit):
            self.audits.append(audit)
        return result

    def create_plan(self, task: str, project: dict[str, Any]) -> AgentPlanDraft:
        return self._record(self.delegate.create_plan(task, project))

    def synthesize_answer(
        self,
        question: str,
        evidence: list[dict[str, Any]],
    ) -> ModelSynthesisResult:
        return self._record(self.delegate.synthesize_answer(question, evidence))

    def validate_claim_optional(
        self,
        claim: str,
        evidence: list[dict[str, Any]],
    ) -> ModelClaimReview:
        return self._record(self.delegate.validate_claim_optional(claim, evidence))

    def choose_next_action(
        self,
        observation: dict[str, Any],
        allowed_tools: list[dict[str, str]],
        budgets: dict[str, Any],
    ) -> Any:
        return self._record(
            self.delegate.choose_next_action(observation, allowed_tools, budgets)
        )

    def propose_plan_revision(
        self,
        observation: dict[str, Any],
        remaining_steps: list[dict[str, Any]],
        allowed_step_templates: list[dict[str, str]],
        budgets: dict[str, Any],
    ) -> PlanRevisionCandidate:
        return self._record(
            self.delegate.propose_plan_revision(
                observation,
                remaining_steps,
                allowed_step_templates,
                budgets,
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a disabled-by-default Bounded Research Agent smoke with a real "
            "model provider and deterministic fixture tools."
        )
    )
    parser.add_argument("--provider", required=True, choices=("deepseek", "openrouter"))
    parser.add_argument("--model", default="")
    parser.add_argument("--max-model-calls", type=int, default=12)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=6000,
        help="Total provider token budget for this isolated smoke run.",
    )
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Explicitly authorize billable external provider requests.",
    )
    return parser


def parse_config(argv: list[str] | None = None) -> LiveSmokeConfig:
    args = build_parser().parse_args(argv)
    model = args.model or default_model(args.provider)
    config = LiveSmokeConfig(
        provider=args.provider,
        model=model,
        max_model_calls=max(4, min(32, int(args.max_model_calls))),
        max_tokens=max(256, min(100_000, int(args.max_tokens))),
        timeout_seconds=max(5.0, min(120.0, float(args.timeout))),
        output=args.output,
        confirm_live=bool(args.confirm_live),
    )
    validate_live_configuration(config)
    return config


def default_model(provider: str) -> str:
    return DEFAULT_DEEPSEEK_MODEL if provider == "deepseek" else DEFAULT_OPENROUTER_MODEL


def provider_base_url(provider: str) -> str:
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL
    return os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL


def provider_key_present(provider: str) -> bool:
    name = "DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENROUTER_API_KEY"
    return bool(os.getenv(name, "").strip())


def validate_live_configuration(config: LiveSmokeConfig) -> None:
    if config.model not in ALLOWED_MODELS[config.provider]:
        raise ValueError(
            f"model_not_allowlisted:{config.provider}:{config.model}"
        )
    parsed = urlparse(provider_base_url(config.provider))
    if parsed.scheme != "https" or parsed.hostname != EXPECTED_ENDPOINT_HOSTS[config.provider]:
        raise ValueError(
            f"live_endpoint_not_allowlisted:{config.provider}:{parsed.scheme}://{parsed.hostname or ''}"
        )
    if config.output != Path("/private/tmp") and Path("/private/tmp") not in config.output.parents:
        raise ValueError("live_smoke_output_must_be_under_/private/tmp")


def dry_run_report(config: LiveSmokeConfig) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_kind": REPORT_KIND,
        "mode": "dry_run",
        "status": "not_started",
        "provider": config.provider,
        "model": config.model,
        "endpoint": provider_base_url(config.provider),
        "api_key_present": provider_key_present(config.provider),
        "limits": {
            "max_model_calls": config.max_model_calls,
            "max_total_tokens": config.max_tokens,
            "timeout_seconds": config.timeout_seconds,
        },
        "scope": {
            "project": "synthetic_non_private_fixture",
            "tools": "deterministic_fixture_tools",
            "external_research_network": False,
            "billable_provider_requests": False,
        },
        "next_step": "Re-run with --confirm-live only after explicit user authorization.",
    }


def instantiate_provider(config: LiveSmokeConfig) -> ModelProvider:
    if config.provider == "deepseek":
        return DeepSeekProvider()
    return OpenRouterProvider()


@contextmanager
def isolated_environment(config: LiveSmokeConfig, database_path: Path) -> Iterator[None]:
    names = {
        "SCHOLARFLOW_DB_PATH": str(database_path),
        "SCHOLARFLOW_MODEL_PROVIDER": config.provider,
        "SCHOLARFLOW_AGENT_MAX_STEPS": "12",
        "SCHOLARFLOW_AGENT_MAX_REPLANS": "2",
        "SCHOLARFLOW_AGENT_MAX_RUNTIME_SECONDS": str(int(config.timeout_seconds * 6)),
        "SCHOLARFLOW_AGENT_MAX_MODEL_CALLS": str(config.max_model_calls),
        "SCHOLARFLOW_MODEL_MAX_OUTPUT_TOKENS": str(min(1200, config.max_tokens)),
        "SCHOLARFLOW_MODEL_TOTAL_TOKEN_BUDGET": str(config.max_tokens),
    }
    prefix = "DEEPSEEK" if config.provider == "deepseek" else "OPENROUTER"
    names[f"{prefix}_MODEL"] = config.model
    names[f"{prefix}_TIMEOUT_SECONDS"] = str(config.timeout_seconds)
    previous = {name: os.environ.get(name) for name in names}
    os.environ.update(names)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def synthetic_papers(project_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "fixture-paper-bounded-decoding-v1",
            "project_id": project_id,
            "title": "Bounded Decoding on Synthetic Unsupported-Claim Tasks",
            "abstract": (
                "On the fixed synthetic benchmark, constrained decoding reduced "
                "unsupported claims by 18% relative, but did not eliminate them."
            ),
            "source": "synthetic_fixture",
            "source_origin": "fixture_manifest",
            "evidence_level": "abstract_only",
            "evidence_verified": False,
            "section": "Results",
            "page": 3,
        },
        {
            "id": "fixture-paper-calibration-v1",
            "project_id": project_id,
            "title": "Calibration Limits in a Synthetic Agent Benchmark",
            "abstract": (
                "The effect was observed only under the stated decoding budget; "
                "the fixture contains no clinical outcome evidence."
            ),
            "source": "synthetic_fixture",
            "source_origin": "fixture_manifest",
            "evidence_level": "abstract_only",
            "evidence_verified": False,
            "section": "Limitations",
            "page": 5,
        },
    ]


def fixture_registry_factory(
    provider: RecordingProvider,
    attempts: dict[str, int],
    connection: Any,
) -> ToolRegistry:
    registry = ToolRegistry()

    def literature(context: ToolContext) -> ToolResult:
        papers = synthetic_papers(str(context.project["id"]))
        return ToolResult(
            "literature_search",
            "success",
            "Loaded two isolated synthetic fixture papers; select direction_review next.",
            data={
                "papers": papers,
                "paper_count": len(papers),
                "relevance_coverage": {"returned_count": len(papers)},
                "errors": [],
            },
        )

    def direction(context: ToolContext) -> ToolResult:
        attempts["direction_review"] = attempts.get("direction_review", 0) + 1
        if attempts["direction_review"] == 1:
            return ToolResult(
                "direction_review",
                "retryable_error",
                "Injected fixture parser timeout; revise the remaining plan and reroute through research memory.",
                data={"errors": ["fixture_parser_timeout"]},
            )
        return ToolResult(
            "direction_review",
            "success",
            "Recovered fixture review; limitations remain explicit.",
            data={"review_status": "complete", "relevant_read_count": 2},
        )

    def memory(context: ToolContext) -> ToolResult:
        return ToolResult(
            "research_memory_query",
            "success",
            "Found bounded fixture evidence and one explicit no_reliable_hit question.",
            data={
                "hit_count": 2,
                "memory_hit_count": 2,
                "reliability_status": "supported",
                "question_results": [
                    {
                        "question": "Does bounded decoding reduce unsupported claims?",
                        "status": "supported",
                    },
                    {
                        "question": "Does it improve clinical outcomes?",
                        "status": "no_reliable_hit",
                    },
                ],
            },
        )

    def decision(context: ToolContext) -> ToolResult:
        return ToolResult(
            "research_decision",
            "partial",
            "Synthetic gap is traceable, but Experiment remains blocked because execution details are missing.",
            data={
                "decision_status": "partial",
                "experiment_status": "blocked",
                "experiment_readiness": "blocked_missing_execution_details",
            },
        )

    def save(context: ToolContext) -> ToolResult:
        required = {"research_memory_query", "research_decision"}
        missing = sorted(required - set(context.outputs))
        if missing:
            return ToolResult(
                "save_artifact",
                "retryable_error",
                "Final synthesis is gated until fixture evidence and decision checks complete.",
                data={"errors": ["missing_fixture_outputs:" + ",".join(missing)]},
            )
        state = context.plan.get("bounded_agent")
        if not isinstance(state, dict):
            return ToolResult("save_artifact", "fatal_error", "bounded state missing")
        budgets = state.get("budgets") if isinstance(state.get("budgets"), dict) else {}
        if int(state.get("model_calls") or 0) >= int(budgets.get("max_model_calls") or 0):
            return ToolResult("save_artifact", "blocked", "model call budget exhausted before synthesis")
        state["model_calls"] = int(state.get("model_calls") or 0) + 1
        evidence = [
            {
                "citation_id": "fixture-paper-bounded-decoding-v1:p3:results",
                "text": (
                    "On the fixed synthetic benchmark, constrained decoding reduced "
                    "unsupported claims by 18% relative, but did not eliminate them."
                ),
                "evidence_level": "abstract_only",
                "section": "Results",
                "page": 3,
            },
            {
                "citation_id": "fixture-paper-calibration-v1:p5:limitations",
                "text": (
                    "The effect was observed only under the stated decoding budget; "
                    "there is no evidence about clinical outcomes."
                ),
                "evidence_level": "abstract_only",
                "section": "Limitations",
                "page": 5,
            },
        ]
        synthesis = provider.synthesize_answer(
            (
                "Answer the supported synthetic benchmark question, explicitly refuse "
                "the clinical-outcomes question as no_reliable_hit, preserve the 'did "
                "not eliminate' limitation, and state that Experiment is blocked."
            ),
            evidence,
        )
        insert_model_call_audit(
            connection,
            project_id=str(context.project["id"]),
            run_id=context.run_id,
            audit=synthesis.audit.to_dict(),
        )
        if synthesis.audit.provider != provider.name or synthesis.audit.response_status != "success":
            return ToolResult(
                "save_artifact",
                "blocked",
                "Real provider synthesis failed; no live-success artifact was claimed.",
                data={"errors": [synthesis.audit.fallback_reason or synthesis.audit.response_status]},
            )
        payload = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "run_kind": REPORT_KIND,
            "answer": synthesis.answer,
            "claim_drafts": synthesis.claim_drafts,
            "evidence_status": {
                "level": "abstract_only",
                "verified_full_text": False,
                "reliable_question": "supported",
                "unrelated_question": "no_reliable_hit",
                "experiment_readiness": "blocked_missing_execution_details",
                "authority": "deterministic_fixture_gate",
            },
            "citations": [item["citation_id"] for item in evidence],
            "model_audit": synthesis.audit.to_dict(),
        }
        artifact = insert_artifact_row(
            connection=connection,
            project_id=str(context.project["id"]),
            title=f"bounded_agent_live_fixture_{context.run_id}.json",
            kind="json",
            content_markdown=synthesis.answer,
            content_json=json.dumps(payload, ensure_ascii=False, indent=2),
            diff="+ live provider synthesis over deterministic fixture evidence",
            now=utc_now(),
        )
        return ToolResult(
            "save_artifact",
            "success",
            "Saved model-generated synthesis with deterministic fixture evidence gates.",
            data={"artifact": artifact, "artifact_id": artifact["id"]},
        )

    def timeline(_context: ToolContext) -> ToolResult:
        return ToolResult(
            "update_timeline",
            "success",
            "Finalized the auditable fixture-tools timeline.",
            data={"timeline_updated": True},
        )

    registry.register(
        "create_plan",
        lambda _context: ToolResult(
            "create_plan",
            "success",
            "Plan already created and confirmed.",
        ),
        "Plan creation is complete before the control loop starts.",
    )
    registry.register("literature_search", literature, "Load synthetic fixture papers first.")
    registry.register(
        "direction_review",
        direction,
        "Review fixtures; the first call intentionally fails and requires PlanRevision.",
    )
    registry.register(
        "research_memory_query",
        memory,
        "Reroute here after the direction-review failure to distinguish support from no_reliable_hit.",
    )
    registry.register(
        "research_decision",
        decision,
        "Apply deterministic readiness gates; Experiment must remain blocked without execution details.",
    )
    registry.register(
        "save_artifact",
        save,
        "Only after memory and research decision, ask the real provider for final synthesis.",
    )
    registry.register(
        "update_timeline",
        timeline,
        "Finalize only after the result artifact exists.",
    )
    return registry


def run_live_smoke(
    config: LiveSmokeConfig,
    *,
    provider_builder: Callable[[LiveSmokeConfig], ModelProvider] = instantiate_provider,
) -> dict[str, Any]:
    validate_live_configuration(config)
    if not config.confirm_live:
        return dry_run_report(config)
    if provider_builder is instantiate_provider and not provider_key_present(config.provider):
        return {
            **dry_run_report(config),
            "mode": "live",
            "status": "skipped",
            "blocked_reason": "provider_api_key_missing",
        }

    started_at = datetime.now(timezone.utc)
    database_path = config.output.with_name(
        f"{config.output.stem}-{uuid4().hex[:10]}.sqlite3"
    )
    attempts: dict[str, int] = {}
    recovered_from_checkpoint = False
    outcome: dict[str, Any] = {}
    with isolated_environment(config, database_path):
        init_db()
        provider = RecordingProvider(provider_builder(config))
        project = create_project(
            ProjectCreate(
                title="Synthetic Bounded Agent Live Provider Smoke",
                description="Non-private synthetic fixture project for provider control-loop audit.",
                keyword="bounded decoding unsupported claims synthetic fixture",
                field="AI reliability",
                workflow="live-provider-fixture-tools",
            )
        )
        plan_response = create_agent_plan(
            AgentPlanRequest(project_id=project.id, task=SYNTHETIC_TASK),
            provider_override=provider,
        )
        if (
            plan_response.execution_mode != "bounded_observe_reason_act"
            or plan_response.model_call.provider != config.provider
            or plan_response.model_call.response_status != "success"
        ):
            outcome = {
                "status": "blocked",
                "reason": "real_provider_plan_generation_failed",
            }
        else:
            execute_agent_run(
                plan_response.run_id,
                AgentExecuteRequest(confirmed=True),
            )
            worker_one = "live-smoke-worker-a"
            first_job = lease_next_job(worker_one, lease_seconds=5)
            if first_job is None:
                raise RuntimeError("live_smoke_job_not_leased")
            crash_execution = CrashAfterFirstCompletedTool(
                job_id=first_job.id,
                worker_id=worker_one,
                lease_seconds=5,
            )
            registry_builder = lambda connection: fixture_registry_factory(
                provider,
                attempts,
                connection,
            )
            try:
                with job_artifact_scope(first_job.id):
                    outcome = run_agent_loop(
                        first_job.id,
                        execution=crash_execution,
                        durable_checkpoint=first_job.checkpoint,
                        registry_factory=registry_builder,
                        provider_factory=lambda: provider,
                    )
                complete_job(first_job.id, worker_one, outcome)
            except SimulatedWorkerCrash as error:
                fail_job(
                    first_job.id,
                    worker_one,
                    error,
                    retry_backoff_seconds=0,
                )
                worker_two = "live-smoke-worker-b"
                resumed_job = lease_next_job(
                    worker_two,
                    lease_seconds=30,
                    now=datetime.now(timezone.utc) + timedelta(seconds=1),
                )
                if resumed_job is None:
                    raise RuntimeError("live_smoke_job_not_recovered")
                recovered_from_checkpoint = bool(resumed_job.checkpoint)
                with job_artifact_scope(resumed_job.id):
                    outcome = run_agent_loop(
                        resumed_job.id,
                        execution=JobExecution(
                            job_id=resumed_job.id,
                            worker_id=worker_two,
                            lease_seconds=30,
                        ),
                        durable_checkpoint=resumed_job.checkpoint,
                        registry_factory=registry_builder,
                        provider_factory=lambda: provider,
                    )
                complete_job(resumed_job.id, worker_two, outcome)

        status = get_agent_run_status(plan_response.run_id)
        report = build_live_report(
            config=config,
            database_path=database_path,
            provider=provider,
            run_id=plan_response.run_id,
            started_at=started_at,
            ended_at=datetime.now(timezone.utc),
            recovered_from_checkpoint=recovered_from_checkpoint,
            outcome=outcome,
            status=status,
        )
        report["secret_scan"] = secret_scan(
            report,
            database_path,
            provider_secrets(),
        )
    return report


def build_live_report(
    *,
    config: LiveSmokeConfig,
    database_path: Path,
    provider: RecordingProvider,
    run_id: str,
    started_at: datetime,
    ended_at: datetime,
    recovered_from_checkpoint: bool,
    outcome: dict[str, Any],
    status: Any,
) -> dict[str, Any]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        events = [
            dict(row)
            for row in connection.execute(
                "SELECT tool, status, summary, created_at FROM tool_events "
                "WHERE session_id = (SELECT session_id FROM agent_runs WHERE id = ?) "
                "ORDER BY rowid",
                (run_id,),
            ).fetchall()
        ]
        revisions = [
            dict(row)
            for row in connection.execute(
                "SELECT id, trigger, reason, validation_result_json, "
                "deterministic_fallback_reason, created_at FROM plan_revisions "
                "WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        ]
        artifact_row = connection.execute(
            "SELECT content_json FROM artifacts WHERE id = "
            "(SELECT result_artifact_id FROM agent_runs WHERE id = ?)",
            (run_id,),
        ).fetchone()
    artifact_payload = json.loads(artifact_row["content_json"]) if artifact_row else {}
    audits = [audit.to_dict() for audit in provider.audits]
    successful_external = [
        audit
        for audit in audits
        if audit["provider"] == config.provider
        and audit["response_status"] == "success"
        and audit["external_data_sent"] is True
    ]
    successful_actions = [
        audit for audit in successful_external if audit["purpose"] == "choose_next_action"
    ]
    successful_revisions = [
        audit
        for audit in successful_external
        if audit["purpose"] == "propose_plan_revision"
    ]
    successful_synthesis = [
        audit for audit in successful_external if audit["purpose"] == "synthesize_answer"
    ]
    revision_payloads = [
        {
            **{key: value for key, value in row.items() if key != "validation_result_json"},
            "validation_result": json.loads(row["validation_result_json"]),
        }
        for row in revisions
    ]
    checks = {
        "real_plan_generated": any(audit["purpose"] == "create_plan" for audit in successful_external),
        "multi_step_model_actions": len(successful_actions) >= 2,
        "model_plan_revision": bool(successful_revisions),
        "model_final_synthesis": bool(successful_synthesis),
        "durable_checkpoint_recovery": recovered_from_checkpoint,
        "fixture_tool_failure_observed": any(
            event["tool"] == "direction_review" and event["status"] in {"partial", "failed"}
            for event in events
        ),
        "plan_revision_persisted": bool(revisions),
        "experiment_remained_blocked": (
            artifact_payload.get("evidence_status", {}).get("experiment_readiness")
            == "blocked_missing_execution_details"
        ),
        "no_reliable_hit_preserved": (
            artifact_payload.get("evidence_status", {}).get("unrelated_question")
            == "no_reliable_hit"
        ),
        "deterministic_evidence_authority": (
            artifact_payload.get("evidence_status", {}).get("authority")
            == "deterministic_fixture_gate"
        ),
    }
    verification_status = "passed" if all(checks.values()) else "partial"
    token_usage = {
        "prompt_tokens": sum(int(audit["prompt_tokens"]) for audit in audits),
        "completion_tokens": sum(int(audit["completion_tokens"]) for audit in audits),
        "total_tokens": sum(int(audit["total_tokens"]) for audit in audits),
        "configured_total_token_budget": config.max_tokens,
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_kind": REPORT_KIND,
        "mode": "live",
        "verification_status": verification_status,
        "provider": config.provider,
        "model": config.model,
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_ms": max(0, int((ended_at - started_at).total_seconds() * 1000)),
        "model_call_count": len(audits),
        "successful_external_model_call_count": len(successful_external),
        "tool_execution_sequence": [
            {"tool": event["tool"], "status": event["status"]}
            for event in events
            if event["tool"] in {
                "literature_search",
                "direction_review",
                "research_memory_query",
                "research_decision",
                "save_artifact",
                "update_timeline",
            }
        ],
        "revision_count": len(revisions),
        "revisions": revision_payloads,
        "fallback_count": sum(1 for audit in audits if audit["fallback_reason"]),
        "final_status": str(status.status),
        "evidence_status": artifact_payload.get("evidence_status", {}),
        "token_usage": token_usage,
        "errors": [
            str(item)
            for item in status.warnings
        ],
        "recovered_from_checkpoint": recovered_from_checkpoint,
        "checks": checks,
        "outcome": outcome,
        "model_audits": audits,
        "scope": {
            "project": "synthetic_non_private_fixture",
            "tools": "deterministic_fixture_tools",
            "external_research_network": False,
            "classification": REPORT_KIND,
        },
        "runtime": {
            "temporary_database": str(database_path),
            "database_isolation": "unique_per_run",
        },
    }


def provider_secrets() -> list[str]:
    return [
        value
        for name in ("DEEPSEEK_API_KEY", "OPENROUTER_API_KEY")
        if (value := os.getenv(name, "").strip())
    ]


def secret_scan(
    report: dict[str, Any],
    database_path: Path,
    secrets: list[str],
) -> dict[str, Any]:
    report_bytes = json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
    database_bytes = database_path.read_bytes() if database_path.exists() else b""
    matches = 0
    for secret in secrets:
        encoded = secret.encode("utf-8")
        matches += int(bool(encoded and encoded in report_bytes))
        matches += int(bool(encoded and encoded in database_bytes))
    return {
        "status": "passed" if matches == 0 else "failed",
        "match_count": matches,
        "scanned": ["report_json", "temporary_sqlite", "result_artifact"],
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    try:
        config = parse_config(argv)
        report = run_live_smoke(config)
        write_report(config.output, report)
        print(
            json.dumps(
                {
                    "run_kind": report["run_kind"],
                    "mode": report["mode"],
                    "status": report.get("verification_status") or report.get("status"),
                    "provider": report["provider"],
                    "model": report["model"],
                    "output": str(config.output),
                },
                ensure_ascii=False,
            )
        )
        return 0 if report.get("verification_status") != "failed" else 1
    except Exception as error:
        print(f"bounded_agent_live_smoke_error:{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
