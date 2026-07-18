from __future__ import annotations

import json
import sqlite3
from statistics import fmean
from typing import Any


QUALITY_DISCLAIMER = (
    "该分数只检查可追溯性、证据等级、检索强度和拒答边界，"
    "不判断论文结论是否真实、实验是否可复现，也不能替代研究者阅读全文。"
)


def assess_rag_answer(
    answer: dict[str, Any],
    *,
    evaluation_id: str,
    evaluated_at: str,
) -> dict[str, Any]:
    claims = [
        item for item in (answer.get("claims") or [])
        if isinstance(item, dict)
    ]
    citations = [
        item for item in (answer.get("citations") or [])
        if isinstance(item, dict)
    ]
    citation_map = {
        str(item.get("citation_id") or ""): item
        for item in citations
        if str(item.get("citation_id") or "")
    }
    validation = (
        answer.get("citation_validation")
        if isinstance(answer.get("citation_validation"), dict)
        else {}
    )
    used_ids = _unique_strings(
        validation.get("used_citation_ids")
        or [
            citation_id
            for claim in claims
            for citation_id in (claim.get("citation_ids") or [])
        ]
    )
    valid_used_ids = [item for item in used_ids if item in citation_map]
    invalid_used_ids = [item for item in used_ids if item not in citation_map]
    rejected_claim_count = _safe_int(validation.get("rejected_claim_count"))
    rejected_citation_ids = _unique_strings(
        validation.get("rejected_citation_ids") or []
    )

    traceable_claims = 0
    for claim in claims:
        claim_ids = _unique_strings(claim.get("citation_ids") or [])
        if claim_ids and all(item in citation_map for item in claim_ids):
            traceable_claims += 1

    answer_kind = str(answer.get("answer_kind") or "no_answer")
    answer_status = str(answer.get("status") or "failed")
    safe_refusal = (
        answer_kind == "no_answer"
        and answer_status == "no_reliable_hit"
        and not claims
        and not citations
        and not str(answer.get("answer") or "").strip()
    )
    claim_traceability = _ratio(
        traceable_claims,
        len(claims),
        empty_value=1.0 if safe_refusal else 0.0,
    )
    citation_integrity = _ratio(
        len(valid_used_ids),
        len(used_ids),
        empty_value=1.0 if safe_refusal else 0.0,
    )
    used_citations = [citation_map[item] for item in valid_used_ids]
    full_text_count = sum(
        1
        for item in used_citations
        if item.get("evidence_level") == "full_text"
    )
    full_text_coverage = _ratio(
        full_text_count,
        len(used_citations),
        empty_value=0.0,
    )
    retrieval_scores = [
        _safe_float(item.get("hybrid_score"))
        for item in used_citations
    ]
    mean_retrieval_score = (
        round(fmean(retrieval_scores), 4)
        if retrieval_scores
        else 0.0
    )
    retrieval_strength = min(1.0, mean_retrieval_score / 0.6)
    distinct_papers = len(
        {
            str(item.get("paper_id") or "")
            for item in used_citations
            if str(item.get("paper_id") or "")
        }
    )

    checks = [
        _check(
            "answer_boundary",
            "回答边界",
            "pass" if safe_refusal or claims else "fail",
            (
                "无可靠命中时保持空答案，拒答边界正确。"
                if safe_refusal
                else (
                    f"{len(claims)} 条主张进入最终回答。"
                    if claims
                    else "响应既没有可靠拒答，也没有可核验主张。"
                )
            ),
            "补充相关论文或上传 PDF 后重新检索。" if not safe_refusal and not claims else "",
        ),
        _check(
            "claim_traceability",
            "主张可追溯性",
            "pass" if claim_traceability == 1.0 else "fail",
            f"{traceable_claims}/{len(claims)} 条主张只使用当前响应中的 citation ID。",
            "移除无引用主张，或为每条主张绑定可见的原文证据。"
            if claim_traceability < 1.0
            else "",
        ),
        _check(
            "citation_integrity",
            "引用完整性",
            "pass" if citation_integrity == 1.0 and not rejected_citation_ids else "fail",
            (
                f"{len(valid_used_ids)}/{len(used_ids)} 个已用引用可在 Citation Inspector 中定位；"
                f"拒绝引用 {len(rejected_citation_ids)} 个。"
            ),
            "检查模型输出的 citation ID，禁止引用检索上下文之外的证据。"
            if citation_integrity < 1.0 or rejected_citation_ids
            else "",
        ),
        _check(
            "full_text_coverage",
            "全文证据覆盖",
            (
                "not_applicable"
                if safe_refusal
                else "pass"
                if full_text_coverage == 1.0
                else "warn"
            ),
            (
                "本次正确拒答，不计算全文覆盖。"
                if safe_refusal
                else f"{full_text_count}/{len(used_citations)} 个已用引用来自 PDF/用户全文。"
            ),
            "为关键论文上传 PDF，避免把摘要线索当作方法或实验结论。"
            if not safe_refusal and full_text_coverage < 1.0
            else "",
        ),
        _check(
            "retrieval_strength",
            "检索强度",
            (
                "not_applicable"
                if safe_refusal
                else "pass"
                if mean_retrieval_score >= 0.35
                else "warn"
            ),
            (
                "没有过阈值命中，系统执行拒答。"
                if safe_refusal
                else f"已用证据平均 hybrid score 为 {mean_retrieval_score:.2f}。"
            ),
            "收紧问题中的任务、数据集、指标或方法术语，并检查索引内容。"
            if not safe_refusal and mean_retrieval_score < 0.35
            else "",
        ),
        _check(
            "claim_rejection",
            "生成主张过滤",
            (
                "not_applicable"
                if safe_refusal
                else "pass"
                if rejected_claim_count == 0
                else "warn"
            ),
            (
                "未调用回答生成。"
                if safe_refusal
                else f"引用校验器拒绝了 {rejected_claim_count} 条候选主张。"
            ),
            "查看被拒绝原因；若持续出现，应调整生成提示或改用逐字证据。"
            if rejected_claim_count
            else "",
        ),
    ]

    metrics: dict[str, float | int] = {
        "claim_traceability": round(claim_traceability, 4),
        "citation_integrity": round(citation_integrity, 4),
        "full_text_coverage": round(full_text_coverage, 4),
        "mean_retrieval_score": mean_retrieval_score,
        "distinct_papers": distinct_papers,
        "accepted_claims": len(claims),
        "rejected_claims": rejected_claim_count,
    }
    strengths: list[str] = []
    risks: list[str] = []
    if safe_refusal:
        quality_status = "safe_refusal"
        score: float | None = None
        strengths.append("没有可靠证据时未生成答案。")
    elif not claims:
        quality_status = "insufficient_evidence"
        score = 0.0
        risks.append("没有可核验主张进入最终回答。")
    else:
        penalty = min(20.0, rejected_claim_count * 5.0)
        score = round(
            max(
                0.0,
                100.0
                * (
                    0.30 * claim_traceability
                    + 0.25 * citation_integrity
                    + 0.25 * full_text_coverage
                    + 0.20 * retrieval_strength
                )
                - penalty,
            ),
            1,
        )
        strong = (
            score >= 80
            and full_text_coverage == 1.0
            and mean_retrieval_score >= 0.35
            and rejected_claim_count == 0
            and not invalid_used_ids
        )
        quality_status = "strong_evidence" if strong else "review_required"
        if claim_traceability == 1.0:
            strengths.append("所有最终主张都能定位到当前响应中的原文引用。")
        if full_text_coverage == 1.0:
            strengths.append("所有已用引用均来自全文证据。")

    if invalid_used_ids or rejected_citation_ids:
        risks.append("存在未知或已拒绝的 citation ID。")
    if claims and full_text_coverage < 1.0:
        risks.append("部分主张仍依赖摘要级证据。")
    if claims and mean_retrieval_score < 0.35:
        risks.append("已用证据与问题的检索匹配强度偏低。")
    if rejected_claim_count:
        risks.append("生成模型曾产生未通过证据校验的候选主张。")
    if claims:
        risks.append("自动检查不能验证论文结论、因果关系或实验可复现性。")

    return {
        "evaluation_id": evaluation_id,
        "quality_status": quality_status,
        "score": score,
        "metrics": metrics,
        "checks": checks,
        "strengths": list(dict.fromkeys(strengths)),
        "risk_flags": list(dict.fromkeys(risks)),
        "human_review_required": bool(claims),
        "disclaimer": QUALITY_DISCLAIMER,
        "evaluated_at": evaluated_at,
    }


