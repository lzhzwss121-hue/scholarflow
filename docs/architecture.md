# ScholarFlow Architecture

This document describes the target architecture and the current v0.1.0 public preview.

## Product Shape

ScholarFlow is a local-first, evidence-aware research workflow system. Its default execution unit is a **Bounded Research Agent**, not an autonomous Agent:

- The user gives a research goal.
- ScholarFlow creates a bounded plan before execution.
- Tool calls are visible in a timeline.
- Intermediate and final outputs are saved as artifacts.
- Users can inspect, edit, compare, and reuse artifacts across projects.
- A deterministic state machine owns tools, evidence gates, refusals, and readiness.

## High-Level Components

```text
React Web UI
  -> Backend API
  -> Research Workflow Orchestrator
  -> Model Providers
  -> Research Tools
  -> Local Workspace / Database
  -> External APIs
```

## Repository Layout

```text
apps/
  web/              React + Vite research workspace
  cli/              Local command entry
services/
  api/
    src/scholarflow_api/
      main.py                 FastAPI assembly only
      routers/                HTTP transport grouped by resource
      services/               deterministic workflow orchestration
      repositories/           SQLite persistence operations
      integrations/           external network I/O adapters
      jobs/                   durable local worker and leases
packages/
  schemas/
    src/api.generated.ts      generated from FastAPI OpenAPI
    src/index.ts              compatibility and cross-end domain types
docs/
  architecture.md
  deep-paper-card.md
examples/
  workflows/
```

Current v0.1.0 entry points:

- `apps/web`: React research workspace with API-aware project, timeline, paper, and artifact state.
- `apps/cli`: Node CLI with workspace initialization and Web/API service management.
- `services/api`: FastAPI app with SQLite persistence, a bounded and durable research runner with deterministic fallback, literature retrieval adapters, direction-level paper review, paper memory retrieval, single-paper card generation, and research decision generation.
- `packages/schemas`: generated API DTOs plus cross-end domain and legacy-hydration compatibility types.
- `.github`: CI, Issue templates, and pull request template for open-source contribution.
- `examples/workflows`: public-safe example artifacts.

## Web UI

The web UI should expose the research workflow, not hide it behind a single chat box.

Planned layout:

- Project Navigator: projects, papers, artifacts, notes, experiments.
- Workflow Workspace: user task, confirmed plan, current step, messages.
- Artifact Preview: paper tables, paper cards, gap boards, experiment plans, diffs.
- Tool Timeline: retrieval queries, filters, model calls, artifact writes, errors.

The current implementation persists projects, papers, artifacts, sessions, tool events, durable jobs, workflow runs, paper cards, paper memories, source chunks, RAG evaluations, and model-call audits. It retrieves candidates from arXiv/OpenAlex, downloads eligible open PDFs, verifies parsed PDF evidence, generates 12-section Deep Paper Cards, builds project-scoped FTS5/BM25 plus optional semantic retrieval, and turns qualified evidence into Gap Board, Idea Validation, and Experiment Plan artifacts. It does not run training jobs or treat user-pasted text as verified PDF evidence.

The UI is Chinese-first. Technical terms such as Artifact, Timeline, Gap, Claim, Baseline, and Ablation can remain in English when useful. “Agent” refers only to the current budgeted, allowlisted Bounded Research Agent; the product does not describe it as autonomous scientific reasoning.

The frontend boundary is organized around `state/useWorkflowController.ts`, domain API modules under `services/`, an `ActiveView` composition layer, and page modules. The legacy `workflowService.ts` and `ProductViews.tsx` paths remain as compatibility barrels. AbortController cancellation, project-switch stale-response guards, partial resource loading, and conservative artifact hydration stay in the controller/hydration boundary rather than page components.

## Backend API

The backend owns persistence, deterministic workflow orchestration, and external integrations. `main.py` only assembles lifespan, CORS, and resource routers. Route modules do not own research decisions: deterministic orchestration stays in `services`, SQLite statements stay in `repositories`, and outbound socket calls are reached through `integrations`.

Planned responsibilities:

- Project and artifact CRUD.
- Session and timeline storage.
- Bounded Research Agent lifecycle.
- Model provider routing.
- Paper retrieval adapters.
- Workspace configuration.
- Future authentication and team features.

SQLite is the current database because the first version is local-first. Every connection enables `foreign_keys=ON` and a 5000 ms busy timeout. Initialization enables WAL and applies idempotent, versioned migrations. Durable Direction Review and Research Workflow jobs use atomic leases, heartbeats, bounded retries, cancellation checkpoints, and idempotent artifact writes; restarting the API does not silently discard leased work.

Current tables:

- `projects`
- `papers`
- `artifacts`
- `paper_cards`
- `paper_memories`
- `direction_memories`
- `paper_chunks` and `paper_chunks_fts`
- `rag_evaluations`
- `sessions`
- `agent_runs` (legacy-compatible storage name for Bounded Research Agent runs)
- `jobs` and `worker_heartbeats`
- `model_call_audits`
- `tool_events`

Current API capabilities:

