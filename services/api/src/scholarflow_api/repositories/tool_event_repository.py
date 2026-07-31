from __future__ import annotations

from typing import Any

from scholarflow_api.database import new_id
from scholarflow_api.schemas import ToolEventStatusLiteral


def insert_tool_event(
    connection: Any,
    session_id: str,
    tool: str,
    status: ToolEventStatusLiteral,
    summary: str,
    created_at: str,
    time_label: str = "Now",
) -> None:
    connection.execute(
        """
        INSERT INTO tool_events (
            id, session_id, time_label, tool, status, summary, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("event"),
            session_id,
            time_label,
            tool,
            status,
            summary,
            created_at,
        ),
    )
