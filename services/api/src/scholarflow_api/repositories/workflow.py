from __future__ import annotations

STATEMENTS: dict[str, str] = {
    "list_projects_1": "\n            SELECT * FROM projects\n            ORDER BY CASE WHEN id = 'local-bootstrap' OR workflow = 'demo-preview' OR stage IN ('seed', 'demo') THEN 1 ELSE 0 END,\n                     updated_at DESC,\n                     created_at DESC\n            ",
    "create_project_1": "\n            INSERT INTO projects (\n                id, title, description, keyword, field, language, workflow, stage,\n                active_session_id, created_at, updated_at\n            )\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n            ",
    "create_project_2": "\n            INSERT INTO sessions (id, project_id, title, status, created_at, updated_at)\n            VALUES (?, ?, ?, ?, ?, ?)\n            ",
    "create_project_3": "\n            INSERT INTO tool_events (id, session_id, time_label, tool, status, summary, created_at)\n            VALUES (?, ?, ?, ?, ?, ?, ?)\n            ",
    "create_project_4": "SELECT * FROM projects WHERE id = ?",
    "get_project_1": "SELECT * FROM projects WHERE id = ?",
    "persist_project_paper_card_1": "\n            INSERT INTO paper_cards (\n                id, project_id, paper_id, artifact_id, sections_json, weakest_assumption,\n                minimal_reproduction, created_at\n            )\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?)\n            ",
    "persist_project_paper_card_2": "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
    "list_project_sessions_1": "SELECT * FROM sessions WHERE project_id = ? ORDER BY updated_at DESC",
    "get_session_timeline_1": "SELECT id FROM sessions WHERE id = ?",
    "get_session_timeline_2": "SELECT * FROM tool_events WHERE session_id = ? ORDER BY created_at ASC, rowid ASC",
}


def statement(name: str) -> str:
    try:
        return STATEMENTS[name]
    except KeyError as error:
        raise ValueError(f"Unknown workflow SQL statement: {name}") from error
