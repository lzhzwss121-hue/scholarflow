# ScholarFlow

ScholarFlow is a Chinese-first AI research workflow agent for students and researchers who need to turn a vague research direction into traceable research assets: paper tables, deep paper cards, gap analysis, novelty checks, reproduction plans, experiment plans, and writing-ready evidence.

ScholarFlow is not a paper search demo. The goal is to build a local-first research workspace that helps users answer a more practical question:

> Given a keyword or rough idea in AI research, what should I read, what is the real gap, what can I reproduce in one week, and what research direction is worth trying next?

## Current Status

This repository is in Phase 3: backend API and SQLite data model.

The current codebase includes a React research workspace, a FastAPI service backed by SQLite, a Node CLI entry, and a shared schema package. It does not include model API calls, real paper retrieval, or agent auto-execution yet.

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

Initialize the SQLite workspace:

```bash
npm run db:init
```

Run the web app:

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
- Optional CLI for local project initialization and service startup.

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

## Current API

Phase 3 provides these local API endpoints:

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
```

The default SQLite database path is `services/api/.data/scholarflow.sqlite3`, and it is ignored by Git.

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
