# ScholarFlow Architecture

This document describes the target architecture and the current Phase 3 API-backed workspace.

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
  web/              React + Vite research workspace skeleton
  cli/              Local command entry skeleton
services/
  api/              FastAPI service skeleton
packages/
  schemas/          Shared TypeScript/Python-compatible contracts
docs/
  architecture.md
  deep-paper-card.md
examples/
  workflows/
```

Current Phase 3 entry points:

- `apps/web`: React research workspace with API-aware project, timeline, paper, and artifact state.
- `apps/cli`: Node CLI entry with `--version` and `status`.
- `services/api`: FastAPI app with SQLite persistence.
- `packages/schemas`: shared TypeScript API contracts.

## Web UI

The web UI should expose the research workflow, not hide it behind a single chat box.

Planned layout:

- Project Navigator: projects, papers, artifacts, notes, experiments.
- Agent Workspace: user task, agent plan, current step, messages.
- Artifact Preview: paper tables, paper cards, gap boards, experiment plans, diffs.
- Tool Timeline: retrieval queries, filters, model calls, artifact writes, errors.

The Phase 3 implementation reads and writes local API data for projects, papers, artifacts, sessions, and tool events. It intentionally does not call a model provider or a real paper retrieval API.

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

## CLI

The CLI should make local usage simple:

```text
scholarflow init
scholarflow start
scholarflow stop
scholarflow status
scholarflow ask "VLM hallucination benchmark"
scholarflow plan "我想做多模态可信评测方向"
```

The CLI is not the core product logic. It starts services, manages local configuration, and provides a lightweight command surface.

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

## Model Provider Strategy

The implementation should define a provider abstraction before binding to a specific model.

Preferred default:

- `deepseek-v4-pro`: planning, deep paper reading, novelty checking, follow-up idea generation.
- `deepseek-v4-flash`: query expansion, classification, extraction, short summaries.

Future providers should be swappable through configuration.

## Research Tools

Initial tool categories:

- Direction understanding.
- Literature retrieval.
- Paper metadata normalization.
- PDF parsing.
- Paper card generation.
- Gap analysis.
- Novelty checking.
- Minimal reproduction planning.
- Experiment planning.
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
- ExperimentPlan: proposed reproduction or ablation plan.

## Evidence And Integrity

ScholarFlow must avoid unsupported research claims.

Expected behavior:

- Link claims to paper sections, metadata, code repositories, or experiment outputs.
- Distinguish paper claims from the agent's interpretation.
- Mark uncertain conclusions.
- Preserve search queries and retrieval sources.
- Avoid inventing citations, datasets, metrics, or experimental results.

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
