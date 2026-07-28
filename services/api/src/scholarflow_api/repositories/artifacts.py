from __future__ import annotations

import sqlite3
from typing import Any

from scholarflow_api.database import new_id, row_to_dict, utc_now
from scholarflow_api.schemas import ArtifactCreate


ARTIFACT_SUMMARY_SELECT = """
    SELECT
        id,
        project_id,
        title,
        kind,
        created_at,
        updated_at,
        length(CAST(content_markdown AS BLOB)) AS markdown_bytes,
        length(CAST(content_json AS BLOB)) AS json_bytes,
        substr(content_markdown, 1, 280) AS markdown_preview,
        CASE
            WHEN json_valid(content_json)
            THEN COALESCE(json_extract(content_json, '$.schema_version'), '')
            ELSE ''
        END AS json_schema_version
    FROM artifacts
"""


def list_artifact_summaries(
    connection: sqlite3.Connection,
    project_id: str,
    *,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    total_row = connection.execute(
        "SELECT COUNT(*) AS total FROM artifacts WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    rows = connection.execute(
        ARTIFACT_SUMMARY_SELECT
        + """
        WHERE project_id = ?
        ORDER BY updated_at DESC, rowid DESC
        LIMIT ? OFFSET ?
        """,
        (project_id, limit, offset),
    ).fetchall()
    return [artifact_summary_from_row(row) for row in rows], int(
        total_row["total"] if total_row else 0
    )


def create_artifact(
    connection: sqlite3.Connection,
    payload: ArtifactCreate,
) -> dict[str, Any]:
    now = utc_now()
    artifact_id = new_id("artifact")
    connection.execute(
        """
        INSERT INTO artifacts (
            id, project_id, title, kind, content_markdown, content_json,
            diff, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            payload.project_id,
            payload.title,
            payload.kind,
            payload.content_markdown,
            payload.content_json,
            payload.diff,
            now,
            now,
        ),
    )
    session_row = connection.execute(
        "SELECT active_session_id FROM projects WHERE id = ?",
        (payload.project_id,),
    ).fetchone()
    if session_row and session_row["active_session_id"]:
        connection.execute(
            """
            INSERT INTO tool_events (id, session_id, time_label, tool, status, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("event"),
                session_row["active_session_id"],
                "Now",
                "artifact.save",
                "done",
                f"已保存 artifact: {payload.title}",
                now,
            ),
        )
    connection.execute(
        "UPDATE projects SET updated_at = ? WHERE id = ?",
        (now, payload.project_id),
    )
    return get_artifact(connection, artifact_id) or {}


def get_artifact(
    connection: sqlite3.Connection,
    artifact_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM artifacts WHERE id = ?",
        (artifact_id,),
    ).fetchone()
    return row_to_dict(row)


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
