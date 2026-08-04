from __future__ import annotations

import sqlite3


def count_project_evaluations(
    connection: sqlite3.Connection,
    project_id: str,
) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS total FROM rag_evaluations WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return int(row["total"]) if row else 0