- Create and read projects.
- Read project papers.
- Save artifacts, page through lightweight summaries, and fetch complete Markdown/JSON only from the artifact detail endpoint. The deprecated project artifact-list path also returns summaries and never embeds large bodies.
- Read project sessions.
- Read session and project timelines.
- Generate and execute Bounded Research Agent plans.
- Retrieve and persist ranked paper tables from arXiv/OpenAlex.
- Generate and persist single-paper Deep Paper Cards with PaperSignals through `POST /projects/{project_id}/paper-cards`.
- Generate direction reviews through `POST /projects/{project_id}/direction-reviews`, with 10 papers per round and three rounds maximum.
- Query Paper Memory Bank through `POST /projects/{project_id}/research-memory/query`, retrieving 3-8 relevant paper memories before answering.
- Generate research decision artifacts through `POST /projects/{project_id}/research-decisions`.

## CLI

The CLI makes local usage simple:

```text
scholarflow init
scholarflow start
scholarflow stop
scholarflow status
```

The CLI is not the core product logic. It starts services, manages local configuration, and provides a lightweight command surface.

Default local workspace:

```text
~/.scholarflow/
  config.yaml
  projects/
  artifacts/
  logs/
  cache/
    scholarflow.sqlite3
    services.json
```

The CLI launches API, Web UI, and the durable SQLite worker. It sets `SCHOLARFLOW_DB_PATH=<workspace>/cache/scholarflow.sqlite3` for the backend and `VITE_SCHOLARFLOW_API_BASE_URL` for the Web UI. Service logs are written to the workspace `logs/` directory. Provider configuration remains backend-only and is inherited by API/worker processes; it is never written into workspace configuration.

## Bounded Research Agent Core

Current behavior:

- Bounded Research Agent: after explicit user confirmation, a capable provider chooses one next action from the current ToolRegistry allowlist and receives the structured ToolResult as its next observation.
- Budgets: `max_steps`, `max_replans`, `max_runtime_seconds`, `max_model_calls`, and an optional cost ceiling stop the loop safely.
- Deterministic fallback: the fixed tool graph remains available when the local provider cannot emit tool calls or an external provider fails.
- Planning: the model may choose among eligible tools, but cannot add unregistered tools or modify evidence, citation, locator, refusal, workflow-state, or Experiment-readiness fields.
- Tool Registry: every callable research capability has an explicit schema and execution contract.
- Permission Gates: external data transfer and execution confirmation are explicit.
- Timeline: every important action becomes a visible event.
- Memory: user preferences and project decisions are reusable across sessions.

Each turn persists a compact observation, reasoning summary, selected tool, empty deterministic arguments, ToolResult, and checkpoint in the run plan and final artifact. The durable worker resumes from the newest fenced checkpoint. The model does not own evidence qualification, citation integrity, state transitions, refusal behavior, or Experiment readiness. ScholarFlow does not implement an unlimited autonomous loop.

Current model-provider implementation:

- `ModelProvider` abstraction.
- Unified `create_plan`, `choose_next_action`, `synthesize_answer`, and `validate_claim_optional` interface.
- Local deterministic provider as the default.
- OpenRouter and DeepSeek as optional OpenAI-compatible HTTP providers configured only by backend environment variables.
- `ToolRegistry`.
- `agent_runs` table.
- `POST /agent/plan`.
- `POST /agent/runs/{run_id}/execute`.
- Default tools: `literature_search`, `direction_review`, `research_memory_query`, `research_decision`, `save_artifact`, `update_timeline`.
- Demo tool: `search_mock_papers` remains registered for offline demos and is marked as Demo Mode in the UI when used.

When a selected remote provider has a key, ScholarFlow calls its real chat-completions endpoint. Missing keys, HTTP 401/429/500, timeouts, network errors, and invalid JSON produce an explicit local fallback; the provider label then reports `local`, not the requested remote provider. Safe audit records store provider/model/purpose/prompt version/request time/latency/status/fallback reason and never store prompts, responses, API keys, or Authorization headers.

## Model Provider Strategy

Configuration comes only from the API process environment:

