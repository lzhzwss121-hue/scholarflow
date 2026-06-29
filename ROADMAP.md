# ScholarFlow Roadmap

This roadmap follows the staged implementation plan in [IMPLEMENTATION_PHASES.md](./IMPLEMENTATION_PHASES.md). Each phase should be completed and reviewed before the next phase starts.

## Phase 0: Open-Source Repository Boundary

Goal: make ScholarFlow understandable as an open-source product before writing business code.

Deliverables:

- README.
- License.
- Roadmap.
- Contribution guide.
- Environment variable example.
- Git ignore rules.
- Architecture note.
- Deep paper card protocol.

Status: complete.

## Phase 1: Monorepo Skeleton

Goal: create the project structure for frontend, backend, CLI, and shared schemas.

Planned deliverables:

- React + Vite empty web app.
- FastAPI empty service.
- Node CLI empty entry.
- Shared schema package placeholder.
- Root development scripts.

Status: complete.

## Phase 2: Static Web Workspace

Goal: build a static research workspace shell inspired by coding agents.

Planned deliverables:

- Project navigator.
- Agent workspace.
- Artifact preview.
- Dashboard.
- New project page.
- Paper table page.
- Paper reader page.
- Gap board page.
- Experiment planner page.
- Static mock data.

Status: complete.

## Phase 3: Backend API And Data Model

Goal: create the minimal persistent research workspace.

Planned deliverables:

- SQLite database.
- Tables for projects, papers, artifacts, paper cards, sessions, and tool events.
- API endpoints for creating projects, reading projects, saving artifacts, and reading timelines.

Status: complete.

## Phase 4: CLI And Local Workspace

Goal: provide a local-first command entry.

Planned deliverables:

- `scholarflow init`.
- `scholarflow start`.
- `scholarflow stop`.
- `scholarflow status`.
- Default local workspace under `~/.scholarflow`.

Status: complete.

## Phase 5: Minimal Agent Core

Goal: implement the first working research agent loop.

Planned deliverables:

- Model provider abstraction.
- DeepSeek provider.
- Tool registry.
- Minimal research tools.
- Research Plan Mode.
- Tool timeline persistence.

Status: complete.

## Phase 6: Literature Retrieval MVP

Goal: turn keywords into a real paper table.

Planned deliverables:

- arXiv retrieval.
- OpenAlex or Semantic Scholar retrieval.
- Query expansion.
- Paper deduplication.
- Relevance ranking.
- Structured paper table artifact.

Status: complete.

## Phase 7: Deep Paper Card

Goal: generate the first complete ScholarFlow paper-reading artifact.

Planned deliverables:

- PDF or abstract ingestion.
- Structured 12-part analysis.
- Citation-aware output.
- JSON and Markdown paper card artifacts.

Status: complete.

## Phase 8: Gap, Novelty, And Experiment Planning

Goal: move from reading papers to making research decisions.

Planned deliverables:

- Gap board.
- Novelty check report.
- Counterexample design.
- One-week minimal reproduction plan.
- Experiment planning artifact.

## Phase 9: Open-Source Release Polish

Goal: prepare ScholarFlow for public use and contribution.

Planned deliverables:

- Installation documentation.
- Example project.
- Screenshots or demo video.
- Issue templates.
- Pull request template.
- Security policy.
- First public release tag.
