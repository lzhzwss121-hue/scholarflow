from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / ".data" / "scholarflow.sqlite3"
SQLITE_BUSY_TIMEOUT_MS = 5000
CURRENT_SCHEMA_VERSION = 4


class DatabaseInitializationError(RuntimeError):
    """Raised when SQLite cannot establish the required integrity contract."""


class DatabaseMigrationError(DatabaseInitializationError):
    """Raised when a schema migration cannot finish atomically."""


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
    connection = sqlite3.connect(
        db_path,
        timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
    )
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        connection.row_factory = sqlite3.Row
        verify_foreign_keys_enabled(connection)
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        connection.close()


def init_db() -> None:
    with get_connection() as connection:
        enable_wal(connection)
        run_schema_migrations(connection)
        verify_foreign_keys_enabled(connection)
        connection.execute("BEGIN IMMEDIATE")
        seed_demo_project(connection)


def enable_wal(connection: sqlite3.Connection) -> None:
    deadline = time.monotonic() + (SQLITE_BUSY_TIMEOUT_MS / 1000)
    while True:
        try:
            row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            break
        except sqlite3.OperationalError as error:
            if "locked" not in str(error).lower() or time.monotonic() >= deadline:
                raise DatabaseInitializationError(
                    "SQLite initialization failed while enabling WAL."
                ) from error
            time.sleep(0.05)
    journal_mode = str(row[0] if row else "").lower()
    if journal_mode != "wal":
        raise DatabaseInitializationError(
            "SQLite initialization failed: PRAGMA journal_mode did not become WAL "
            f"(reported {journal_mode or 'unknown'})."
        )


def verify_foreign_keys_enabled(connection: sqlite3.Connection) -> None:
    row = connection.execute("PRAGMA foreign_keys").fetchone()
    enabled = int(row[0] if row else 0)
    if enabled != 1:
        raise DatabaseInitializationError(
            "SQLite integrity initialization failed: PRAGMA foreign_keys must equal 1 "
            f"for every connection (reported {enabled})."
        )


def run_schema_migrations(connection: sqlite3.Connection) -> None:
    current_version = schema_version(connection)
    if current_version > CURRENT_SCHEMA_VERSION:
        raise DatabaseMigrationError(
            "SQLite schema is newer than this ScholarFlow build: "
            f"database={current_version}, supported={CURRENT_SCHEMA_VERSION}."
        )
    if current_version == CURRENT_SCHEMA_VERSION:
        validate_schema_contracts(connection)
        return

    for version in range(current_version + 1, CURRENT_SCHEMA_VERSION + 1):
        apply_schema_migration(connection, version)

    validate_schema_contracts(connection)


def apply_schema_migration(connection: sqlite3.Connection, version: int) -> None:
    migration_names = {
        1: "baseline_integrity_contract",
        2: "durable_local_jobs",
        3: "evidence_hybrid_rag_fts5",
        4: "model_provider_audit_contract",
    }
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        foreign_keys_row = connection.execute("PRAGMA foreign_keys").fetchone()
        if int(foreign_keys_row[0] if foreign_keys_row else 1) != 0:
            raise DatabaseMigrationError(
                "SQLite migration could not temporarily suspend foreign-key enforcement."
            )
        if version == 1:
            initialize_schema_v1(connection)
            ensure_foreign_key_contracts(connection)
            create_schema_indexes(connection)
        elif version == 2:
            initialize_schema_v2(connection)
        elif version == 3:
            initialize_schema_v3(connection)
        elif version == 4:
            initialize_schema_v4(connection)
        else:
            raise DatabaseMigrationError(f"Unknown SQLite schema migration: {version}.")

        # Another local process may have completed this migration while this
        # connection was waiting for BEGIN IMMEDIATE. Re-check under the write
        # lock so concurrent API/worker startup remains idempotent.
        if schema_version(connection) >= version:
            connection.rollback()
            return

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            details = "; ".join(
                f"table={row[0]} rowid={row[1]} parent={row[2]}"
                for row in violations[:10]
            )
            raise DatabaseMigrationError(
                "SQLite migration found orphaned rows and was rolled back: " + details
            )
        connection.execute(
            """
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (version, migration_names[version], utc_now()),
        )
        connection.execute(f"PRAGMA user_version = {version}")
        connection.commit()
    except BaseException as error:
        connection.rollback()
        if isinstance(error, DatabaseMigrationError):
            raise
        raise DatabaseMigrationError(
            f"SQLite schema migration {version} failed and was rolled back: {error}"
        ) from error
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
        verify_foreign_keys_enabled(connection)


def schema_version(connection: sqlite3.Connection) -> int:
    table = connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name = 'schema_migrations'
        """
    ).fetchone()
    if table is None:
        return 0
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    ).fetchone()
    return int(row[0] if row else 0)