def insert_rag_evaluation(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    answer_artifact_id: str,
    answer: dict[str, Any],
    assessment: dict[str, Any],
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO rag_evaluations (
            id, project_id, answer_artifact_id, question, answer_status,
            answer_kind, quality_status, score, generation_provider,
            generation_model, assessment_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assessment["evaluation_id"],
            project_id,
            answer_artifact_id,
            str(answer.get("question") or ""),
            str(answer.get("status") or "failed"),
            str(answer.get("answer_kind") or "no_answer"),
            str(assessment.get("quality_status") or "insufficient_evidence"),
            assessment.get("score"),
            str(answer.get("generation_provider") or ""),
            str(answer.get("generation_model") or ""),
            json.dumps(assessment, ensure_ascii=False, separators=(",", ":")),
            created_at,
        ),
    )


def list_rag_evaluations(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, project_id, answer_artifact_id, question, answer_status,
               answer_kind, quality_status, score, generation_provider,
               generation_model, assessment_json, created_at
        FROM rag_evaluations
        WHERE project_id = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            assessment = json.loads(row["assessment_json"])
        except (json.JSONDecodeError, TypeError):
            assessment = {}
        records.append(
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "answer_artifact_id": row["answer_artifact_id"],
                "question": row["question"],
                "answer_status": row["answer_status"],
                "answer_kind": row["answer_kind"],
                "quality_status": row["quality_status"],
                "score": row["score"],
                "generation_provider": row["generation_provider"],
                "generation_model": row["generation_model"],
                "assessment": assessment,
                "created_at": row["created_at"],
            }
        )
    return records


def _check(
    check_id: str,
    label: str,
    status: str,
    detail: str,
    remediation: str,
) -> dict[str, str]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
        "remediation": remediation,
    }


def _ratio(numerator: int, denominator: int, *, empty_value: float) -> float:
    if denominator <= 0:
        return empty_value
    return numerator / denominator


def _unique_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(
            normalized
            for item in value
            if (normalized := str(item or "").strip())
        )
    )


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
