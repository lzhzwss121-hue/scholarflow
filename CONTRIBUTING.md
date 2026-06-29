# Contributing To ScholarFlow

ScholarFlow is an early-stage research workflow agent. Contributions should keep the project focused on helping users produce traceable research assets, not just longer chat responses.

## Project Scope

Good contributions should improve at least one of these areas:

- AI research workflow design.
- Literature retrieval and filtering.
- Paper-reading quality.
- Evidence tracking and citation reliability.
- Novelty checking.
- Reproduction and experiment planning.
- Local-first workspace reliability.
- Clear Chinese-first user experience.

Avoid adding broad features that do not support the research workflow.

## Development Principles

- Keep changes scoped to the current implementation phase.
- Prefer explicit data structures over loosely formatted text.
- Store important outputs as artifacts.
- Preserve evidence links for claims.
- Keep model providers replaceable.
- Do not commit local papers, API keys, logs, databases, vector stores, or user workspaces.

## Before Opening A Pull Request

Make sure the change:

- Matches the current roadmap phase.
- Updates documentation when behavior or scope changes.
- Does not introduce secrets or private user data.
- Includes focused tests when implementation code exists.
- Keeps Chinese-first product copy unless the target file is explicitly English-only.

## Commit Style

Use short, descriptive commits:

```text
docs: add deep paper card protocol
feat(api): add project health endpoint
fix(web): prevent artifact panel overflow
```

## Privacy And Research Integrity

ScholarFlow may process unpublished ideas, local PDFs, experiment outputs, and private notes. Contributors must treat these as sensitive by default.

Do not add example data from private papers, private repositories, personal transcripts, lab application materials, or unpublished research without explicit permission.

