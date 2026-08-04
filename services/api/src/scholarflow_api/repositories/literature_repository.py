from __future__ import annotations

import sqlite3


def list_project_paper_rows(
    connection: sqlite3.Connection,
    project_id: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT * FROM papers
        WHERE project_id = ?
        ORDER BY
            CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
            relevance_score DESC,
            year DESC
        """,
        (project_id,),
    ).fetchall()


def mark_literature_retrieved(
    connection: sqlite3.Connection,
    project_id: str,
    updated_at: str,
) -> None:
    connection.execute(
        "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
        ("literature-retrieval", updated_at, project_id),
    )
