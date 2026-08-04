from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from scholarflow_api.database import (
    CURRENT_SCHEMA_VERSION,
    FOREIGN_KEY_CONTRACTS,
    DatabaseMigrationError,
    foreign_key_signatures,
    get_connection,
    init_db,
    initialize_schema_v1,
    initialize_schema_v2,
)


NOW = "2026-07-28T00:00:00+00:00"


def insert_related_rows(connection: sqlite3.Connection, suffix: str) -> dict[str, str]:
    ids = {
        "project": f"project-{suffix}",
        "paper": f"paper-{suffix}",
        "artifact": f"artifact-{suffix}",
        "paper_card": f"paper-card-{suffix}",
        "paper_memory": f"paper-memory-{suffix}",
        "direction_memory": f"direction-memory-{suffix}",
        "paper_chunk": f"paper-chunk-{suffix}",
        "evaluation": f"evaluation-{suffix}",
        "session": f"session-{suffix}",
        "agent_run": f"agent-run-{suffix}",
        "direction_review_run": f"direction-review-run-{suffix}",
        "tool_event": f"tool-event-{suffix}",
        "job": f"job-{suffix}",
    }
    connection.execute(
        """
        INSERT INTO projects (
            id, title, active_session_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            ids["project"],
            "Integrity project",
            ids["session"],
            NOW,
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO papers (id, project_id, title, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (ids["paper"], ids["project"], "Integrity paper", NOW),
    )
    connection.execute(
        """
        INSERT INTO artifacts (
            id, project_id, title, kind, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ids["artifact"],
            ids["project"],
            "Integrity artifact",
            "paper_card",
            NOW,
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO paper_cards (
            id, project_id, paper_id, artifact_id, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            ids["paper_card"],
            ids["project"],
            ids["paper"],
            ids["artifact"],
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO paper_memories (
            id, project_id, paper_id, title, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ids["paper_memory"],
            ids["project"],
            ids["paper"],
            "Integrity memory",
            NOW,
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO direction_memories (
            id, project_id, direction, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            ids["direction_memory"],
            ids["project"],
            "integrity",
            NOW,
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO paper_chunks (
            id, project_id, paper_id, chunk_index, source, chunk_text,
            chunk_hash, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ids["paper_chunk"],
            ids["project"],
            ids["paper"],
            0,
            "test",
            "Traceable source text.",
            f"hash-{suffix}",
            NOW,
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO rag_evaluations (
            id, project_id, answer_artifact_id, question, answer_status,
            answer_kind, quality_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ids["evaluation"],
            ids["project"],
            ids["artifact"],
            "Is this traceable?",
            "answered",
            "extractive",
            "passed",
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO sessions (
            id, project_id, title, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            ids["session"],
            ids["project"],
            "Integrity session",
            NOW,
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO agent_runs (
            id, project_id, session_id, task, plan_artifact_id,
            result_artifact_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ids["agent_run"],
            ids["project"],
            ids["session"],
            "Check integrity",
            ids["artifact"],
            ids["artifact"],
            NOW,
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO direction_review_runs (
            id, project_id, session_id, direction, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ids["direction_review_run"],
            ids["project"],
            ids["session"],
            "integrity",
            NOW,
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO tool_events (
            id, session_id, time_label, tool, status, summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ids["tool_event"],
            ids["session"],
            "00:00",
            "test",
            "success",
            "Integrity event",
            NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO jobs (
            id, project_id, session_id, job_type, payload_json, dedupe_key,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, '{}', ?, ?, ?)
        """,
        (
            ids["job"],
            ids["project"],
            ids["session"],
            "test",
            f"test:{suffix}",
            NOW,
            NOW,
        ),
    )
    return ids


class DatabaseContractTest(unittest.TestCase):
    def temporary_database(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        tmpdir = tempfile.TemporaryDirectory(dir="/private/tmp")
        return tmpdir, Path(tmpdir.name) / "scholarflow.sqlite3"

    def test_every_new_connection_enables_required_pragmas(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            observed = []
            for _ in range(2):
                with get_connection() as connection:
                    observed.append(
                        (
                            connection.execute("PRAGMA foreign_keys").fetchone()[0],
                            connection.execute("PRAGMA busy_timeout").fetchone()[0],
                            connection.execute("PRAGMA journal_mode").fetchone()[0],
                        )
                    )

        self.assertEqual(observed, [(1, 5000, "wal"), (1, 5000, "wal")])

    def test_write_with_missing_project_id_is_rejected(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            with self.assertRaises(sqlite3.IntegrityError):
                with get_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO papers (id, project_id, title, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        ("orphan-paper", "missing-project", "Orphan", NOW),
                    )
            with get_connection() as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM papers WHERE id = 'orphan-paper'"
                ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_deleting_project_cascades_all_project_owned_rows(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            with get_connection() as connection:
                ids = insert_related_rows(connection, "cascade")
            with get_connection() as connection:
                connection.execute(
                    "DELETE FROM projects WHERE id = ?",
                    (ids["project"],),
                )
            with get_connection() as connection:
                remaining = {
                    table: connection.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE id = ?',
                        (row_id,),
                    ).fetchone()[0]
                    for table, row_id in {
                        "papers": ids["paper"],
                        "artifacts": ids["artifact"],
                        "paper_cards": ids["paper_card"],
                        "paper_memories": ids["paper_memory"],
                        "direction_memories": ids["direction_memory"],
                        "paper_chunks": ids["paper_chunk"],
                        "rag_evaluations": ids["evaluation"],
                        "sessions": ids["session"],
                        "agent_runs": ids["agent_run"],
                        "direction_review_runs": ids["direction_review_run"],
                        "tool_events": ids["tool_event"],
                        "jobs": ids["job"],
                    }.items()
                }

        self.assertEqual(remaining, {table: 0 for table in remaining})

    def test_research_assets_use_set_null_when_source_is_deleted(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            with get_connection() as connection:
                ids = insert_related_rows(connection, "preserve")
            with get_connection() as connection:
                connection.execute(
                    "DELETE FROM papers WHERE id = ?",
                    (ids["paper"],),
                )
                connection.execute(
                    "DELETE FROM artifacts WHERE id = ?",
                    (ids["artifact"],),
                )
            with get_connection() as connection:
                paper_card = connection.execute(
                    """
                    SELECT paper_id, artifact_id FROM paper_cards WHERE id = ?
                    """,
                    (ids["paper_card"],),
                ).fetchone()
                paper_memory = connection.execute(
                    "SELECT paper_id FROM paper_memories WHERE id = ?",
                    (ids["paper_memory"],),
                ).fetchone()
                evaluation = connection.execute(
                    """
                    SELECT answer_artifact_id FROM rag_evaluations WHERE id = ?
                    """,
                    (ids["evaluation"],),
                ).fetchone()
                agent_run = connection.execute(
                    """
                    SELECT plan_artifact_id, result_artifact_id
                    FROM agent_runs WHERE id = ?
                    """,
                    (ids["agent_run"],),
                ).fetchone()
                chunk_count = connection.execute(
                    "SELECT COUNT(*) FROM paper_chunks WHERE id = ?",
                    (ids["paper_chunk"],),
                ).fetchone()[0]

        self.assertEqual(tuple(paper_card), (None, None))
        self.assertEqual(paper_memory["paper_id"], None)
        self.assertEqual(evaluation["answer_artifact_id"], None)
        self.assertEqual(tuple(agent_run), (None, None))
        self.assertEqual(chunk_count, 0)

    def test_deleting_active_session_clears_project_pointer(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            with get_connection() as connection:
                ids = insert_related_rows(connection, "active-session")
            with get_connection() as connection:
                connection.execute(
                    "DELETE FROM sessions WHERE id = ?",
                    (ids["session"],),
                )
            with get_connection() as connection:
                active_session_id = connection.execute(
                    "SELECT active_session_id FROM projects WHERE id = ?",
                    (ids["project"],),
                ).fetchone()[0]
                job_session_id = connection.execute(
                    "SELECT session_id FROM jobs WHERE id = ?",
                    (ids["job"],),
                ).fetchone()[0]

        self.assertIsNone(active_session_id)
        self.assertIsNone(job_session_id)

    def test_exception_rolls_back_the_entire_transaction(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            failed_connection: sqlite3.Connection | None = None
            with self.assertRaisesRegex(RuntimeError, "force rollback"):
                with get_connection() as connection:
                    failed_connection = connection
                    connection.execute(
                        """
                        INSERT INTO projects (id, title, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        ("rollback-project", "Rollback", NOW, NOW),
                    )
                    connection.execute(
                        """
                        INSERT INTO papers (id, project_id, title, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        ("rollback-paper", "rollback-project", "Rollback", NOW),
                    )
                    raise RuntimeError("force rollback")
            assert failed_connection is not None
            with self.assertRaises(sqlite3.ProgrammingError):
                failed_connection.execute("SELECT 1")
            with get_connection() as connection:
                project_count = connection.execute(
                    "SELECT COUNT(*) FROM projects WHERE id = 'rollback-project'"
                ).fetchone()[0]
                paper_count = connection.execute(
                    "SELECT COUNT(*) FROM papers WHERE id = 'rollback-paper'"
                ).fetchone()[0]

        self.assertEqual((project_count, paper_count), (0, 0))

    def test_wal_allows_concurrent_reader_and_short_writer(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO projects (id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("concurrency-project", "Concurrency", NOW, NOW),
                )

            writer_started = threading.Event()
            reader_finished = threading.Event()

            def write_once() -> None:
                with get_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO artifacts (
                            id, project_id, title, kind, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "concurrent-artifact",
                            "concurrency-project",
                            "Concurrent",
                            "note",
                            NOW,
                            NOW,
                        ),
                    )
                    writer_started.set()
                    if not reader_finished.wait(timeout=3):
                        raise TimeoutError("concurrent reader did not finish")

            def read_during_write() -> int:
                if not writer_started.wait(timeout=3):
                    raise TimeoutError("concurrent writer did not start")
                try:
                    with get_connection() as connection:
                        return connection.execute(
                            """
                            SELECT COUNT(*) FROM artifacts
                            WHERE id = 'concurrent-artifact'
                            """
                        ).fetchone()[0]
                finally:
                    reader_finished.set()

            with ThreadPoolExecutor(max_workers=2) as executor:
                writer = executor.submit(write_once)
                reader = executor.submit(read_during_write)
                count_during_uncommitted_write = reader.result(timeout=5)
                writer.result(timeout=5)

            with get_connection() as connection:
                count_after_commit = connection.execute(
                    """
                    SELECT COUNT(*) FROM artifacts
                    WHERE id = 'concurrent-artifact'
                    """
                ).fetchone()[0]

        self.assertEqual(count_during_uncommitted_write, 0)
        self.assertEqual(count_after_commit, 1)

    def test_migration_is_idempotent_and_foreign_key_contracts_are_exact(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            with get_connection() as connection:
                first_schema = [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT type, name, sql FROM sqlite_master
                        WHERE name NOT LIKE 'sqlite_%'
                        ORDER BY type, name
                        """
                    ).fetchall()
                ]
            init_db()
            with get_connection() as connection:
                second_schema = [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT type, name, sql FROM sqlite_master
                        WHERE name NOT LIKE 'sqlite_%'
                        ORDER BY type, name
                        """
                    ).fetchall()
                ]
                migration_rows = connection.execute(
                    """
                    SELECT version, name FROM schema_migrations ORDER BY version
                    """
                ).fetchall()
                user_version = connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
                index_counts = connection.execute(
                    """
                    SELECT COUNT(*), COUNT(DISTINCT name)
                    FROM sqlite_master WHERE type = 'index'
                    """
                ).fetchone()
                actual_contracts = {
                    table: foreign_key_signatures(connection, table)
                    for table in FOREIGN_KEY_CONTRACTS
                }

        self.assertEqual(
            [tuple(row) for row in migration_rows],
            [
                (1, "baseline_integrity_contract"),
                (2, "durable_local_jobs"),
                (3, "evidence_hybrid_rag_fts5"),
                (4, "model_provider_audit_contract"),
                (5, "versioned_agent_plan_revisions"),
                (CURRENT_SCHEMA_VERSION, "model_provider_token_usage"),
            ],
        )
        self.assertEqual(user_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(index_counts[0], index_counts[1])
        self.assertEqual(second_schema, first_schema)
        self.assertEqual(actual_contracts, FOREIGN_KEY_CONTRACTS)

    def test_concurrent_api_and_worker_initialization_is_idempotent(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(init_db) for _ in range(2)]
                for future in futures:
                    future.result(timeout=5)
            with get_connection() as connection:
                migrations = [
                    tuple(row)
                    for row in connection.execute(
                        "SELECT version, name FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]

        self.assertEqual(
            migrations,
            [
                (1, "baseline_integrity_contract"),
                (2, "durable_local_jobs"),
                (3, "evidence_hybrid_rag_fts5"),
                (4, "model_provider_audit_contract"),
                (5, "versioned_agent_plan_revisions"),
                (6, "model_provider_token_usage"),
            ],
        )

    def test_legacy_database_upgrade_preserves_readable_data(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO projects (id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("legacy-project", "Legacy", NOW, NOW),
                )
                connection.execute(
                    """
                    INSERT INTO papers (id, project_id, title, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("legacy-paper", "legacy-project", "Readable legacy paper", NOW),
                )

            with sqlite3.connect(db_path) as connection:
                connection.execute("DROP TABLE schema_migrations")
                connection.execute("PRAGMA user_version = 0")
                connection.execute(
                    "CREATE TABLE papers_legacy AS SELECT * FROM papers"
                )
                connection.execute("DROP TABLE papers")
                connection.execute("ALTER TABLE papers_legacy RENAME TO papers")

            init_db()
            with get_connection() as connection:
                paper = connection.execute(
                    """
                    SELECT project_id, title FROM papers WHERE id = 'legacy-paper'
                    """
                ).fetchone()
                paper_foreign_keys = foreign_key_signatures(connection, "papers")

        self.assertEqual(
            tuple(paper),
            ("legacy-project", "Readable legacy paper"),
        )
        self.assertEqual(
            paper_foreign_keys,
            FOREIGN_KEY_CONTRACTS["papers"],
        )

    def test_v2_full_text_chunk_is_conservatively_unverified_after_fts_upgrade(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                initialize_schema_v1(connection)
                connection.commit()
                initialize_schema_v2(connection)
                connection.execute(
                    """
                    INSERT INTO schema_migrations (version, name, applied_at)
                    VALUES (1, 'baseline_integrity_contract', ?),
                           (2, 'durable_local_jobs', ?)
                    """,
                    (NOW, NOW),
                )
                connection.execute("PRAGMA user_version = 2")
                connection.execute(
                    """
                    INSERT INTO projects (id, title, created_at, updated_at)
                    VALUES ('legacy-rag-project', 'Legacy RAG', ?, ?)
                    """,
                    (NOW, NOW),
                )
                connection.execute(
                    """
                    INSERT INTO papers (id, project_id, title, created_at)
                    VALUES ('legacy-rag-paper', 'legacy-rag-project', 'Legacy PDF claim', ?)
                    """,
                    (NOW,),
                )
                connection.execute(
                    """
                    INSERT INTO paper_chunks (
                        id, project_id, paper_id, chunk_index, source,
                        source_origin, evidence_level, section, page_start,
                        page_end, chunk_text, chunk_hash, created_at, updated_at
                    )
                    VALUES (
                        'legacy-rag-chunk', 'legacy-rag-project', 'legacy-rag-paper',
                        0, 'pdf.full_text', 'legacy', 'full_text', 'results',
                        4, 4, 'Legacy claim with no qualification object.',
                        'legacy-hash', ?, ?
                    )
                    """,
                    (NOW, NOW),
                )
                connection.commit()

            init_db()
            with get_connection() as connection:
                chunk = connection.execute(
                    """
                    SELECT evidence_level, evidence_verified, parser_version
                    FROM paper_chunks WHERE id = 'legacy-rag-chunk'
                    """
                ).fetchone()
                fts_count = connection.execute(
                    """
                    SELECT COUNT(*) FROM paper_chunks_fts
                    WHERE chunk_id = 'legacy-rag-chunk'
                    """
                ).fetchone()[0]

        self.assertEqual(tuple(chunk), ("full_text", 0, "legacy.unknown"))
        self.assertEqual(fts_count, 1)

    def test_failed_migration_rolls_back_without_recording_version(self) -> None:
        tmpdir, db_path = self.temporary_database()
        with tmpdir, patch.dict(
            os.environ,
            {"SCHOLARFLOW_DB_PATH": str(db_path)},
        ):
            init_db()
            with sqlite3.connect(db_path) as connection:
                connection.execute("DROP TABLE schema_migrations")
                connection.execute("PRAGMA user_version = 0")
                connection.execute(
                    """
                    INSERT INTO papers (id, project_id, title, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("legacy-orphan", "missing-project", "Legacy orphan", NOW),
                )

            with self.assertRaisesRegex(
                DatabaseMigrationError,
                "orphaned rows",
            ):
                init_db()

            with sqlite3.connect(db_path) as connection:
                orphan_count = connection.execute(
                    "SELECT COUNT(*) FROM papers WHERE id = 'legacy-orphan'"
                ).fetchone()[0]
                migration_table_count = connection.execute(
                    """
                    SELECT COUNT(*) FROM sqlite_master
                    WHERE type = 'table' AND name = 'schema_migrations'
                    """
                ).fetchone()[0]

        self.assertEqual(orphan_count, 1)
        self.assertEqual(migration_table_count, 0)


if __name__ == "__main__":
    unittest.main()
