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
                pdf_url TEXT NOT NULL DEFAULT '',
                relation TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'Medium',
                code TEXT NOT NULL DEFAULT '',
                relevance_score REAL NOT NULL DEFAULT 0,
                relevance_quality TEXT NOT NULL DEFAULT 'medium',
                matched_terms_json TEXT NOT NULL DEFAULT '[]',
                review_required INTEGER NOT NULL DEFAULT 0,
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
                research_sight_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE SET NULL,
                FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS paper_memories (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                paper_id TEXT,
                direction TEXT NOT NULL DEFAULT '',
                round_index INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL,
                authors TEXT NOT NULL DEFAULT '',
                year TEXT NOT NULL DEFAULT '',
                venue TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                abstract_translation TEXT NOT NULL DEFAULT '',
                sections_json TEXT NOT NULL DEFAULT '[]',
                weakest_assumption TEXT NOT NULL DEFAULT '',
                minimal_reproduction TEXT NOT NULL DEFAULT '',
                counterexample TEXT NOT NULL DEFAULT '',
                follow_up_idea TEXT NOT NULL DEFAULT '',
                why_selected TEXT NOT NULL DEFAULT '',
                research_sight_json TEXT NOT NULL DEFAULT '{}',
                memory_text TEXT NOT NULL DEFAULT '',
                keywords_json TEXT NOT NULL DEFAULT '[]',
                self_read_priority INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS direction_memories (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                total_papers INTEGER NOT NULL DEFAULT 0,
                round_count INTEGER NOT NULL DEFAULT 0,
                summary TEXT NOT NULL DEFAULT '',
                paper_ids_json TEXT NOT NULL DEFAULT '[]',
                baseline_map_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
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
                provider TEXT NOT NULL DEFAULT 'openrouter',
                mode TEXT NOT NULL DEFAULT 'plan',
                status TEXT NOT NULL DEFAULT 'planned',
                plan_json TEXT NOT NULL DEFAULT '{}',
                plan_artifact_id TEXT,
                result_artifact_id TEXT,
                cancellation_requested INTEGER NOT NULL DEFAULT 0,
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

            CREATE TABLE IF NOT EXISTS retrieval_cache (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                query TEXT NOT NULL,
                max_results INTEGER NOT NULL,
                response_json TEXT NOT NULL DEFAULT '[]',
                errors_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_papers_project_id ON papers(project_id);
            CREATE INDEX IF NOT EXISTS idx_artifacts_project_id ON artifacts(project_id);
            CREATE INDEX IF NOT EXISTS idx_paper_memories_project_id ON paper_memories(project_id);
            CREATE INDEX IF NOT EXISTS idx_paper_memories_direction ON paper_memories(project_id, direction);
            CREATE INDEX IF NOT EXISTS idx_direction_memories_project_id ON direction_memories(project_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
            CREATE INDEX IF NOT EXISTS idx_agent_runs_project_id ON agent_runs(project_id);
            CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id ON agent_runs(session_id);
            CREATE INDEX IF NOT EXISTS idx_tool_events_session_id ON tool_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_retrieval_cache_lookup ON retrieval_cache(source, query, max_results, created_at);
            """
        )
        ensure_paper_columns(connection)
        ensure_paper_card_columns(connection)
        ensure_paper_memory_columns(connection)
        ensure_direction_memory_columns(connection)
        ensure_agent_run_columns(connection)
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
        "pdf_url": "TEXT NOT NULL DEFAULT ''",
        "relevance_score": "REAL NOT NULL DEFAULT 0",
        "relevance_quality": "TEXT NOT NULL DEFAULT 'medium'",
        "matched_terms_json": "TEXT NOT NULL DEFAULT '[]'",
        "review_required": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in columns.items():
        if name not in existing_columns:
            connection.execute(f"ALTER TABLE papers ADD COLUMN {name} {definition}")


def ensure_paper_card_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(paper_cards)").fetchall()
    }
    columns = {
        "research_sight_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for name, definition in columns.items():
        if name not in existing_columns:
            connection.execute(f"ALTER TABLE paper_cards ADD COLUMN {name} {definition}")


def ensure_paper_memory_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(paper_memories)").fetchall()
    }
    columns = {
        "research_sight_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for name, definition in columns.items():
        if name not in existing_columns:
            connection.execute(f"ALTER TABLE paper_memories ADD COLUMN {name} {definition}")


def ensure_direction_memory_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(direction_memories)").fetchall()
    }
    columns = {
        "baseline_map_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for name, definition in columns.items():
        if name not in existing_columns:
            connection.execute(f"ALTER TABLE direction_memories ADD COLUMN {name} {definition}")


def ensure_agent_run_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(agent_runs)").fetchall()
    }
    columns = {
        "cancellation_requested": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in columns.items():
        if name not in existing_columns:
            connection.execute(f"ALTER TABLE agent_runs ADD COLUMN {name} {definition}")


def seed_demo_project(connection: sqlite3.Connection) -> None:
    existing = connection.execute(
        "SELECT id, title FROM projects WHERE id = ?",
        ("local-bootstrap",),
    ).fetchone()
    if existing:
        legacy_paper = connection.execute(
            """
            SELECT id FROM papers
            WHERE project_id = ? AND title = ?
            """,
            ("local-bootstrap", "Evaluating Object Hallucination in Large Vision-Language Models"),
        ).fetchone()
        if existing["title"] == "VLM Hallucination Benchmark" or legacy_paper:
            update_legacy_demo_project(connection)
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
            "AI 研究方向探索示例",
            "输入你自己的研究方向后，ScholarFlow 会帮助你检索论文、精读论文、整理记忆并生成 gap 与实验计划。",
            "你的研究方向关键词",
            "Artificial Intelligence",
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


def update_legacy_demo_project(connection: sqlite3.Connection) -> None:
    now = utc_now()
    connection.execute(
        """
        UPDATE projects
        SET title = ?, description = ?, keyword = ?, field = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            "AI 研究方向探索示例",
            "输入你自己的研究方向后，ScholarFlow 会帮助你检索论文、精读论文、整理记忆并生成 gap 与实验计划。",
            "你的研究方向关键词",
            "Artificial Intelligence",
            now,
            "local-bootstrap",
        ),
    )
    connection.execute(
        """
        UPDATE artifacts
        SET content_markdown = ?, content_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            "# AI 研究方向探索示例\n\n- 先在新建项目页输入自己的研究方向\n- 再检索近三年论文并执行方向精读\n- 最后生成 Paper Memory、Gap Board 和 Experiment Plan",
            json.dumps(
                {
                    "project": "ai-research-direction-example",
                    "stage": "api",
                    "source": "seed",
                },
                ensure_ascii=False,
                indent=2,
            ),
            now,
            "artifact_research_overview",
        ),
    )
    demo_papers = [
        (
            "Synthetic Example: Research Workflow Agents for Literature Review",
            "System",
            "Demo",
            "展示从方向到论文表的工作流",
            "demo",
            "paper_object_hallucination",
        ),
        (
            "Synthetic Example: Memory-Augmented Paper Reading",
            "Method",
            "Demo",
            "展示 Paper Memory 如何支持后续问答",
            "demo",
            "paper_faithful_vqa",
        ),
        (
            "Synthetic Example: Evidence-Bounded Gap Analysis",
            "Protocol",
            "Demo",
            "展示如何从论文证据生成研究 gap",
            "demo",
            "paper_benchmark_bias",
        ),
        (
            "Synthetic Example: Selecting Reproducible Experiment Anchors",
            "Guide",
            "Demo",
            "展示实验计划如何避免选择综述论文",
            "demo",
            "paper_trustworthy_vlm_survey",
        ),
    ]
    connection.executemany(
        """
        UPDATE papers
        SET title = ?, type = ?, venue = ?, relation = ?, code = ?
        WHERE id = ?
        """,
        demo_papers,
    )


def seed_papers(connection: sqlite3.Connection, project_id: str, now: str) -> None:
    papers = [
        (
            "research_agent_workflow",
            "Synthetic Example: Research Workflow Agents for Literature Review",
            "unknown",
            "",
            "2025",
            "System",
            "Demo",
            "seed",
            "",
            "展示从方向到论文表的工作流",
            "High",
            "demo",
            1.5,
        ),
        (
            "paper_memory_retrieval",
            "Synthetic Example: Memory-Augmented Paper Reading",
            "unknown",
            "",
            "2025",
            "Method",
            "Demo",
            "seed",
            "",
            "展示 Paper Memory 如何支持后续问答",
            "High",
            "demo",
            1.4,
        ),
        (
            "gap_analysis_protocol",
            "Synthetic Example: Evidence-Bounded Gap Analysis",
            "unknown",
            "",
            "2024",
            "Protocol",
            "Demo",
            "seed",
            "",
            "展示如何从论文证据生成研究 gap",
            "High",
            "demo",
            1.3,
        ),
        (
            "experiment_anchor_selection",
            "Synthetic Example: Selecting Reproducible Experiment Anchors",
            "unknown",
            "",
            "2026",
            "Guide",
            "Demo",
            "seed",
            "",
            "展示实验计划如何避免选择综述论文",
            "Medium",
            "demo",
            0.9,
        ),
    ]
    connection.executemany(
        """
        INSERT INTO papers (
            id, project_id, title, authors, abstract, year, type, venue, source, url,
            relation, priority, code, relevance_score, relevance_quality, matched_terms_json,
            review_required, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                "strong" if priority == "High" else "medium",
                "[]",
                0,
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
            "# AI 研究方向探索示例\n\n- 先在新建项目页输入自己的研究方向\n- 再检索近三年论文并执行方向精读\n- 最后生成 Paper Memory、Gap Board 和 Experiment Plan",
            json.dumps(
                {
                    "project": "ai-research-direction-example",
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
            "paper_card_memory_augmented_reading",
            project_id,
            "paper_paper_memory_retrieval",
            artifact_id,
            json.dumps({"sections": 12}, ensure_ascii=False),
            "结构化论文记忆足以支撑后续研究问题回答。",
            "一周内验证 Paper Memory 检索是否能减少无证据泛化回答。",
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


def artifact_summary_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": data["id"],
        "project_id": data["project_id"],
        "title": data["title"],
        "kind": data["kind"],
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        "markdown_bytes": int(data.get("markdown_bytes") or 0),
        "json_bytes": int(data.get("json_bytes") or 0),
        "markdown_preview": data.get("markdown_preview") or "",
        "json_schema_version": data.get("json_schema_version") or "",
    }


def main() -> None:
    init_db()
    print(get_db_path())


if __name__ == "__main__":
    main()
