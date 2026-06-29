# ScholarFlow

[English](./README.md) | [简体中文](./README.zh-CN.md)

ScholarFlow is a Chinese-first AI research workflow agent for students and researchers working in AI. It helps turn a keyword, paper topic, or rough research idea into reusable research artifacts instead of leaving everything in a chat transcript.

The project is designed for workflows such as:

- Finding and organizing papers for an AI research direction.
- Producing structured paper tables and deep paper-reading notes.
- Identifying real research gaps instead of vague topic ideas.
- Planning one-week reproduction experiments.
- Designing baselines, datasets, metrics, ablations, and success criteria.
- Saving research outputs as traceable local artifacts.

## How ScholarFlow Helps

ScholarFlow focuses on the research process after a user gives a keyword or rough direction:

```text
Keyword / rough idea
  -> understand the research direction
  -> retrieve and rank papers
  -> generate a structured paper table
  -> create deep paper cards
  -> analyze gaps and novelty risk
  -> plan a minimal reproduction
  -> design an experiment plan
  -> save reusable research artifacts
```

The default product language is Chinese, while technical terms such as VLM, LLM, Agent, Artifact, Gap, Baseline, Metric, and Ablation can remain in English when they are clearer.

## Get Started

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

Start the Web UI and API:

```bash
npm --workspace @scholarflow/cli run start -- start
```

By default, the CLI starts:

- Web UI: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- Local workspace: `~/.scholarflow`

Check or stop local services:

```bash
npm --workspace @scholarflow/cli run start -- status
npm --workspace @scholarflow/cli run start -- stop
```

Use a custom workspace path:

```bash
SCHOLARFLOW_WORKSPACE=/path/to/workspace npm --workspace @scholarflow/cli run start -- init
SCHOLARFLOW_WORKSPACE=/path/to/workspace npm --workspace @scholarflow/cli run start -- start
```

## Development Commands

Run the web app only:

```bash
npm run dev:web
```

Run the API only:

```bash
npm run dev:api
```

Initialize the development database:

```bash
npm run db:init
```

Run local checks:

```bash
npm run check
npm run build
python3 -m compileall services/api/src/scholarflow_api
```

Check the API health handler after installing Python dependencies:

```bash
npm run health:api
```

## Local Data

ScholarFlow is local-first. The CLI stores runtime data under `~/.scholarflow` by default:

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

Do not commit API keys, local databases, PDFs, logs, user artifacts, private notes, or unpublished research materials.
