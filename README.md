# ScholarFlow

ScholarFlow is a Chinese-first AI research workflow agent for students and researchers who need to turn a vague research direction into traceable research assets: paper tables, deep paper cards, gap analysis, novelty checks, reproduction plans, experiment plans, and writing-ready evidence.

ScholarFlow is not a paper search demo. The goal is to build a local-first research workspace that helps users answer a more practical question:

> Given a keyword or rough idea in AI research, what should I read, what is the real gap, what can I reproduce in one week, and what research direction is worth trying next?

## Current Status

This repository is in Phase 8: Gap / Novelty / Experiment Plan.

The current codebase includes a React research workspace, a FastAPI service backed by SQLite, a Node CLI for local workspace and service management, a minimal research agent loop, real arXiv/OpenAlex literature retrieval, single-paper Deep Paper Card generation, research gap/novelty/experiment planning, and a shared schema package. It does not include real model API calls, PDF downloading, automatic training, batch paper reading, or automatic paper writing yet.

See [IMPLEMENTATION_PHASES.md](./IMPLEMENTATION_PHASES.md) for the staged build plan.

## Quick Start

Prerequisites:

- Node.js 20+
- npm 10+
- Python 3.11+

Install JavaScript dependencies:

```bash
npm install
```

Install Python API dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r services/api/requirements.txt
```

Initialize the local ScholarFlow workspace:

```bash
npm --workspace @scholarflow/cli run start -- init
```

Start the Web UI and API together:

```bash
npm --workspace @scholarflow/cli run start -- start
```

Check or stop local services:

```bash
npm --workspace @scholarflow/cli run start -- status
npm --workspace @scholarflow/cli run start -- stop
```

The default local workspace is `~/.scholarflow`. To use another location:

```bash
SCHOLARFLOW_WORKSPACE=/path/to/workspace npm --workspace @scholarflow/cli run start -- init
```

For backend-only development, initialize the SQLite database directly:

```bash
npm run db:init
```

For manual development, run the web app:

```bash
npm run dev:web
```

Run the API service:

```bash
npm run dev:api
```

For reload-based local API development, use `npm run dev:api:reload`.

Check the CLI entry:

```bash
npm run version:cli
```

Check the API health handler without starting a server:

```bash
npm run health:api
```

## Target Users

ScholarFlow is initially designed for:

- AI-oriented master students.
- Senior undergraduate students entering research training.
- Researchers who need a structured workflow for literature review, idea validation, and experiment planning.

The first product language is Chinese, with technical terms kept in English when that is clearer.

## Core Workflow

The intended MVP workflow is:

```text
Keyword / vague idea
  -> direction understanding
  -> paper retrieval and filtering
  -> structured paper table
  -> deep paper card
  -> gap analysis
  -> novelty check
  -> minimal reproduction plan
  -> experiment plan
  -> reusable research artifacts