def initialize_schema_v1(connection: sqlite3.Connection) -> None:
    connection.executescript(
            """
            BEGIN IMMEDIATE;

            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );

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
                updated_at TEXT NOT NULL,
                FOREIGN KEY (active_session_id) REFERENCES sessions(id)
                    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
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

            CREATE TABLE IF NOT EXISTS paper_chunks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                source TEXT NOT NULL,
                source_origin TEXT NOT NULL DEFAULT '',
                evidence_level TEXT NOT NULL DEFAULT 'metadata_only',
                section TEXT NOT NULL DEFAULT 'unknown',
                page_start INTEGER,
                page_end INTEGER,
                chunk_text TEXT NOT NULL,
                char_count INTEGER NOT NULL DEFAULT 0,
                token_count INTEGER NOT NULL DEFAULT 0,
                chunk_hash TEXT NOT NULL,
                index_version TEXT NOT NULL DEFAULT 'paper_chunks.v1',
                embedding_model TEXT NOT NULL DEFAULT '',
                embedding_dimensions INTEGER NOT NULL DEFAULT 0,
                embedding_json TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS rag_evaluations (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                answer_artifact_id TEXT,
                question TEXT NOT NULL,
                answer_status TEXT NOT NULL,
                answer_kind TEXT NOT NULL,
                quality_status TEXT NOT NULL,
                score REAL,
                generation_provider TEXT NOT NULL DEFAULT '',
                generation_model TEXT NOT NULL DEFAULT '',
                assessment_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (answer_artifact_id) REFERENCES artifacts(id) ON DELETE SET NULL
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

            CREATE TABLE IF NOT EXISTS direction_review_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                round_index INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'queued',
                stage TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                notices_json TEXT NOT NULL DEFAULT '[]',
                result_json TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
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
            CREATE INDEX IF NOT EXISTS idx_paper_chunks_project_id ON paper_chunks(project_id);
            CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_id ON paper_chunks(project_id, paper_id, chunk_index);
            CREATE INDEX IF NOT EXISTS idx_paper_chunks_locator ON paper_chunks(project_id, section, page_start);
            CREATE INDEX IF NOT EXISTS idx_paper_chunks_hash ON paper_chunks(project_id, paper_id, chunk_hash);
            CREATE INDEX IF NOT EXISTS idx_rag_evaluations_project_id
                ON rag_evaluations(project_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_rag_evaluations_question
                ON rag_evaluations(project_id, question, created_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
            CREATE INDEX IF NOT EXISTS idx_agent_runs_project_id ON agent_runs(project_id);
            CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id ON agent_runs(session_id);
            CREATE INDEX IF NOT EXISTS idx_direction_review_runs_project_id
                ON direction_review_runs(project_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_direction_review_runs_active
                ON direction_review_runs(project_id, status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_tool_events_session_id ON tool_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_retrieval_cache_lookup ON retrieval_cache(source, query, max_results, created_at);
            """
    )
    ensure_legacy_columns(connection)


