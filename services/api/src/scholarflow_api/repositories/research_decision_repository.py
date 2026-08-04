from __future__ import annotations

import sqlite3


def update_project_stage(
    connection: sqlite3.Connection,
    project_id: str,
    stage: str,
    updated_at: str,
) -> None:
    connection.execute(
        "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
        (stage, updated_at, project_id),
    )
