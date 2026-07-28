from __future__ import annotations

STATEMENTS: dict[str, str] = {
    "insert_model_call_audit_1": "\n        INSERT INTO model_call_audits (\n            id, project_id, run_id, provider, model, purpose, prompt_version,\n            request_timestamp, latency_ms, response_status, fallback_reason,\n            requested_provider, requested_model, external_data_sent, created_at\n        )\n        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n        ",
    "persist_agent_run_progress_1": "\n        UPDATE agent_runs\n        SET status = ?, plan_json = ?, result_artifact_id = COALESCE(?, result_artifact_id), updated_at = ?\n        WHERE id = ?\n        ",
    "fetch_agent_run_dict_1": "SELECT * FROM agent_runs WHERE id = ?",
    "is_agent_cancellation_requested_1": "SELECT cancellation_requested FROM agent_runs WHERE id = ?",
    "run_agent_loop_1": "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
    "list_projects_1": "\n            SELECT * FROM projects\n            ORDER BY CASE WHEN id = 'local-bootstrap' OR workflow = 'demo-preview' OR stage IN ('seed', 'demo') THEN 1 ELSE 0 END,\n                     updated_at DESC,\n                     created_at DESC\n            ",
    "create_project_1": "\n            INSERT INTO projects (\n                id, title, description, keyword, field, language, workflow, stage,\n                active_session_id, created_at, updated_at\n            )\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n            ",
    "create_project_2": "\n            INSERT INTO sessions (id, project_id, title, status, created_at, updated_at)\n            VALUES (?, ?, ?, ?, ?, ?)\n            ",
    "create_project_3": "\n            INSERT INTO tool_events (id, session_id, time_label, tool, status, summary, created_at)\n            VALUES (?, ?, ?, ?, ?, ?, ?)\n            ",
    "create_project_4": "SELECT * FROM projects WHERE id = ?",
    "get_project_1": "SELECT * FROM projects WHERE id = ?",
    "list_project_papers_1": "\n            SELECT * FROM papers\n            WHERE project_id = ?\n            ORDER BY\n                CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,\n                relevance_score DESC,\n                year DESC\n            ",
    "search_project_literature_1": "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
    "persist_project_paper_card_1": "\n            INSERT INTO paper_cards (\n                id, project_id, paper_id, artifact_id, sections_json, weakest_assumption,\n                minimal_reproduction, created_at\n            )\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?)\n            ",
    "persist_project_paper_card_2": "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
    "get_project_rag_evaluations_1": "SELECT COUNT(*) AS total FROM rag_evaluations WHERE project_id = ?",
    "execute_project_direction_review_1": "\n                INSERT INTO paper_cards (\n                    id, project_id, paper_id, artifact_id, sections_json, weakest_assumption,\n                    minimal_reproduction, research_sight_json, created_at\n                )\n                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)\n                ",
    "execute_project_direction_review_2": "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
    "fetch_direction_review_run_dict_1": "SELECT * FROM direction_review_runs WHERE id = ? AND project_id = ?",
    "persist_direction_review_run_1": "SELECT notices_json FROM direction_review_runs WHERE id = ?",
    "persist_direction_review_run_2": "\n            UPDATE direction_review_runs\n            SET status = ?, stage = ?, progress = ?, message = ?, notices_json = ?,\n                result_json = COALESCE(?, result_json), updated_at = ?,\n                started_at = CASE\n                    WHEN started_at IS NULL AND ? = 'running' THEN ?\n                    ELSE started_at\n                END,\n                completed_at = CASE WHEN ? THEN ? ELSE completed_at END\n            WHERE id = ?\n            ",
    "start_project_direction_review_run_1": "\n            SELECT * FROM direction_review_runs\n            WHERE project_id = ? AND status IN ('queued', 'running')\n            ORDER BY created_at DESC\n            LIMIT 1\n            ",
    "start_project_direction_review_run_2": "\n            INSERT INTO direction_review_runs (\n                id, project_id, session_id, direction, round_index, status, stage,\n                progress, message, notices_json, result_json, created_at, updated_at, completed_at\n            )\n            VALUES (?, ?, ?, ?, ?, 'queued', 'queued', 0, ?, '[]', '', ?, ?, NULL)\n            ",
    "get_latest_project_direction_review_run_1": "\n            SELECT * FROM direction_review_runs\n            WHERE project_id = ?\n            ORDER BY created_at DESC\n            LIMIT 1\n            ",
    "create_project_research_decisions_1": "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
    "query_project_research_memory_1": "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
    "create_agent_plan_1": "\n            INSERT INTO agent_runs (\n                id, project_id, session_id, task, provider, mode, status,\n                plan_json, plan_artifact_id, result_artifact_id, cancellation_requested, created_at, updated_at\n            )\n            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n            ",
    "create_agent_plan_2": "UPDATE projects SET stage = ?, updated_at = ? WHERE id = ?",
    "cancel_agent_run_1": "UPDATE agent_runs SET cancellation_requested = ?, updated_at = ? WHERE id = ?",
    "cancel_agent_run_2": "UPDATE agent_runs SET plan_json = ?, updated_at = ? WHERE id = ?",
    "execute_agent_run_1": "UPDATE agent_runs SET status = ?, cancellation_requested = ?, updated_at = ? WHERE id = ?",
    "list_project_sessions_1": "SELECT * FROM sessions WHERE project_id = ? ORDER BY updated_at DESC",
    "get_session_timeline_1": "SELECT id FROM sessions WHERE id = ?",
    "get_session_timeline_2": "SELECT * FROM tool_events WHERE session_id = ? ORDER BY created_at ASC, rowid ASC",
    "direction_review_tool_1": "\n                INSERT INTO paper_cards (\n                    id, project_id, paper_id, artifact_id, sections_json, weakest_assumption,\n                    minimal_reproduction, research_sight_json, created_at\n                )\n                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)\n                ",
}


def statement(name: str) -> str:
    try:
        return STATEMENTS[name]
    except KeyError as error:
        raise ValueError(f"Unknown workflow SQL statement: {name}") from error
