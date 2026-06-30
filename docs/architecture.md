# ScholarFlow Architecture

This document describes the target architecture and the current v0.1.0 public preview.

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

Current v0.1.0 entry points:

- `apps/web`: React research workspace with API-aware project, timeline, paper, and artifact state.
- `apps/cli`: Node CLI with workspace initialization and Web/API service management.
- `services/api`: FastAPI app with SQLite persistence, the first minimal agent loop, literature retrieval adapters, direction-level paper review, paper memory retrieval, single-paper card generation, and research decision generation.
- `packages/schemas`: shared TypeScript API contracts.
- `.github`: CI, Issue templates, and pull request template for open-source contribution.
- `examples/workflows`: public-safe example artifacts.

## Web UI

The web UI should expose the research workflow, not hide it behind a single chat box.

Planned layout:

- Project Navigator: projects, papers, artifacts, notes, experiments.
- Agent Workspace: user task, agent plan, current step, messages.
- Artifact Preview: paper tables, paper cards, gap boards, experiment plans, diffs.
- Tool Timeline: retrieval queries, filters, model calls, artifact writes, errors.

The v0.1.0 implementation reads and writes local API data for projects, papers, artifacts, sessions, tool events, agent runs, paper cards, paper memories, and direction memories. It can retrieve paper candidates from arXiv/OpenAlex, run a direction-level review over 10 recent high-relevance papers per round, extract PaperSignals from title/abstract/pasted text, generate 12-section Deep Paper Cards, build a searchable Paper Memory Bank, retrieve 3-8 relevant paper memories for follow-up questions, and turn those assets into a Gap Board, Idea Validation Report, and Experiment Plan. It intentionally does not download PDFs, parse full-paper PDFs in bulk, or run training jobs yet.

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
- `paper_memories`
- `direction_memories`
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

Current model-provider implementation:

- `ModelProvider` abstraction.
- `OpenRouterProvider` as the default provider, using `OPENROUTER_MODEL=minimax/minimax-m2.5` unless overridden.
- `DeepSeekProvider` as an optional fallback provider.
- `ToolRegistry`.
- `agent_runs` table.
- `POST /agent/plan`.
- `POST /agent/runs/{run_id}/execute`.
- Default tools: `literature_search`, `direction_review`, `research_memory_query`, `research_decision`, `save_artifact`, `update_timeline`.
- Demo tool: `search_mock_papers` remains registered for offline demos and is marked as Demo Mode in the UI when used.

When `OPENROUTER_API_KEY` is available, Research Plan Mode calls the OpenRouter OpenAI-compatible chat completions API. Without a key or after an API failure, ScholarFlow falls back to the deterministic local planner so local development and CI remain stable.

## Model Provider Strategy

The implementation should define a provider abstraction before binding to a specific model.

Preferred default:

- `minimax/minimax-m2.5`: default planning model through OpenRouter.
- `qwen/qwen3-embedding-8b`: configured RAG embedding model alias for future evidence retrieval workflows.

Providers remain swappable through configuration. ScholarFlow stores the provider name on each `agent_run` so artifacts can show whether a plan came from OpenRouter, DeepSeek, or local fallback.

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

## Core Data Objects

Planned entities:

- Project: a research workspace.
- Paper: metadata, source links, code links, tags, relevance score.
- Artifact: Markdown or JSON output saved by the agent.
- PaperCard: structured deep analysis for one paper.
- BaselineMap: comparative context used by direction review and memory.
- ResearchSight: structured critique attached to one paper reading.
- EvidenceSnippet / EvidencePack: metadata, abstract, and paper-card snippets that ground a critique, plus confidence and missing evidence.
- PaperMemory: searchable compressed record created from a direction-review paper card.
- DirectionMemory: cumulative summary over up to 30 paper memories for one research direction.
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
- Surface confidence and missing evidence when a critique is based only on metadata, abstract, or generated paper-card content.
- Preserve search queries and retrieval sources.
- Avoid inventing citations, datasets, metrics, or experimental results.

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