```

## Planned Capabilities

- Direction understanding for AI research topics such as VLM, LLM, trustworthy AI, multimodal alignment, hallucination evaluation, benchmark design, PEFT, and agent systems.
- Literature retrieval from arXiv, Semantic Scholar, OpenAlex, Crossref, GitHub, Papers with Code, and optional domain-specific sources.
- Deep paper analysis based on a fixed 12-part paper-reading protocol.
- Research gap and novelty checking before proposing ideas.
- One-week minimal reproduction planning for selected claims.
- Experiment planning, ablation design, result interpretation, and writing support.
- Local workspace for long-term research assets.
- Web UI inspired by coding agents: plan checklist, tool timeline, artifact preview, and artifact diffs.
- CLI for local project initialization and service startup.

## Current Web Workspace

The current web app provides a Claude Code-style research workspace:

- Project Navigator.
- Agent Workspace.
- Artifact Preview.
- Dashboard.
- New Project.
- Paper Table.
- Paper Reader.
- Gap Board.
- Experiment Planner.
- Static plan checklist and tool timeline.

When the API is running, the web app reads projects, papers, artifacts, and session timeline events from SQLite. If the API is not running, it falls back to static mock content.

The Dashboard also includes the first Research Plan Mode:

- Enter a research task.
- Generate a persisted plan artifact.
- Confirm execution.
- Run mock tools through the backend Tool Registry.
- Save the result artifact.
- Refresh the visible timeline from SQLite.

The Paper Table page can run the first real literature retrieval flow:

- Expand a keyword into related search queries.
- Retrieve candidates from arXiv and OpenAlex.
- Deduplicate and rank papers.
- Save a structured `paper_table.md` artifact.
- Persist paper metadata to SQLite.

The Paper Reader page can generate the first 12-section Deep Paper Card:

- Select a retrieved paper.
- Optionally paste an abstract, method, or experiment excerpt.
- Generate the fixed 12-part paper-reading artifact.
- Save Markdown and JSON outputs to SQLite.
- Preserve weakest assumption and one-week reproduction fields for later gap analysis.

The Gap Board and Experiment Planner pages can generate the first decision bundle:

- Distinguish true gaps, engineering gaps, and pseudo gaps.
- Produce an idea validation report with novelty risk and feasibility.
- Generate an experiment plan with baseline, dataset, metrics, ablations, resources, success criteria, and failure criteria.
- Save `gap_board.md`, `idea_validation_report.md`, and `experiment_plan.md` artifacts.

## Current CLI

Phase 4 provides the local command entry:

```text
scholarflow init
scholarflow start
scholarflow status
scholarflow stop
```

The CLI creates this local workspace shape:

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

`start` launches both the FastAPI service and Vite web app, writes service logs under `logs/`, and stores process state under `cache/services.json`. The API database path is injected through `SCHOLARFLOW_DB_PATH`, so local data stays outside Git by default.

## Current API

Phase 3, Phase 5, Phase 6, Phase 7, and Phase 8 provide these local API endpoints:

```text
GET  /health
GET  /projects
POST /projects
GET  /projects/{project_id}
GET  /projects/{project_id}/papers
GET  /projects/{project_id}/artifacts
POST /artifacts
GET  /artifacts/{artifact_id}
GET  /projects/{project_id}/sessions
GET  /sessions/{session_id}/timeline
GET  /projects/{project_id}/timeline
POST /agent/plan
POST /agent/runs/{run_id}/execute
POST /projects/{project_id}/literature/search
POST /projects/{project_id}/paper-cards
POST /projects/{project_id}/research-decisions
```

The default development SQLite database path is `services/api/.data/scholarflow.sqlite3`, and it is ignored by Git. When launched by the CLI, the database path is `<workspace>/cache/scholarflow.sqlite3`.

## Current Agent Core

Phase 5 provides the first minimal agent loop:

- `ModelProvider` abstraction.
- `DeepSeekProvider` integration boundary using `DEEPSEEK_MODEL`, defaulting to `deepseek-v4-pro`.
- `ToolRegistry`.
- `create_plan`.
- `search_mock_papers`.
- `save_artifact`.
- `update_timeline`.

The current agent is deterministic and local-first. It does not call the DeepSeek API yet; the provider boundary exists so the later real model integration can replace the local planner without changing the workflow API.

## Current Literature Retrieval

Phase 6 provides a real paper-table workflow:

- arXiv API retrieval.
- OpenAlex Works retrieval.
- Query expansion for AI research terms such as VLM, hallucination, multimodal evaluation, and research agents.
- Title-based deduplication.
- Lightweight relevance scoring using keyword overlap, recency, source, and title matches.
- SQLite persistence for structured paper rows.
- Markdown and JSON paper-table artifact output.

The current retrieval flow does not download PDFs, build citation graphs, or generate deep paper cards. Those are later phases.

## Design Principles

- Research workflow first, chat second.
- Every important output should become an artifact, not only a chat message.
- Claims must be linked to evidence from papers, code, experiments, or user-provided files.
- The agent should plan before acting.
- The system should expose its tool calls, search queries, filtering decisions, and intermediate reasoning artifacts.
- Model providers should be replaceable. DeepSeek is the preferred default target, but ScholarFlow should not be locked to one model.

## Planned Architecture

The target architecture is:

```text
apps/web          React research workspace
apps/cli          Local command entry
services/api      Backend API and agent orchestration service
packages/schemas  Shared data contracts
docs              Architecture, protocols, and product notes
examples          Example workflows and artifacts
```

For details, see [docs/architecture.md](./docs/architecture.md).

## Deep Paper Card

ScholarFlow's paper-reading workflow is built around a 12-part deep paper card:

1. Research problem and background.
2. Prior work and limitations.
3. Reconstructed author reasoning path.
4. Core intuition.
5. Method pipeline with an example.
6. Math and theory explanation.
7. Experiment logic and claim validation.
8. Take-aways.
9. Weakest assumption.
10. One-week minimal reproduction.
11. Counterexample design.
12. Non-incremental follow-up idea.

For the full protocol, see [docs/deep-paper-card.md](./docs/deep-paper-card.md).

Phase 7 implements this protocol as a single-paper workflow. The current generator is deterministic and local-first: it uses title, metadata, abstract, and optional user-pasted text. It does not claim to read a full PDF unless the user provides that text, and it does not fabricate formulas or experimental numbers.

## Current Research Decisions

Phase 8 turns reading artifacts into decision artifacts:

- `gap_board.md`
- `idea_validation_report.md`
- `experiment_plan.md`

The current generator is deterministic and local-first. It uses project metadata, ranked papers, and paper cards to propose a focused research direction. It does not run training, download datasets, or claim experimental results.

## Model Strategy

The preferred default model target is DeepSeek:

- `deepseek-v4-pro` for planning, paper analysis, novelty checking, and long-form reasoning.
- `deepseek-v4-flash` for fast classification, query expansion, extraction, and lightweight summaries.

The implementation should use a provider abstraction so future users can swap models without rewriting the agent workflow.

## Security And Privacy

ScholarFlow will handle API keys, local papers, notes, experiment results, and potentially unpublished research ideas. The repository therefore treats these as non-committable by default:

- API keys must stay in environment variables or local config files.
- Local papers, PDFs, databases, logs, vector stores, and user workspaces are ignored by Git.
- Public examples should use synthetic or openly licensed data.
- Research artifacts should preserve source links and avoid unsupported claims.

## License

ScholarFlow is released under the MIT License. See [LICENSE](./LICENSE).
