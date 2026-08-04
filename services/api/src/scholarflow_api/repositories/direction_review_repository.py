from __future__ import annotations

import sqlite3
from collections.abc import Sequence


def insert_direction_paper_card(
    connection: sqlite3.Connection,
    values: Sequence[object],
) -> None:
    connection.execute(
        """
        INSERT INTO paper_cards (
            id, project_id, paper_id, artifact_id, sections_json, weakest_assumption,
            minimal_reproduction, research_sight_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )


def mark_direction_reviewed(
    connection: sqlite3.Connection,
    project_id: str,
    updated_at: str,
) -> None:
    connection.execute(
        "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
        ("direction-review", updated_at, project_id),
    )


def fetch_run(
    connection: sqlite3.Connection,
    project_id: str,
    run_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM direction_review_runs WHERE id = ? AND project_id = ?",
        (run_id, project_id),
    ).fetchone()


def fetch_run_notices(
    connection: sqlite3.Connection,
    run_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT notices_json FROM direction_review_runs WHERE id = ?",
        (run_id,),
    ).fetchone()


def update_run(
    connection: sqlite3.Connection,
    values: Sequence[object],
) -> None:
    connection.execute(
        """
        UPDATE direction_review_runs
        SET status = ?, stage = ?, progress = ?, message = ?, notices_json = ?,
            result_json = COALESCE(?, result_json), updated_at = ?,
            started_at = CASE
                WHEN started_at IS NULL AND ? = 'running' THEN ?
                ELSE started_at
            END,
            completed_at = CASE WHEN ? THEN ? ELSE completed_at END
        WHERE id = ?
        """,
        values,
    )


def find_active_run(
    connection: sqlite3.Connection,
    project_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM direction_review_runs
        WHERE project_id = ? AND status IN ('queued', 'running')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()


def insert_run(
    connection: sqlite3.Connection,
    values: Sequence[object],
) -> None:
    connection.execute(
        """
        INSERT INTO direction_review_runs (
            id, project_id, session_id, direction, round_index, status, stage,
            progress, message, notices_json, result_json, created_at, updated_at, completed_at
        )
        VALUES (?, ?, ?, ?, ?, 'queued', 'queued', 0, ?, '[]', '', ?, ?, NULL)
        """,
        values,
    )


def fetch_latest_run(
    connection: sqlite3.Connection,
    project_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM direction_review_runs
        WHERE project_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