def initialize_schema_v2(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    artifact_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(artifacts)").fetchall()
    }
    if "idempotency_key" not in artifact_columns:
        connection.execute("ALTER TABLE artifacts ADD COLUMN idempotency_key TEXT")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_idempotency_key
        ON artifacts(idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            session_id TEXT,
            job_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'queued',
            stage TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            lease_owner TEXT,
            lease_until TEXT,
            heartbeat_at TEXT,
            cancellation_requested INTEGER NOT NULL DEFAULT 0,
            checkpoint_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            next_attempt_at TEXT,
            dedupe_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_claim
        ON jobs(status, next_attempt_at, lease_until, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_project
        ON jobs(project_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_heartbeats (
            worker_id TEXT PRIMARY KEY,
            pid INTEGER NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            stopped_at TEXT
        )
        """
    )


def initialize_schema_v3(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    existing_paper_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(papers)").fetchall()
    }
    for column_name in ("doi", "arxiv_id", "openalex_id", "canonical_work_id"):
        if column_name not in existing_paper_columns:
            connection.execute(
                f"ALTER TABLE papers ADD COLUMN {quote_identifier(column_name)} "
                "TEXT NOT NULL DEFAULT ''"
            )
    existing_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(paper_chunks)").fetchall()
    }
    additions = {
        "doi": "TEXT NOT NULL DEFAULT ''",
        "arxiv_id": "TEXT NOT NULL DEFAULT ''",
        "openalex_id": "TEXT NOT NULL DEFAULT ''",
        "title": "TEXT NOT NULL DEFAULT ''",
        "evidence_verified": "INTEGER NOT NULL DEFAULT 0",
        "parser_version": "TEXT NOT NULL DEFAULT 'legacy.unknown'",
        "canonical_work_id": "TEXT NOT NULL DEFAULT ''",
        "lexical_text": "TEXT NOT NULL DEFAULT ''",
    }
    for column_name, definition in additions.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE paper_chunks "
                f"ADD COLUMN {quote_identifier(column_name)} {definition}"
            )

    connection.execute(
        """
        UPDATE paper_chunks
        SET title = COALESCE(
                NULLIF(title, ''),
                (SELECT papers.title FROM papers WHERE papers.id = paper_chunks.paper_id),
                ''
            ),
            canonical_work_id = COALESCE(NULLIF(canonical_work_id, ''), paper_id),
            lexical_text = CASE
                WHEN lexical_text <> '' THEN lexical_text
                ELSE LOWER(
                    COALESCE(
                        (SELECT papers.title FROM papers WHERE papers.id = paper_chunks.paper_id),
                        ''
                    ) || ' ' || section || ' ' || chunk_text
                )
            END
        """
    )
    try:
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS paper_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                project_id UNINDEXED,
                paper_id UNINDEXED,
                title,
                section,
                chunk_text,
                lexical_text,
                tokenize = 'unicode61 remove_diacritics 2'
            )
            """
        )
    except sqlite3.OperationalError as error:
        raise DatabaseMigrationError(
            "SQLite FTS5 is required for Evidence-aware Hybrid RAG but is unavailable."
        ) from error

    for statement in (
        """
        CREATE TRIGGER IF NOT EXISTS paper_chunks_fts_insert
        AFTER INSERT ON paper_chunks
        BEGIN
            INSERT INTO paper_chunks_fts (
                chunk_id, project_id, paper_id, title, section, chunk_text, lexical_text
            )
            VALUES (
                new.id, new.project_id, new.paper_id, new.title,
                new.section, new.chunk_text, new.lexical_text
            );
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS paper_chunks_fts_delete
        AFTER DELETE ON paper_chunks
        BEGIN
            DELETE FROM paper_chunks_fts WHERE chunk_id = old.id;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS paper_chunks_fts_update
        AFTER UPDATE OF project_id, paper_id, title, section, chunk_text, lexical_text
        ON paper_chunks
        BEGIN
            DELETE FROM paper_chunks_fts WHERE chunk_id = old.id;
            INSERT INTO paper_chunks_fts (
                chunk_id, project_id, paper_id, title, section, chunk_text, lexical_text
            )
            VALUES (
                new.id, new.project_id, new.paper_id, new.title,
                new.section, new.chunk_text, new.lexical_text
            );
        END
        """,
    ):
        connection.execute(statement)
    connection.execute("DELETE FROM paper_chunks_fts")
    connection.execute(
        """
        INSERT INTO paper_chunks_fts (
            chunk_id, project_id, paper_id, title, section, chunk_text, lexical_text
        )
        SELECT id, project_id, paper_id, title, section, chunk_text, lexical_text
        FROM paper_chunks
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_paper_chunks_evidence_gate
        ON paper_chunks(project_id, evidence_verified, evidence_level, paper_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_paper_chunks_canonical_work
        ON paper_chunks(project_id, canonical_work_id, paper_id)
        """
    )


def initialize_schema_v4(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS model_call_audits (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            run_id TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            purpose TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            request_timestamp TEXT NOT NULL,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            response_status TEXT NOT NULL,
            fallback_reason TEXT NOT NULL DEFAULT '',
            requested_provider TEXT NOT NULL DEFAULT '',
            requested_model TEXT NOT NULL DEFAULT '',
            external_data_sent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_call_audits_project
        ON model_call_audits(project_id, request_timestamp)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_call_audits_run
        ON model_call_audits(run_id, request_timestamp)
        """
    )


FOREIGN_KEY_CONTRACTS: dict[str, frozenset[tuple[str, str, str, str]]] = {
    "projects": frozenset(
        {("active_session_id", "sessions", "id", "SET NULL")}
    ),
    "papers": frozenset({("project_id", "projects", "id", "CASCADE")}),
    "artifacts": frozenset({("project_id", "projects", "id", "CASCADE")}),
    "paper_cards": frozenset(
        {
            ("project_id", "projects", "id", "CASCADE"),
            ("paper_id", "papers", "id", "SET NULL"),
            ("artifact_id", "artifacts", "id", "SET NULL"),
        }
    ),
    "paper_memories": frozenset(
        {
            ("project_id", "projects", "id", "CASCADE"),
            ("paper_id", "papers", "id", "SET NULL"),
        }
    ),
    "direction_memories": frozenset(
        {("project_id", "projects", "id", "CASCADE")}
    ),
    "paper_chunks": frozenset(
        {
            ("project_id", "projects", "id", "CASCADE"),
            ("paper_id", "papers", "id", "CASCADE"),
        }
    ),
    "rag_evaluations": frozenset(
        {
            ("project_id", "projects", "id", "CASCADE"),
            ("answer_artifact_id", "artifacts", "id", "SET NULL"),
        }
    ),
    "sessions": frozenset({("project_id", "projects", "id", "CASCADE")}),
    "agent_runs": frozenset(
        {
            ("project_id", "projects", "id", "CASCADE"),
            ("session_id", "sessions", "id", "CASCADE"),
            ("plan_artifact_id", "artifacts", "id", "SET NULL"),
            ("result_artifact_id", "artifacts", "id", "SET NULL"),
        }
    ),
    "direction_review_runs": frozenset(
        {
            ("project_id", "projects", "id", "CASCADE"),
            ("session_id", "sessions", "id", "CASCADE"),
        }
    ),
    "tool_events": frozenset({("session_id", "sessions", "id", "CASCADE")}),
    "jobs": frozenset(
        {
            ("project_id", "projects", "id", "CASCADE"),
            ("session_id", "sessions", "id", "SET NULL"),
        }
    ),
    "model_call_audits": frozenset(
        {
            ("project_id", "projects", "id", "CASCADE"),
            ("run_id", "agent_runs", "id", "SET NULL"),
        }
    ),
}

V1_FOREIGN_KEY_CONTRACTS = {
    table_name: contract
    for table_name, contract in FOREIGN_KEY_CONTRACTS.items()
    if table_name not in {"jobs", "model_call_audits"}
}


def canonical_schema_objects() -> tuple[dict[str, str], list[str]]:
    canonical = sqlite3.connect(":memory:")
    canonical.row_factory = sqlite3.Row
    try:
        initialize_schema_v1(canonical)
        canonical.commit()
        tables = {
            str(row["name"]): str(row["sql"])
            for row in canonical.execute(
                """
                SELECT name, sql FROM sqlite_master
                WHERE type = 'table' AND name IN (
                    'projects', 'papers', 'artifacts', 'paper_cards',
                    'paper_memories', 'direction_memories', 'paper_chunks',
                    'rag_evaluations', 'sessions', 'agent_runs',
                    'direction_review_runs', 'tool_events'
                )
                """
            ).fetchall()
        }
        indexes = [
            str(row["sql"])
            for row in canonical.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type = 'index' AND sql IS NOT NULL
                ORDER BY name
                """
            ).fetchall()
        ]
        return tables, indexes
    finally:
        canonical.close()


def foreign_key_signatures(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[tuple[str, str, str, str]]:
    return {
        (
            str(row["from"]),
            str(row["table"]),
            str(row["to"]),
            str(row["on_delete"]).upper(),
        )
        for row in connection.execute(
            f"PRAGMA foreign_key_list({quote_identifier(table_name)})"
        ).fetchall()
    }


def ensure_foreign_key_contracts(connection: sqlite3.Connection) -> None:
    canonical_tables, _ = canonical_schema_objects()
    for table_name, expected in V1_FOREIGN_KEY_CONTRACTS.items():
        actual = foreign_key_signatures(connection, table_name)
        if actual != expected:
            rebuild_table(
                connection,
                table_name=table_name,
                canonical_sql=canonical_tables[table_name],
            )


def validate_schema_contracts(connection: sqlite3.Connection) -> None:
    for table_name, expected in FOREIGN_KEY_CONTRACTS.items():
        actual = foreign_key_signatures(connection, table_name)
        if actual != expected:
            raise DatabaseInitializationError(
                "SQLite foreign-key contract mismatch for "
                f"{table_name}: expected={sorted(expected)}, actual={sorted(actual)}."
            )
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        details = "; ".join(
            f"table={row[0]} rowid={row[1]} parent={row[2]}"
            for row in violations[:10]
        )
        raise DatabaseInitializationError(
            "SQLite foreign-key integrity check failed: " + details
        )
    artifact_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(artifacts)").fetchall()
    }
    if "idempotency_key" not in artifact_columns:
        raise DatabaseInitializationError(
            "SQLite schema contract mismatch: artifacts.idempotency_key is missing."
        )
    idempotency_index = connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'index' AND name = 'idx_artifacts_idempotency_key'
        """
    ).fetchone()
    if idempotency_index is None:
        raise DatabaseInitializationError(
            "SQLite schema contract mismatch: artifact idempotency index is missing."
        )
    required_job_columns = {
        "id",
        "project_id",
        "session_id",
        "job_type",
        "payload_json",
        "status",
        "stage",
        "progress",
        "attempts",
        "max_attempts",
        "lease_owner",
        "lease_until",
        "heartbeat_at",
        "cancellation_requested",
        "checkpoint_json",
        "result_json",
        "error",
        "created_at",
        "updated_at",
        "completed_at",
    }
    actual_job_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    missing_job_columns = sorted(required_job_columns - actual_job_columns)
    if missing_job_columns:
        raise DatabaseInitializationError(
            "SQLite schema contract mismatch: jobs columns are missing: "
            + ", ".join(missing_job_columns)
        )
    required_chunk_columns = {
        "project_id",
        "paper_id",
        "doi",
        "arxiv_id",
        "openalex_id",
        "title",
        "section",
        "page_start",
        "page_end",
        "source_origin",
        "evidence_level",
        "evidence_verified",
        "parser_version",
        "chunk_hash",
        "canonical_work_id",
        "lexical_text",
    }
    actual_chunk_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(paper_chunks)").fetchall()
    }
    missing_chunk_columns = sorted(required_chunk_columns - actual_chunk_columns)
    if missing_chunk_columns:
        raise DatabaseInitializationError(
            "SQLite schema contract mismatch: paper_chunks columns are missing: "
            + ", ".join(missing_chunk_columns)
        )
    required_paper_identifiers = {
        "doi",
        "arxiv_id",
        "openalex_id",
        "canonical_work_id",
    }
    actual_paper_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(papers)").fetchall()
    }
    if not required_paper_identifiers.issubset(actual_paper_columns):
        raise DatabaseInitializationError(
            "SQLite schema contract mismatch: paper identity columns are missing."
        )
    fts_table = connection.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'paper_chunks_fts'
        """
    ).fetchone()
    if fts_table is None or "fts5" not in str(fts_table["sql"] or "").lower():
        raise DatabaseInitializationError(
            "SQLite schema contract mismatch: paper_chunks_fts must be an FTS5 index."
        )
    trigger_names = {
        str(row["name"])
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'trigger' AND name LIKE 'paper_chunks_fts_%'
            """
        ).fetchall()
    }
    required_triggers = {
        "paper_chunks_fts_insert",
        "paper_chunks_fts_delete",
        "paper_chunks_fts_update",
    }
    if not required_triggers.issubset(trigger_names):
        raise DatabaseInitializationError(
            "SQLite schema contract mismatch: paper_chunks_fts sync triggers are missing."
        )
    required_audit_columns = {
        "id",
        "project_id",
        "run_id",
        "provider",
        "model",
        "purpose",
        "prompt_version",
        "request_timestamp",
        "latency_ms",
        "response_status",
        "fallback_reason",
        "requested_provider",
        "requested_model",
        "external_data_sent",
        "created_at",
    }
    actual_audit_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(model_call_audits)").fetchall()
    }
    missing_audit_columns = sorted(required_audit_columns - actual_audit_columns)
    if missing_audit_columns:
        raise DatabaseInitializationError(
            "SQLite schema contract mismatch: model_call_audits columns are missing: "
            + ", ".join(missing_audit_columns)
        )


def rebuild_table(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    canonical_sql: str,
) -> None:
    temporary_name = f"__scholarflow_migration_{table_name}"
    connection.execute(f"DROP TABLE IF EXISTS {quote_identifier(temporary_name)}")
    prefix = f"CREATE TABLE {table_name}"
    if not canonical_sql.startswith(prefix):
        raise DatabaseMigrationError(
            f"Cannot rebuild {table_name}: unexpected canonical CREATE TABLE statement."
        )
    connection.execute(
        canonical_sql.replace(
            prefix,
            f"CREATE TABLE {quote_identifier(temporary_name)}",
            1,
        )
    )

    old_columns = {
        str(row["name"]): row
        for row in connection.execute(
            f"PRAGMA table_info({quote_identifier(table_name)})"
        ).fetchall()
    }
    new_columns = {
        str(row["name"]): row
        for row in connection.execute(
            f"PRAGMA table_info({quote_identifier(temporary_name)})"
        ).fetchall()
    }
    for column_name, column in old_columns.items():
        if column_name in new_columns:
            continue
        connection.execute(
            f"ALTER TABLE {quote_identifier(temporary_name)} "
            f"ADD COLUMN {quote_identifier(column_name)} "
            f"{legacy_column_definition(column)}"
        )
        new_columns[column_name] = column

    shared_columns = [
        column_name
        for column_name in old_columns
        if column_name in new_columns
    ]
    if shared_columns:
        columns_sql = ", ".join(quote_identifier(name) for name in shared_columns)
        connection.execute(
            f"INSERT INTO {quote_identifier(temporary_name)} ({columns_sql}) "
            f"SELECT {columns_sql} FROM {quote_identifier(table_name)}"
        )
    connection.execute(f"DROP TABLE {quote_identifier(table_name)}")
    connection.execute(
        f"ALTER TABLE {quote_identifier(temporary_name)} "
        f"RENAME TO {quote_identifier(table_name)}"
    )


def legacy_column_definition(column: sqlite3.Row) -> str:
    declared_type = str(column["type"] or "BLOB")
    parts = [declared_type]
    default_value = column["dflt_value"]
    if int(column["notnull"] or 0):
        if default_value is None:
            raise DatabaseMigrationError(
                "Cannot safely preserve unknown NOT NULL legacy column "
                f"{column['name']} without a default."
            )
        parts.append("NOT NULL")
    if default_value is not None:
        parts.append(f"DEFAULT {default_value}")
    return " ".join(parts)


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def create_schema_indexes(connection: sqlite3.Connection) -> None:
    _, index_statements = canonical_schema_objects()
    for statement in index_statements:
        connection.execute(
            statement.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
        )


LEGACY_COLUMN_ADDITIONS: dict[str, dict[str, str]] = {
    "papers": {
        "authors": "TEXT NOT NULL DEFAULT ''",
        "abstract": "TEXT NOT NULL DEFAULT ''",
        "source": "TEXT NOT NULL DEFAULT ''",
        "url": "TEXT NOT NULL DEFAULT ''",
        "pdf_url": "TEXT NOT NULL DEFAULT ''",
        "relevance_score": "REAL NOT NULL DEFAULT 0",
        "relevance_quality": "TEXT NOT NULL DEFAULT 'medium'",
        "matched_terms_json": "TEXT NOT NULL DEFAULT '[]'",
        "review_required": "INTEGER NOT NULL DEFAULT 0",
    },
    "paper_cards": {
        "research_sight_json": "TEXT NOT NULL DEFAULT '{}'",
    },
    "paper_memories": {
        "research_sight_json": "TEXT NOT NULL DEFAULT '{}'",
    },
    "direction_memories": {
        "baseline_map_json": "TEXT NOT NULL DEFAULT '{}'",
    },
    "agent_runs": {
        "cancellation_requested": "INTEGER NOT NULL DEFAULT 0",
    },
    "direction_review_runs": {
        "started_at": "TEXT",
    },
}


def ensure_legacy_columns(connection: sqlite3.Connection) -> None:
    for table_name, columns in LEGACY_COLUMN_ADDITIONS.items():
        existing_columns = {
            str(row["name"])
            for row in connection.execute(
                f"PRAGMA table_info({quote_identifier(table_name)})"
            ).fetchall()
        }
        for column_name, definition in columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE {quote_identifier(table_name)} "
                    f"ADD COLUMN {quote_identifier(column_name)} {definition}"
                )


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


def main() -> None:
    init_db()
    print(get_db_path())


if __name__ == "__main__":
    main()