- `SCHOLARFLOW_MODEL_PROVIDER=local|openrouter|deepseek`
- `SCHOLARFLOW_AGENT_MAX_STEPS`, `SCHOLARFLOW_AGENT_MAX_REPLANS`
- `SCHOLARFLOW_AGENT_MAX_RUNTIME_SECONDS`, `SCHOLARFLOW_AGENT_MAX_MODEL_CALLS`
- `SCHOLARFLOW_AGENT_MAX_COST_USD` (optional; enforced only from provider-reported cost)
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`

The browser cannot select or override the provider. Remote model output is schema-validated and treated as advisory. Deterministic code owns the canonical tool set, computes the per-turn eligible allowlist, validates every selected action, and alone writes scientific state, so prompt-injection text cannot grant tools or promote evidence.

## Research Tools

Initial tool categories:

- Direction understanding.
- Literature retrieval: Phase 6 implements arXiv and OpenAlex adapters behind `POST /projects/{project_id}/literature/search`.
- Paper metadata normalization.
- BaselineMap: direction-level comparison background with classic baselines, recent strong baselines, alternative paradigms, benchmark risks, and open questions.
- ResearchSight: paper-level critique covering motivation sharpness, solution elegance, evaluation integrity, paradigm inspiration, why-good, why-not-good, better-angle, baseline comparison, and next-step proposal.
- EvidencePack: evidence boundary for a baseline or critique, including snippets, confidence, and missing-evidence notes.
- Paper memory retrieval: the memory bank stores structured readings and retrieves 3-8 relevant paper memories before answering follow-up questions.
- PDF parsing.
- Paper card generation: Phase 7 implements deterministic single-paper card generation with Markdown and JSON artifacts.
- Direction review: Phase 10 implements a 10-paper-per-round reading workflow with cumulative direction summaries and top-3 personal reading recommendations.
- Gap analysis.
- Novelty checking.
- Minimal reproduction planning.
- Experiment planning: Phase 8 implements deterministic artifact generation for baseline, dataset, metrics, ablations, resource estimates, success criteria, and failure criteria.
- Artifact save and diff.

Every tool should return structured data where possible.

## API Contracts And Artifact Transport

FastAPI OpenAPI is the source for transport DTOs. `npm run generate:api-types` regenerates `packages/schemas/src/api.generated.ts`; the backend contract test fails if the checked-in output drifts. `packages/schemas/src/index.ts` keeps compatibility aliases and only the richer domain shapes needed to conservatively hydrate legacy artifacts.

Artifact transport is two-step:

1. `GET /projects/{project_id}/artifacts/summary?limit=...&offset=...` returns paginated metadata, byte counts, a short Markdown preview, and schema version.
2. `GET /artifacts/{artifact_id}` returns complete `content_markdown`, `content_json`, and diff only for a selected or hydration-required artifact.

The web client accepts both the new page object and the old array-shaped mocked response, then hydrates only the newest relevant artifacts. This preserves old local artifacts without making list requests carry every full document.

## Core Data Objects

Planned entities:

- Project: a research workspace.
- Paper: metadata, source links, code links, tags, relevance score.
- Artifact: Markdown or JSON output saved by a workflow tool.
- PaperCard: structured deep analysis for one paper.
- BaselineMap: comparative context used by direction review and memory.
- ResearchSight: structured critique attached to one paper reading.
- EvidenceSnippet / EvidencePack: metadata, abstract, and paper-card snippets that ground a critique, plus confidence and missing evidence.
- PaperMemory: searchable compressed record created from a direction-review paper card.
- DirectionMemory: cumulative summary over up to 30 paper memories for one research direction.
- Session: one Bounded Research Agent run or related interaction sequence.
- ToolEvent: one visible tool call or system action.
- AgentRun: legacy-compatible API/storage name for one plan-confirm-execute Bounded Research Agent run.
- ExperimentPlan: proposed reproduction or ablation plan.

## Evidence And Integrity

ScholarFlow must avoid unsupported research claims.

Expected behavior:

- Link claims to paper sections, metadata, code repositories, or experiment outputs.
- Distinguish paper claims from model-generated drafts and workflow synthesis.
- Mark uncertain conclusions.
- Surface confidence and missing evidence when a critique is based only on metadata, abstract, or generated paper-card content.
- Preserve search queries and retrieval sources.
- Avoid inventing citations, datasets, metrics, or experimental results.
- Treat pasted text as unverified `supplemental_text`; only successfully parsed and qualified PDF content can be verified `full_text`.
- Retrieve project-isolated source chunks with SQLite FTS5/BM25 and optional external semantic embeddings. Local lexical hash remains labelled lexical rather than semantic.
- Keep `no_reliable_hit` when evidence gates fail, and represent claim checks as supported, contradicted, insufficient, or not checked instead of a generic validated boolean.

The Phase 6 paper table artifact preserves expanded queries, source API names, source URLs, relevance reasons, and retrieval warnings. Phase 7 paper-card artifacts preserve the 12 sections, weakest assumption, minimal reproduction, counterexample, and follow-up idea in structured JSON. Phase 8 decision artifacts preserve true/engineering/pseudo gap labels, novelty risk, feasibility, and experiment plans. Phase 9 adds public release documentation, contribution templates, CI, release notes, and synthetic example artifacts. Phase 10 direction-review artifacts preserve the scope, selected papers, abstract Chinese reading entry, 12-section card content, direction summary, and top-3 self-reading recommendation. Phase 11 memory artifacts preserve the user question, retrieved paper memories, direction memory snapshot, answer, and retrieval warnings. Phase 13 artifacts preserve the direction-level BaselineMap and paper-level ResearchSight critique. Phase 14 adds EvidencePack boundaries to these critiques, making explicit whether a judgment is grounded in metadata, abstract, generated paper-card content, or still missing full-paper evidence.

## Local Data Policy

Local workspaces may contain private papers, unpublished ideas, notes, and experiment logs.

Default ignored data:

- API keys.
- PDFs and documents.
- SQLite databases.
- Logs.
- Vector stores.
- User artifacts.
- Local workspaces.
