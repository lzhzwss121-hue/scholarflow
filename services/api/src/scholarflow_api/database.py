from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / ".data" / "scholarflow.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def get_db_path() -> Path:
    configured = os.getenv("SCHOLARFLOW_DB_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_DB_PATH


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                keyword TEXT NOT NULL DEFAULT '',
                field TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT 'zh-CN',
                workflow TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL DEFAULT 'api',
                active_session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                authors TEXT NOT NULL DEFAULT '',
                abstract TEXT NOT NULL DEFAULT '',
                year TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT '',
                venue TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                relation TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'Medium',
                code TEXT NOT NULL DEFAULT '',
                relevance_score REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                content_markdown TEXT NOT NULL DEFAULT '',
                content_json TEXT NOT NULL DEFAULT '',
                diff TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS paper_cards (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                paper_id TEXT,
                artifact_id TEXT,
                sections_json TEXT NOT NULL DEFAULT '{}',
                weakest_assumption TEXT NOT NULL DEFAULT '',
                minimal_reproduction TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE SET NULL,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS agent_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                task TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'deepseek',
                mode TEXT NOT NULL DEFAULT 'plan',
                status TEXT NOT NULL DEFAULT 'planned',
                plan_json TEXT NOT NULL DEFAULT '{}',
                plan_artifact_id TEXT,
                result_artifact_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (plan_artifact_id) REFERENCES artifacts(id) ON DELETE SET NULL,
                FOREIGN KEY (result_artifact_id) REFERENCES artifacts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS tool_events (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                time_label TEXT NOT NULL,
                tool TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_papers_project_id ON papers(project_id);
            CREATE INDEX IF NOT EXISTS idx_artifacts_project_id ON artifacts(project_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
            CREATE INDEX IF NOT EXISTS idx_agent_runs_project_id ON agent_runs(project_id);
            CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id ON agent_runs(session_id);
            CREATE INDEX IF NOT EXISTS idx_tool_events_session_id ON tool_events(session_id);
            """
        )
        ensure_paper_columns(connection)
        seed_demo_project(connection)


def ensure_paper_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(papers)").fetchall()
    }
    columns = {
        "authors": "TEXT NOT NULL DEFAULT ''",
        "abstract": "TEXT NOT NULL DEFAULT ''",
        "source": "TEXT NOT NULL DEFAULT ''",
        "url": "TEXT NOT NULL DEFAULT ''",
        "relevance_score": "REAL NOT NULL DEFAULT 0",
    }
    for name, definition in columns.items():
        if name not in existing_columns:
            connection.execute(f"ALTER TABLE papers ADD COLUMN {name} {definition}")


def seed_demo_project(connection: sqlite3.Connection) -> None:
    existing = connection.execute(
        "SELECT id FROM projects WHERE id = ?",
        ("local-bootstrap",),
    ).fetchone()
    if existing:
        return

    now = utc_now()
    session_id = "session_bootstrap"
    connection.execute(
        """
        INSERT INTO projects (
            id, title, description, keyword, field, language, workflow, stage,
            active_session_id, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "local-bootstrap",
            "VLM Hallucination Benchmark",
            "从可信多模态评测出发，定位现有 benchmark 无法暴露的证据错误和 visual grounding 失败。",
            "VLM hallucination benchmark",
            "Trustworthy AI / Multimodal Evaluation",
            "zh-CN",
            "survey-to-experiment",
            "api",
            session_id,
            now,
            now,
        ),
    )

    seed_papers(connection, "local-bootstrap", now)
    seed_artifacts(connection, "local-bootstrap", now)
    seed_session(connection, "local-bootstrap", session_id, now)


def seed_papers(connection: sqlite3.Connection, project_id: str, now: str) -> None:
    papers = [
        (
            "object_hallucination",
            "Evaluating Object Hallucination in Large Vision-Language Models",
            "unknown",
            "",
            "2025",
            "Benchmark",
            "arXiv",
            "seed",
            "",
            "直接对应 hallucination evaluation",
            "High",
            "available",
            1.5,
        ),
        (
            "faithful_vqa",
            "Faithful Visual Question Answering Requires Grounded Evidence",
            "unknown",
            "",
            "2025",
            "Method",
            "ACL",
            "seed",
            "",
            "把答案正确性和证据一致性分开",
            "High",
            "partial",
            1.4,
        ),
        (
            "benchmark_bias",
            "Benchmark Bias in Multimodal Foundation Model Evaluation",
            "unknown",
            "",
            "2024",
            "Analysis",
            "NeurIPS",
            "seed",
            "",
            "解释评测集捷径和分布偏差",
            "High",
            "available",
            1.3,
        ),
        (
            "trustworthy_vlm_survey",
            "A Survey of Trustworthy Vision-Language Models",
            "unknown",
            "",
            "2026",
            "Survey",
            "arXiv",
            "seed",
            "",
            "补全研究图谱和术语",
            "Medium",
            "none",
            0.9,
        ),
    ]
    connection.executemany(
        """
        INSERT INTO papers (
            id, project_id, title, authors, abstract, year, type, venue, source, url,
            relation, priority, code, relevance_score, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                f"paper_{paper_suffix}" if project_id == "local-bootstrap" else f"{project_id}_paper_{paper_suffix}",
                project_id,
                title,
                authors,
                abstract,
                year,
                type_,
                venue,
                source,
                url,
                relation,
                priority,
                code,
                relevance_score,
                now,
            )
            for (
                paper_suffix,
                title,
                authors,
                abstract,
                year,
                type_,
                venue,
                source,
                url,
                relation,
                priority,
                code,
                relevance_score,
            ) in papers
        ],
    )


def seed_artifacts(connection: sqlite3.Connection, project_id: str, now: str) -> None:
    artifact_id = "artifact_research_overview"
    connection.execute(
        """
        INSERT INTO artifacts (
            id, project_id, title, kind, content_markdown, content_json, diff, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            project_id,
            "research_overview.md",
            "markdown",
            "# VLM Hallucination Benchmark\n\n- 方向：trustworthy VLM evaluation\n- 当前阶段：Backend API\n- 下一步：Agent Core 之前的数据持久化",
            json.dumps(
                {
                    "project": "vlm-hallucination-benchmark",
                    "stage": "api",
                    "source": "seed",
                },
                ensure_ascii=False,
                indent=2,
            ),
            "+ Added SQLite-backed artifact persistence",
            now,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO paper_cards (
            id, project_id, paper_id, artifact_id, sections_json, weakest_assumption,
            minimal_reproduction, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "paper_card_faithful_vqa",
            project_id,
            "paper_faithful_vqa",
            artifact_id,
            json.dumps({"sections": 12}, ensure_ascii=False),
            "人工证据标签足以代表模型真实视觉依据。",
            "一周内验证 answer accuracy 与 evidence consistency 是否分离。",
            now,
        ),
    )


def seed_session(connection: sqlite3.Connection, project_id: str, session_id: str, now: str) -> None:
    connection.execute(
        """
        INSERT INTO sessions (id, project_id, title, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, project_id, "Phase 3 Backend API Session", "active", now, now),
    )
    events = [
        ("event_schema", "13:42", "db.migrate", "done", "创建 projects、papers、artifacts、paper_cards、sessions、tool_events 表。"),
        ("event_seed", "13:45", "db.seed", "done", "写入本地示例项目、论文、artifact 和 session timeline。"),
        ("event_api", "13:49", "api.timeline", "running", "前端正在从 /sessions/{id}/timeline 读取工具事件。"),
        ("event_next", "Next", "api.artifact", "queued", "等待用户保存当前 artifact 后写入 SQLite。"),
    ]
    connection.executemany(
        """
        INSERT INTO tool_events (id, session_id, time_label, tool, status, summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [(event_id, session_id, time_label, tool, status, summary, now) for event_id, time_label, tool, status, summary in events],
    )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def main() -> None:
    init_db()
    print(get_db_path())


if __name__ == "__main__":
    main()
