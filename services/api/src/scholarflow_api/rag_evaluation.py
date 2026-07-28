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
    supported_claims = [
        item
        for item in claims
        if isinstance(item.get("verification"), dict)
        and item["verification"].get("status") == "supported"
        and item["verification"].get("method")
        in {"exact_quote", "model_checked", "human"}
    ]
    verification_counts = {
        status: sum(
            1
            for item in claims
            if isinstance(item.get("verification"), dict)
            and item["verification"].get("status") == status
        )
        for status in ("supported", "contradicted", "insufficient", "not_checked")
    }
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
    raw_used_ids = validation.get("used_citation_ids")
    used_ids = _unique_strings(
        raw_used_ids
        if isinstance(raw_used_ids, list)
        else [
            citation_id
            for claim in supported_claims
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
    for claim in supported_claims:
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
        len(supported_claims),
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
        and bool(item.get("evidence_verified"))
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
    anchor_coverages = [
        (
            _safe_float(item.get("anchor_coverage"))
            if item.get("anchor_coverage") is not None
            else min(1.0, _safe_float(item.get("hybrid_score")) / 0.6)
        )
        for item in used_citations
    ]
    mean_anchor_coverage = (
        round(fmean(anchor_coverages), 4)
        if anchor_coverages
        else 0.0
    )
    retrieval_strength = min(
        1.0,
        mean_retrieval_score / 0.6,
        mean_anchor_coverage / 0.6,
    )
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
            "pass" if safe_refusal or supported_claims else "fail",
            (
                "无可靠命中时保持空答案，拒答边界正确。"
                if safe_refusal
                else (
                    f"{len(supported_claims)} 条主张由逐字引用、模型语义检查或人工确认直接支持。"
                    if supported_claims
                    else "响应既没有可靠拒答，也没有可核验主张。"
                )
            ),
            "补充相关论文或上传 PDF 后重新检索。"
            if not safe_refusal and not supported_claims
            else "",
        ),
        _check(
            "claim_traceability",
            "主张可追溯性",
            "pass" if claim_traceability == 1.0 else "fail",
            (
                f"{traceable_claims}/{len(supported_claims)} 条直接支持主张"
                "只使用当前响应中的 citation ID。"
            ),
            "移除无引用主张，或为每条主张绑定可见的原文证据。"
            if claim_traceability < 1.0
            else "",
        ),
        _check(
            "semantic_support_boundary",
            "语义支持边界",
            (
                "not_applicable"
                if safe_refusal
                else "pass"
                if supported_claims and not any(
                    verification_counts[item]
                    for item in ("contradicted", "insufficient", "not_checked")
                )
                else "warn"
            ),
            (
                "本次正确拒答，不进行语义支持判断。"
                if safe_refusal
                else (
                    f"直接支持 {verification_counts['supported']} 条；"
                    f"矛盾 {verification_counts['contradicted']} 条；"
                    f"证据不足 {verification_counts['insufficient']} 条；"
                    f"仅完成格式/词面检查 {verification_counts['not_checked']} 条。"
                )
            ),
            (
                "不得把词面重合显示为已验证；回到原文逐字引用、可靠语义检查或人工确认。"
                if not safe_refusal
                and any(
                    verification_counts[item]
                    for item in ("contradicted", "insufficient", "not_checked")
                )
                else ""
            ),
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
                else f"{full_text_count}/{len(used_citations)} 个已用引用来自已验证 PDF 全文。"
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
            "query_relevance",
            "问题覆盖",
            (
                "not_applicable"
                if safe_refusal
                else "pass"
                if mean_anchor_coverage >= 0.5
                else "warn"
                if mean_anchor_coverage >= 0.3
                else "fail"
            ),
            (
                "没有过阈值命中，系统执行拒答。"
                if safe_refusal
                else f"已用证据平均覆盖问题 query anchor 的 {mean_anchor_coverage:.0%}。"
            ),
            "当前片段只命中少量泛化词；请拒答、缩小问题，或补充包含任务/方法/数据集/指标锚点的原文。"
            if not safe_refusal and mean_anchor_coverage < 0.3
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
        "mean_anchor_coverage": mean_anchor_coverage,
        "retrieval_relevance": round(retrieval_strength, 4),
        "distinct_papers": distinct_papers,
        "accepted_claims": len(supported_claims),
        "rejected_claims": rejected_claim_count,
        "contradicted_claims": verification_counts["contradicted"],
        "insufficient_claims": verification_counts["insufficient"],
        "not_checked_claims": verification_counts["not_checked"],
    }
    strengths: list[str] = []
    risks: list[str] = []
    if safe_refusal:
        quality_status = "safe_refusal"
        score: float | None = None
        strengths.append("没有可靠证据时未生成答案。")
    elif not supported_claims:
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
                    0.20 * claim_traceability
                    + 0.15 * citation_integrity
                    + 0.15 * full_text_coverage
                    + 0.50 * retrieval_strength
                )
                - penalty,
            ),
            1,
        )
        strong = (
            score >= 80
            and full_text_coverage == 1.0
            and mean_retrieval_score >= 0.35
            and mean_anchor_coverage >= 0.4
            and retrieval_strength >= 0.65
            and rejected_claim_count == 0
            and not invalid_used_ids
            and not any(
                verification_counts[item]
                for item in ("contradicted", "insufficient", "not_checked")
            )
        )
        quality_status = "strong_evidence" if strong else "review_required"
        if claim_traceability == 1.0:
            strengths.append("所有最终主张都能定位到当前响应中的原文引用。")
        if full_text_coverage == 1.0:
            strengths.append("所有已用引用均来自全文证据。")

    if invalid_used_ids or rejected_citation_ids:
        risks.append("存在未知或已拒绝的 citation ID。")
    if supported_claims and full_text_coverage < 1.0:
        risks.append("部分主张仍依赖摘要级证据。")
    if supported_claims and mean_retrieval_score < 0.35:
        risks.append("已用证据与问题的检索匹配强度偏低。")
    if supported_claims and mean_anchor_coverage < 0.3:
        risks.append("已用证据只覆盖少量问题锚点，可能是在回答相邻主题而不是用户问题。")
    if rejected_claim_count:
        risks.append("生成模型曾产生未通过证据校验的候选主张。")
    if verification_counts["contradicted"]:
        risks.append("候选主张与引用在否定、比较方向、实体或关系上存在矛盾。")
    if verification_counts["not_checked"]:
        risks.append("部分候选主张仅通过引用格式和词面检查，未完成语义支持验证。")
    if supported_claims:
        risks.append("证据链分只衡量可追溯性，不代表结论真实。")

    return {
        "evaluation_id": evaluation_id,
        "quality_status": quality_status,
        "score": score,
        "metrics": metrics,
        "checks": checks,
        "strengths": list(dict.fromkeys(strengths)),
        "risk_flags": list(dict.fromkeys(risks)),
        "human_review_required": bool(supported_claims),
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
