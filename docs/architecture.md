# ScholarFlow Architecture

This document describes the target architecture and the current Phase 8 research decision workflow.

## Product Shape

ScholarFlow is a local-first AI research workflow agent. It should feel closer to a coding agent workspace than a normal chatbot:

- The user gives a research goal.
- The agent creates a plan before execution.
- Tool calls are visible in a timeline.
- Intermediate and final outputs are saved as artifacts.
- Users can inspect, edit, compare, and reuse artifacts across projects.

## High-Level Components

```text
React Web UI
  -> Backend API
  -> Agent Orchestrator
  -> Model Providers
  -> Research Tools
  -> Local Workspace / Database
  -> External APIs
```

## Planned Repository Layout

```text
apps/
  web/              React + Vite research workspace
  cli/              Local command entry
services/
  api/              FastAPI service
packages/
  schemas/          Shared TypeScript/Python-compatible contracts
docs/
  architecture.md
  deep-paper-card.md
examples/
  workflows/
```

Current Phase 8 entry points:

- `apps/web`: React research workspace with API-aware project, timeline, paper, and artifact state.
- `apps/cli`: Node CLI with workspace initialization and Web/API service management.
- `services/api`: FastAPI app with SQLite persistence, the first minimal agent loop, literature retrieval adapters, single-paper card generation, and research decision generation.
- `packages/schemas`: shared TypeScript API contracts.

## Web UI

The web UI should expose the research workflow, not hide it behind a single chat box.

Planned layout:

- Project Navigator: projects, papers, artifacts, notes, experiments.
- Agent Workspace: user task, agent plan, current step, messages.
- Artifact Preview: paper tables, paper cards, gap boards, experiment plans, diffs.
- Tool Timeline: retrieval queries, filters, model calls, artifact writes, errors.

The Phase 8 implementation reads and writes local API data for projects, papers, artifacts, sessions, tool events, agent runs, and paper cards. It can retrieve paper candidates from arXiv/OpenAlex, generate a single-paper 12-section Deep Paper Card, and turn those assets into a Gap Board, Idea Validation Report, and Experiment Plan. It intentionally does not download PDFs, batch-read papers, or run training jobs yet.

The UI is Chinese-first. Technical terms such as Agent Loop, Artifact, Timeline, Gap, Claim, Baseline, and Ablation can remain in English when useful.

## Backend API

The backend owns persistence, agent orchestration, and external integrations.

Planned responsibilities:

- Project and artifact CRUD.
- Session and timeline storage.
- Agent run lifecycle.
- Model provider routing.
- Paper retrieval adapters.
- Workspace configuration.
- Future authentication and team features.

SQLite is the current database because the first version is local-first.

Current tables:

- `projects`
- `papers`
- `artifacts`
- `paper_cards`
- `sessions`
- `tool_events`

Current API capabilities:

- Create and read projects.
- Read project papers.
- Save and read artifacts.
- Read project sessions.
- Read session and project timelines.
- Generate and execute minimal agent plans.
- Retrieve and persist ranked paper tables from arXiv/OpenAlex.
- Generate and persist single-paper Deep Paper Cards through `POST /projects/{project_id}/paper-cards`.
- Generate research decision artifacts through `POST /projects/{project_id}/research-decisions`.

## CLI

The CLI makes local usage simple:

```text
scholarflow init
scholarflow start
scholarflow stop
scholarflow status
scholarflow ask "VLM hallucination benchmark"
scholarflow plan "我想做多模态可信评测方向"
```

Phase 4 implements the first four commands only. The CLI is not the core product logic. It starts services, manages local configuration, and provides a lightweight command surface.

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

The CLI launches the API with `SCHOLARFLOW_DB_PATH=<workspace>/cache/scholarflow.sqlite3` and launches the Web UI with `VITE_SCHOLARFLOW_API_BASE_URL` pointing to the selected API host and port. Service logs are written to the workspace `logs/` directory.

## Agent Core

ScholarFlow should borrow the following ideas from Claude Code-like systems:

- Agent Loop: the model alternates between reasoning, tool selection, tool execution, and artifact updates.
- Plan Mode: the agent creates a research plan before taking expensive actions.
- Tool Registry: every callable research capability has an explicit schema and execution contract.
- Permission Gates: sensitive operations such as sending data to external APIs or writing files should be explicit.
- Timeline: every important action becomes a visible event.
- Memory: user preferences and project decisions are reusable across sessions.
- Skills: research workflows such as deep paper reading, novelty check, and reproduction planning can be packaged.
- Sub-Agents: literature, reading, skeptic, novelty, and experiment roles can work on separate subtasks.
- MCP-Style Integrations: Zotero, GitHub, Hugging Face, Papers with Code, and local file tools can be added without rewriting the core loop.

Current Phase 5 implementation:

- `ModelProvider` abstraction.
- `DeepSeekProvider` integration boundary using the configured DeepSeek model name.
- `ToolRegistry`.
- `agent_runs` table.
- `POST /agent/plan`.
- `POST /agent/runs/{run_id}/execute`.
- Minimal tools: `create_plan`, `search_mock_papers`, `save_artifact`, `update_timeline`.

The current provider path is deterministic and local-first. `DeepSeekProvider` is the provider boundary, not a live external model call in Phase 5.

## Model Provider Strategy

The implementation should define a provider abstraction before binding to a specific model.

Preferred default:

- `deepseek-v4-pro`: planning, deep paper reading, novelty checking, follow-up idea generation.
- `deepseek-v4-flash`: query expansion, classification, extraction, short summaries.

Future providers should be swappable through configuration. Phase 5 stores the provider name on each `agent_run`; live external model calls are intentionally deferred.

## Research Tools

Initial tool categories:

- Direction understanding.
- Literature retrieval: Phase 6 implements arXiv and OpenAlex adapters behind `POST /projects/{project_id}/literature/search`.
- Paper metadata normalization.
- PDF parsing.
- Paper card generation: Phase 7 implements deterministic single-paper card generation with Markdown and JSON artifacts.
- Gap analysis.
- Novelty checking.
- Minimal reproduction planning.
- Experiment planning: Phase 8 implements deterministic artifact generation for baseline, dataset, metrics, ablations, resource estimates, success criteria, and failure criteria.
- Artifact save and diff.

Every tool should return structured data where possible.

## Core Data Objects

Planned entities:

- Project: a research workspace.
- Paper: metadata, source links, code links, tags, relevance score.
- Artifact: Markdown or JSON output saved by the agent.
- PaperCard: structured deep analysis for one paper.
- Session: one agent run or conversation.
- ToolEvent: one visible tool call or system action.
- AgentRun: one plan-and-confirm execution unit.
- ExperimentPlan: proposed reproduction or ablation plan.

## Evidence And Integrity

ScholarFlow must avoid unsupported research claims.

Expected behavior:

- Link claims to paper sections, metadata, code repositories, or experiment outputs.
- Distinguish paper claims from the agent's interpretation.
- Mark uncertain conclusions.
- Preserve search queries and retrieval sources.
- Avoid inventing citations, datasets, metrics, or experimental results.

The Phase 6 paper table artifact preserves expanded queries, source API names, source URLs, relevance reasons, and retrieval warnings. Phase 7 paper-card artifacts preserve the 12 sections, weakest assumption, minimal reproduction, counterexample, and follow-up idea in structured JSON. Phase 8 decision artifacts preserve true/engineering/pseudo gap labels, novelty risk, feasibility, and experiment plans.

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
