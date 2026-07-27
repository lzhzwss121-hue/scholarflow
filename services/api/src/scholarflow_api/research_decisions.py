from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from scholarflow_api.full_text import normalize_persisted_evidence_qualification
from scholarflow_api.text_utils import extract_terms, score_term_overlap


KNOWN_BASELINES = [
    "Qwen2.5-VL",
    "LLaVA-1.5",
    "GPT-4V",
    "GPT-4o",
    "Qwen2-VL",
    "Qwen-VL",
    "BLIP-2",
    "InstructBLIP",
    "MiniGPT-4",
    "mPLUG-Owl",
    "LLaVA",
]

GOAL_GENERIC_TERMS = {
    "build",
    "design",
    "day",
    "days",
    "experiment",
    "find",
    "gap",
    "idea",
    "month",
    "months",
    "novel",
    "one-week",
    "plan",
    "reproduce",
    "replicate",
    "run",
    "use",
    "week",
    "weeks",
    "实验",
    "七天",
    "计划",
    "缺口",
}

GOAL_ACTION_MARKERS = {
    "不要",
    "不使用",
    "区别",
    "区别于",
    "可复现",
    "天内",
    "并给出",
    "使用",
    "依赖",
    "明确",
    "给出",
    "设计",
    "采用",
    "排除",
    "避免",
}

GOAL_REQUIRED_MARKERS = (
    "must",
    "required",
    "require ",
    "include ",
    "compare ",
    "comparison",
    "必须",
    "需包含",
    "需要包含",
    "至少包含",
    "包含",
    "比较",
    "对比",
    "单张",
    "单卡",
)

KNOWN_EXPERIMENT_DATASETS = [
    "HallusionBench",
    "MMBench",
    "MMMU",
    "POPE",
    "CHAIR",
    "MM-Vet",
    "LLaVA-Bench",
    "SEED-Bench",
    "RealWorldQA",
    "ScienceQA",
    "MathVista",
    "ChartQA",
    "DocVQA",
    "TextVQA",
    "VQA v2",
    "OK-VQA",
    "GQA",
    "COCO",
    "ImageNet",
]

GAP_GENERIC_TERMS = {
    "analysis",
    "benchmark",
    "current",
    "dataset",
    "evaluation",
    "experiment",
    "limited",
    "limitation",
    "metric",
    "only",
    "paper",
    "result",
    "results",
    "study",
    "测试",
    "当前",
    "局限",
    "数据集",
    "方法",
    "评估",
    "论文",
}

GAP_TOPIC_MARKERS = [
    "object hallucination",
    "visual grounding",
    "evidence faithfulness",
    "single-object",
    "multi-object",
    "cross-dataset",
    "long-tail",
    "failure mode",
    "对象幻觉",
    "物体幻觉",
    "视觉定位",
    "证据忠实性",
    "单物体",
    "多物体",
    "跨数据集",
    "长尾",
    "失败模式",
]

GAP_CORROBORATION_MARKERS = {
    "single-object",
    "multi-object",
    "cross-dataset",
    "long-tail",
    "failure mode",
    "单物体",
    "多物体",
    "跨数据集",
    "长尾",
    "失败模式",
}

GAP_BROAD_TOPIC_TERMS = {
    "evidence",
    "faithfulness",
    "grounding",
    "hallucination",
    "object",
    "visual",
    "object hallucination",
    "visual grounding",
    "evidence faithfulness",
    "对象幻觉",
    "物体幻觉",
    "视觉定位",
    "证据忠实性",
}

GAP_FAILURE_CANONICAL_MARKERS = {
    "single-object": ["single-object", "single object", "单物体", "单对象"],
    "multi-object": ["multi-object", "multiple objects", "multi object", "多物体", "多对象"],
    "cross-dataset": ["cross-dataset", "cross dataset", "跨数据集"],
    "long-tail": ["long-tail", "long tail", "长尾"],
    "english-only": ["english prompt", "english-only", "only english", "仅支持英文", "英语提示"],
    "visual-conflict": [
        "conflicting visual evidence",
        "visual conflict",
        "冲突视觉证据",
        "视觉证据冲突",
    ],
    "open-ended": ["open-ended", "open ended", "开放式"],
    "distribution-shift": ["distribution shift", "out-of-distribution", "ood", "分布偏移"],
}

GAP_CONFLICT_PATTERNS = (
    r"\bnot limited to\b",
    r"\bdoes not (?:fail|degrade|suffer)\b",
    r"\bremains? robust\b",
    r"\bunaffected by\b",
    r"\bno (?:performance )?(?:drop|degradation|limitation)\b",
)


@dataclass
class DecisionIntent:
    raw_goal: str
    focus: str
    required_terms: list[str]
    contrast_terms: list[str]
    excluded_terms: list[str]
    contribution_type: str
    time_budget_days: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GapDecision:
    id: str
    title: str
    kind: str
    evidence: str
    weakness: str
    opportunity: str
    novelty_risk: str
    feasibility: str
    support_status: str = "insufficient"
    confidence: str = "low"
    paper_ids: list[str] = field(default_factory=list)
    evidence_refs: list[dict[str, str]] = field(default_factory=list)
    validation_requirements: list[str] = field(default_factory=list)
    gap_signature: dict[str, str] = field(default_factory=dict)
    consistency_score: float = 0.0
    conflict_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IdeaValidation:
    idea: str
    why_not_incremental: str
    difference_from_existing_work: str
    novelty_risk: str
    feasibility: str
    key_risks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentPlan:
    status: str
    anchor_paper_id: str
    anchor_paper_title: str
    claim: str
    dataset: str
    baseline: str
    metrics: list[str]
    ablations: list[str]
    resources: str
    timeline: list[str]
    success_criterion: str
    failure_criterion: str
    unblock_suggestions: list[str] = field(default_factory=list)
    goal_alignment: dict[str, Any] = field(default_factory=dict)
    readiness_checks: dict[str, str] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentAnchor:
    paper_title: str
    paper_id: str
    card: dict[str, Any]
    paper: dict[str, Any]
    claim: str
    dataset: str
    baseline: str
    metrics: list[str]
    minimal_reproduction: str
    reason: str
    score: float
    goal_alignment: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchDecisionBundle:
    project_title: str
    gaps: list[GapDecision]
    validation: IdeaValidation
    experiment: ExperimentPlan
    decision_status: str = "complete"
    evidence_quality: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    decision_intent: DecisionIntent | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_title": self.project_title,
            "gaps": [gap.to_dict() for gap in self.gaps],
            "validation": self.validation.to_dict(),
            "experiment": self.experiment.to_dict(),
            "decision_status": self.decision_status,
            "evidence_quality": self.evidence_quality,
            "warnings": self.warnings,
            "decision_intent": self.decision_intent.to_dict() if self.decision_intent else None,
        }


def generate_research_decisions(
    project: dict[str, Any],
    papers: list[dict[str, Any]],
    paper_cards: list[dict[str, Any]],
    goal: str = "",
) -> ResearchDecisionBundle:
    evidence_papers = filter_evidence_papers(papers)
    gap_evidence_papers = filter_gap_evidence_papers(evidence_papers, paper_cards)
    evidence_quality = build_evidence_quality(papers, evidence_papers, gap_evidence_papers, paper_cards)
    decision_status = evidence_quality["decision_status"]
    focus = infer_focus(project, gap_evidence_papers or evidence_papers, paper_cards, goal)
    decision_intent = parse_decision_intent(goal, focus)
    top_papers = (
        ", ".join(paper.get("title", "") for paper in gap_evidence_papers[:3] if paper.get("title"))
        or "当前没有 strong/medium 相关论文可作为 gap evidence（且非 survey-only）"
    )
    anchor = select_experiment_anchor(gap_evidence_papers, paper_cards, decision_intent)
    unblock_suggestions = (
        build_unblock_suggestions(gap_evidence_papers, paper_cards, decision_intent) if anchor is None else []
    )
    grounded_evidence = collect_grounded_gap_evidence(gap_evidence_papers, paper_cards)
    evidence_groups = group_grounded_gap_evidence(grounded_evidence)
    corroborated_groups = [
        group for group in evidence_groups
        if is_corroborated_gap_group(group)
    ]
    evidence_quality["grounded_gap_evidence_count"] = len(grounded_evidence)
    evidence_quality["specific_gap_evidence_count"] = sum(
        1 for item in grounded_evidence
        if gap_signature_is_specific(normalized_gap_signature(item))
    )
    evidence_quality["corroborated_gap_group_count"] = len(corroborated_groups)
    evidence_quality["conflicted_gap_group_count"] = sum(
        1 for group in evidence_groups
        if any(gap_evidence_has_conflict(item) for item in group)
    )
    if decision_status == "complete" and not grounded_evidence:
        decision_status = "partial"
        evidence_quality["decision_status"] = decision_status
    if decision_status == "complete" and len(grounded_evidence) < 2:
        decision_status = "partial"
        evidence_quality["decision_status"] = decision_status
    if decision_status == "complete" and not corroborated_groups:
        decision_status = "partial"
        evidence_quality["decision_status"] = decision_status
    warnings = build_evidence_quality_warnings(evidence_quality)
    gaps = build_gap_decisions(
        decision_status=decision_status,
        top_papers=top_papers,
        grounded_evidence=grounded_evidence,
        evidence_groups=evidence_groups,
    )

    validation = build_idea_validation(
        focus,
        decision_status,
        warnings,
        corroborated_groups[0] if corroborated_groups else [],
    )

    experiment = build_experiment_plan_from_anchor(anchor, focus, unblock_suggestions, decision_intent)

    if experiment.status in {"blocked", "partial"} and decision_status == "complete":
        decision_status = "partial"
        evidence_quality["decision_status"] = decision_status
        warnings.append(
            "实验计划尚未达到 ready；Gap Board 与实验建议只能作为 partial 决策参考。",
        )

    return ResearchDecisionBundle(
        project_title=project.get("title") or "ScholarFlow Project",
        gaps=gaps,
        validation=validation,
        experiment=experiment,
        decision_status=decision_status,
        evidence_quality=evidence_quality,
        warnings=unique_preserve_order(warnings),
        decision_intent=decision_intent,
    )


def build_gap_decisions(
    decision_status: str,
    top_papers: str,
    grounded_evidence: list[dict[str, Any]],
    evidence_groups: list[list[dict[str, Any]]] | None = None,
) -> list[GapDecision]:
    if not grounded_evidence:
        reason = (
            "无法判断：当前没有足够的 metadata.abstract 或 pdf.full_text 原文片段来证明一个方向级 gap。"
            f" 候选论文：{top_papers}。"
        )
        return [
            GapDecision(
                id="gap_evidence_boundary",
                title="证据不足：暂不认定确定科研缺口",
                kind="pseudo_gap",
                evidence=reason,
                weakness="上游候选或 Paper Card 仍缺少可定位的 claim、limitation、dataset、metric 或 baseline 原文证据。",
                opportunity="先补齐可追溯的 PDF/摘要证据，再比较不同论文是否报告了同一失败模式。",
                novelty_risk="high",
                feasibility="one-month",
                validation_requirements=[
                    "至少补充 2 篇独立论文的可定位 limitation 原文。",
                    "确认两篇论文讨论的是同一任务、失败模式和评价协议。",
                ],
            ),
            GapDecision(
                id="gap_anchor_missing_fields",
                title="证据字段尚未形成可复现实验 anchor",
                kind="pseudo_gap",
                evidence="无法判断：没有证据支持通用反例或 benchmark 批判是否适用于当前论文集合。",
                weakness="缺少同一论文绑定的 claim + dataset + metric + baseline 时，任何一周实验计划都只是泛化建议。",
                opportunity="为一篇非 survey 论文补充原文实验段，并把四个字段绑定到对应 paper_id。",
                novelty_risk="high",
                feasibility="one-month",
                validation_requirements=[
                    "同一 paper_id 下绑定 claim、dataset、metric 与 baseline。",
                    "先复现原论文现象，再讨论新方法。",
                ],
            ),
        ]

    groups = evidence_groups or group_grounded_gap_evidence(grounded_evidence)
    decisions: list[GapDecision] = []
    if decision_status != "complete":
        decisions.append(
            GapDecision(
                id="gap_evidence_boundary",
                title="证据规模或一致性不足：只展示待验证候选",
                kind="pseudo_gap",
                evidence=(
                    f"当前有 {len(grounded_evidence)} 条可定位 limitation 证据，但尚未同时满足方向覆盖、"
                    f"全文证据和同一失败模式独立佐证。候选论文：{top_papers}。"
                ),
                weakness="数量达标不等于语义一致；不同论文的 limitation 不能直接合并成方向级科研缺口。",
                opportunity="先按失败模式聚类，再在统一 dataset、metric 和 baseline 下复核同一限制。",
                novelty_risk="high",
                feasibility="one-month",
                support_status="insufficient",
                confidence="low",
                paper_ids=unique_preserve_order(
                    [str(item.get("paper_id", "")) for item in grounded_evidence]
                ),
                evidence_refs=[build_gap_evidence_ref(item) for item in grounded_evidence[:3]],
                validation_requirements=[
                    "至少补足 2 篇独立论文中可定位、可比较的同类失败模式证据。",
                    "同一失败模式至少由 2 篇独立论文的 PDF 全文直接支持。",
                ],
            ),
        )

    for index, group in enumerate(groups, start=1):
        if len(decisions) >= 4:
            break
        primary = group[0]
        corroborated = is_corroborated_gap_group(group)
        conflict_detected = any(gap_evidence_has_conflict(item) for item in group)
        consistency_score = gap_group_consistency_score(group)
        can_label_true_gap = decision_status == "complete" and corroborated
        paper_ids = unique_preserve_order([str(item.get("paper_id", "")) for item in group])
        evidence_refs = [build_gap_evidence_ref(item) for item in group]
        evidence_lines = [
            format_grounded_gap_evidence(item)
            for item in group[:3]
        ]
        decisions.append(
            GapDecision(
                id=f"gap_group_{index}",
                title=(
                    f"跨论文待验证缺口：{primary['title']}"
                    if can_label_true_gap
                    else f"单篇/弱佐证限制：{primary['title']}"
                ),
                kind="true_gap" if can_label_true_gap else "engineering_gap",
                evidence=" 独立证据：".join(
                    ["同一失败模式已形成可追溯候选。" if corroborated else "当前仅能确认论文自身限制。", "；".join(evidence_lines)]
                ),
                weakness=(
                    "两篇独立论文报告了语义相近限制，但尚未证明它们由同一机制导致，也未完成相邻工作 novelty 检索。"
                    if corroborated
                    else "只有单篇或弱语义佐证，不能外推为方向共识，也不能直接声称 novelty。"
                ),
                opportunity=(
                    "在统一 dataset、metric、强 baseline 和失败样本切片下复核该限制；复现后再决定方法创新。"
                ),
                novelty_risk="medium" if can_label_true_gap else "high",
                feasibility="one-month",
                support_status=(
                    "conflicted"
                    if conflict_detected
                    else "corroborated"
                    if corroborated
                    else "single_source"
                ),
                confidence="medium" if can_label_true_gap else "low",
                paper_ids=paper_ids,
                evidence_refs=evidence_refs,
                gap_signature=normalized_gap_signature(primary),
                consistency_score=consistency_score,
                conflict_detected=conflict_detected,
                validation_requirements=[
                    "固定同一任务、dataset、metric 与 baseline，复现限制是否稳定出现。",
                    "检索相邻工作，确认该限制尚未被已有方法或评价协议解决。",
                    "预注册成功/失败判据，并保留不能复现的反证。",
                ],
            ),
        )
    return decisions


def collect_grounded_gap_evidence(
    papers: list[dict[str, Any]],
    paper_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cards_by_paper_id = {str(card.get("paper_id") or ""): card for card in paper_cards if card.get("paper_id")}
    grounded: list[dict[str, Any]] = []
    for paper in papers:
        card = cards_by_paper_id.get(str(paper.get("id") or ""), {})
        qualification = card_evidence_qualification(card)
        signals = card.get("signals") if isinstance(card.get("signals"), dict) else {}
        limitation = normalize_space(signals.get("limitation", ""))
        if limitation.startswith("当前证据不足"):
            limitation = ""
        if not limitation:
            continue
        signal_evidence = signals.get("signal_evidence") if isinstance(signals.get("signal_evidence"), dict) else {}
        limitation_evidence = (
            signal_evidence.get("limitation") if isinstance(signal_evidence.get("limitation"), dict) else None
        )
        source_snippet = normalize_limitation_evidence(limitation_evidence)
        if source_snippet is None:
            source_snippet = find_legacy_limitation_snippet(card, limitation)
        if source_snippet is None:
            continue
        item = {
            "paper_id": normalize_space(paper.get("id", "")),
            "title": normalize_space(paper.get("title", "")) or "Untitled paper",
            "snippet_id": normalize_space(source_snippet.get("id", "")) or "source_snippet",
            "source": normalize_space(source_snippet.get("source", "")),
            "snippet": normalize_space(source_snippet.get("text", ""))[:280],
            "limitation": limitation,
            "section": normalize_space(source_snippet.get("section", "")),
            "page": normalize_space(source_snippet.get("page", "")),
            "evidence_level": qualification.level,
            "verified_full_text": (
                qualification.level == "full_text" and qualification.verified
            ),
        }
        item["signature"] = build_gap_evidence_signature(item, signals)
        item["specific"] = gap_signature_is_specific(item["signature"])
        item["conflict"] = gap_evidence_has_conflict(item)
        grounded.append(item)
    return grounded


def build_gap_evidence_signature(
    item: dict[str, Any],
    signals: dict[str, Any] | None = None,
) -> dict[str, str]:
    signals = signals or {}
    text = normalize_space(f"{item.get('limitation', '')} {item.get('snippet', '')}")
    lower = text.lower()
    failure_mode = ""
    for canonical, markers in GAP_FAILURE_CANONICAL_MARKERS.items():
        if any(marker in lower for marker in markers):
            failure_mode = canonical
            break
    if not failure_mode:
        failure_mode = extract_specific_gap_phrase(lower)
    dataset = clean_signal_value(signals.get("dataset", ""))
    metric = clean_signal_value(signals.get("metric", ""))
    return {
        "failure_mode": failure_mode,
        "affected_capability": extract_gap_affected_capability(lower),
        "condition": extract_gap_condition(lower, failure_mode),
        "consequence": extract_gap_consequence(lower),
        "evaluation_context": " | ".join(value for value in [dataset, metric] if value),
        "dataset_or_slice": dataset,
        "metric_or_observation": metric,
        "source_level": (
            "full_text"
            if item.get("verified_full_text") is True
            and normalize_space(item.get("source", "")) == "pdf.full_text"
            else "abstract_only"
        ),
    }


def extract_specific_gap_phrase(text: str) -> str:
    patterns = [
        r"\blimited (?:to|by|in)\s+([^.;。；]{3,90})",
        r"\bonly (?:supports?|covers?|evaluates?|handles?|works? (?:for|on|with))\s+([^.;。；]{3,90})",
        r"\b(?:cannot|unable to|fails? to|struggles? to)\s+([^.;。；]{3,90})",
        r"\b(?:fails?|degrades?|breaks?)\s+(?:under|when|on|for|with)\s+([^.;。；]{3,90})",
        r"(?:仅支持|仅覆盖|无法处理|不能处理|受限于)\s*([^。；;]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        phrase = normalize_signature_phrase(match.group(1))
        if phrase and not gap_phrase_is_generic(phrase):
            return phrase
    return ""


def extract_gap_condition(text: str, failure_mode: str) -> str:
    if failure_mode in GAP_FAILURE_CANONICAL_MARKERS:
        return failure_mode
    patterns = [
        r"\b(?:under|when|on|for|with|in)\s+([^.;。；]{3,70})",
        r"\blimited (?:to|by|in)\s+([^.;。；]{3,70})",
        r"\bonly (?:supports?|covers?|evaluates?|handles?)\s+([^.;。；]{3,70})",
        r"(?:在|当|对于|受限于)\s*([^，。；;]{2,50})(?:时|下|中|范围)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            phrase = normalize_signature_phrase(match.group(1))
            if phrase and not gap_phrase_is_generic(phrase):
                return phrase
    return ""


def extract_gap_consequence(text: str) -> str:
    if re.search(
        r"\blimited (?:to|by|in)\b|\bonly (?:supports?|covers?|evaluates?|handles?)\b|仅支持|仅覆盖|受限于",
        text,
    ):
        return "coverage_restriction"
    if re.search(r"\b(?:cannot|unable to|fails? to|struggles? to)\b|无法|不能", text):
        return "capability_failure"
    if re.search(r"\b(?:degrades?|drops?|worse|reduced?|declines?)\b|下降|退化", text):
        return "performance_degradation"
    if re.search(r"\b(?:increases?|causes?|leads? to)\b.{0,40}\bhallucination\b|导致.{0,20}幻觉", text):
        return "hallucination_increase"
    return ""


def extract_gap_affected_capability(text: str) -> str:
    capability_markers = [
        ("visual_grounding", ["visual grounding", "grounding evidence", "视觉定位", "视觉证据"]),
        ("hallucination_control", ["hallucination", "幻觉"]),
        ("evaluation_coverage", ["evaluation", "benchmark", "评估", "评测"]),
        ("generalization", ["generalization", "generalize", "泛化"]),
        ("language_coverage", ["english", "language", "语言", "英文"]),
        ("multi_object_reasoning", ["multi-object", "multiple objects", "多物体"]),
    ]
    for canonical, markers in capability_markers:
        if any(marker in text for marker in markers):
            return canonical
    return ""


def normalize_signature_phrase(value: str) -> str:
    terms = [
        term
        for term in extract_terms(normalize_space(value).lower(), limit=10)
        if term not in GAP_GENERIC_TERMS and term not in GAP_BROAD_TOPIC_TERMS
    ]
    return " ".join(sorted(unique_preserve_order(terms)))[:100]


def gap_phrase_is_generic(value: str) -> bool:
    terms = {
        term
        for term in extract_terms(value, limit=12)
        if term not in GAP_GENERIC_TERMS and term not in GAP_BROAD_TOPIC_TERMS
    }
    return not terms or terms.issubset({"following", "several", "some", "two", "three", "future", "work"})


def clean_signal_value(value: Any) -> str:
    return re.sub(
        r"^(?:方法证据|核心 claim 证据|本论文自身局限|已有研究不足|Baseline evidence)\s*[:：]\s*",
        "",
        normalize_space(value),
        flags=re.IGNORECASE,
    )


def gap_signature_is_specific(signature: dict[str, str]) -> bool:
    failure_mode = normalize_space(signature.get("failure_mode", ""))
    if not failure_mode or gap_phrase_is_generic(failure_mode):
        return False
    return bool(
        normalize_space(signature.get("condition", ""))
        or normalize_space(signature.get("consequence", ""))
    )


def gap_evidence_has_conflict(item: dict[str, Any]) -> bool:
    text = normalize_space(f"{item.get('limitation', '')} {item.get('snippet', '')}").lower()
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in GAP_CONFLICT_PATTERNS)


def group_grounded_gap_evidence(
    grounded_evidence: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for item in grounded_evidence:
        for group in groups:
            # Complete-link grouping prevents A≈B and B≈C from silently
            # promoting A and C into one direction-level gap.
            if all(gap_evidence_is_semantically_related(item, member) for member in group):
                group.append(item)
                break
        else:
            groups.append([item])
    return sorted(
        groups,
        key=lambda group: (
            -len({normalize_space(item.get("paper_id", "")) for item in group}),
            str(group[0].get("title", "")) if group else "",
        ),
    )


def gap_evidence_is_semantically_related(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    return gap_evidence_consistency_score(left, right) >= 0.70


def gap_signature_terms(item: dict[str, Any]) -> set[str]:
    text = normalize_space(f"{item.get('limitation', '')} {item.get('snippet', '')}").lower()
    terms = {
        term
        for term in extract_terms(text, limit=32)
        if term not in GAP_GENERIC_TERMS
    }
    terms.update(marker for marker in GAP_TOPIC_MARKERS if marker in text)
    return terms


def gap_evidence_consistency_score(
    left: dict[str, Any],
    right: dict[str, Any],
) -> float:
    left_signature = normalized_gap_signature(left)
    right_signature = normalized_gap_signature(right)
    if not gap_signature_is_specific(left_signature) or not gap_signature_is_specific(right_signature):
        return 0.0
    score = (
        0.45 * signature_component_similarity(left_signature["failure_mode"], right_signature["failure_mode"])
        + 0.25 * signature_component_similarity(left_signature["condition"], right_signature["condition"])
        + 0.20 * signature_component_similarity(left_signature["consequence"], right_signature["consequence"])
        + 0.10
        * signature_component_similarity(
            left_signature["evaluation_context"],
            right_signature["evaluation_context"],
        )
    )
    return round(score, 4)


def normalized_gap_signature(item: dict[str, Any]) -> dict[str, str]:
    signature = item.get("signature")
    if isinstance(signature, dict):
        return {
            key: normalize_space(signature.get(key, ""))
            for key in [
                "failure_mode",
                "affected_capability",
                "condition",
                "consequence",
                "evaluation_context",
                "dataset_or_slice",
                "metric_or_observation",
                "source_level",
            ]
        }
    return build_gap_evidence_signature(item)


def signature_component_similarity(left: str, right: str) -> float:
    left_value = normalize_space(left).lower()
    right_value = normalize_space(right).lower()
    if not left_value or not right_value:
        return 0.0
    if left_value == right_value:
        return 1.0
    left_terms = {
        term
        for term in extract_terms(left_value, limit=16)
        if term not in GAP_GENERIC_TERMS
    }
    right_terms = {
        term
        for term in extract_terms(right_value, limit=16)
        if term not in GAP_GENERIC_TERMS
    }
    union = left_terms | right_terms
    return len(left_terms & right_terms) / len(union) if union else 0.0


def gap_group_consistency_score(group: list[dict[str, Any]]) -> float:
    pair_scores = [
        gap_evidence_consistency_score(left, right)
        for index, left in enumerate(group)
        for right in group[index + 1 :]
        if normalize_space(left.get("paper_id", ""))
        != normalize_space(right.get("paper_id", ""))
    ]
    return round(min(pair_scores), 4) if pair_scores else 0.0


def is_corroborated_gap_group(group: list[dict[str, Any]]) -> bool:
    paper_ids = {
        normalize_space(item.get("paper_id", ""))
        for item in group
        if normalize_space(item.get("paper_id", ""))
    }
    full_text_paper_ids = {
        normalize_space(item.get("paper_id", ""))
        for item in group
        if normalize_space(item.get("paper_id", ""))
        and normalize_space(item.get("source", "")) == "pdf.full_text"
        and item.get("verified_full_text") is True
        and gap_signature_is_specific(normalized_gap_signature(item))
    }
    return (
        len(paper_ids) >= 2
        and len(full_text_paper_ids) >= 2
        and not any(gap_evidence_has_conflict(item) for item in group)
        and gap_group_consistency_score(group) >= 0.70
    )


def build_gap_evidence_ref(item: dict[str, Any]) -> dict[str, str]:
    return {
        "paper_id": normalize_space(item.get("paper_id", "")),
        "paper_title": normalize_space(item.get("title", "")),
        "snippet_id": normalize_space(item.get("snippet_id", "")),
        "source": normalize_space(item.get("source", "")),
        "section": normalize_space(item.get("section", "")),
        "page": normalize_space(item.get("page", "")),
        "text": normalize_space(item.get("snippet", "")),
        "evidence_level": normalize_space(item.get("evidence_level", "")),
    }


def format_grounded_gap_evidence(item: dict[str, Any]) -> str:
    locator = " / ".join(
        part
        for part in [
            normalize_space(item.get("section", "")),
            f"p.{normalize_space(item.get('page', ''))}" if normalize_space(item.get("page", "")) else "",
        ]
        if part
    )
    return (
        f"[paper_id={normalize_space(item.get('paper_id', '')) or 'unknown'}；"
        f"{normalize_space(item.get('snippet_id', '')) or 'source_snippet'}；"
        f"{normalize_space(item.get('source', '')) or 'unknown'}"
        f"{f'；{locator}' if locator else ''}] "
        f"{normalize_space(item.get('snippet', ''))}"
    )


def normalize_limitation_evidence(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    source = normalize_space(value.get("source", ""))
    quote = normalize_space(value.get("quote", ""))
    validation_errors = value.get("validation_errors")
    if source not in {"metadata.abstract", "pdf.full_text"} or not quote:
        return None
    if isinstance(validation_errors, list) and validation_errors:
        return None
    page = value.get("page")
    section = normalize_space(value.get("section", ""))
    locator = section or "unknown"
    if page not in (None, ""):
        locator += f"-p{page}"
    return {
        "id": f"signal-limitation-{locator}",
        "source": source,
        "text": quote,
        "section": section,
        "page": page,
    }


def find_legacy_limitation_snippet(card: dict[str, Any], limitation: str) -> dict[str, Any] | None:
    sight = parse_json_object(card.get("research_sight_json", "{}"))
    pack = sight.get("evidence_pack") if isinstance(sight.get("evidence_pack"), dict) else {}
    snippets = pack.get("snippets") if isinstance(pack.get("snippets"), list) else []
    limitation_text = normalize_space(re.sub(r"^(本论文自身局限|原文限制信号)\s*[:：]\s*", "", limitation))
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        text = normalize_space(snippet.get("text", ""))
        if snippet.get("source") not in {"metadata.abstract", "pdf.full_text"} or not text:
            continue
        if limitation_text and (
            limitation_text.lower() in text.lower()
            or text.lower() in limitation_text.lower()
        ):
            return snippet
    return None


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_idea_validation(
    focus: str,
    decision_status: str,
    warnings: list[str],
    corroborated_evidence: list[dict[str, Any]],
) -> IdeaValidation:
    if decision_status != "complete" or len(corroborated_evidence) < 2:
        return IdeaValidation(
            idea=(
                f"围绕 `{focus}` 暂不输出确定性研究判断：当前 strong/medium 且非 survey-only 的证据不足，"
                "只能先做检索补强和证据审计。"
            ),
            why_not_incremental=(
                "不可下结论：证据池不足时，无法区分真 gap、benchmark 偏差和单篇论文偶然观察。"
            ),
            difference_from_existing_work=(
                "下一步不是提出新方法，而是先补足可引用证据、baseline、dataset、metric 和失败模式样本。"
            ),
            novelty_risk="high",
            feasibility="one-week",
            key_risks=warnings
            or [
                "strong/medium 论文数量不足，容易把弱相关论文误当成研究证据。",
                "缺少非 survey 的方法或 benchmark paper，无法支撑可实验 gap。",
            ],
        )
    anchor = corroborated_evidence[0]
    corroborating = corroborated_evidence[1]
    evidence_label = f"{anchor['title']} / {anchor['snippet_id']} / {anchor['source']}"
    corroborating_label = (
        f"{corroborating['title']} / {corroborating['snippet_id']} / {corroborating['source']}"
    )
    return IdeaValidation(
        idea=(
            f"推断性 idea：围绕 `{focus}` 复核 `{anchor['limitation']}` 是否稳定存在。"
            f"主证据锚点：{evidence_label}；独立复核锚点：{corroborating_label}。"
        ),
        why_not_incremental=(
            "两篇论文都有可定位限制证据，但只有当这些限制在同一任务、强 baseline 和同一数据/指标协议下复现时，"
            "才有资格进一步判断它是否构成非增量研究入口。"
        ),
        difference_from_existing_work=(
            f"当前无法声称优于已有工作；可验证差异仅是把 `{anchor['limitation']}` 作为待复核对象，"
            f"并用 `{corroborating['limitation']}` 作为独立证据边界；后续必须补充明确 baseline、dataset 与 metric 对照。"
        ),
        novelty_risk="high",
        feasibility="one-month",
        key_risks=[
            f"两篇锚点 {evidence_label} / {corroborating_label} 的 limitation 未必语义等价，仍不能外推为方向共识。",
            "需要用统一协议复现实证，确认二者是否属于同一失败机制。",
            "如果 baseline、dataset、metric 不能固定，差异可能只是实验设置变化。",
        ],
    )


def filter_evidence_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [paper for paper in papers if is_relevant_evidence_paper(paper)]


def filter_gap_evidence_papers(papers: list[dict[str, Any]], paper_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    card_by_paper_id = {card.get("paper_id", ""): card for card in paper_cards if card.get("paper_id")}
    return [paper for paper in papers if not is_survey_like(paper, card_by_paper_id.get(paper.get("id", ""), {}))]


def build_evidence_quality(
    papers: list[dict[str, Any]],
    evidence_papers: list[dict[str, Any]],
    gap_evidence_papers: list[dict[str, Any]],
    paper_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    strong_count = sum(1 for paper in papers if normalize_space(paper.get("relevance_quality", "")).lower() == "strong")
    medium_count = sum(1 for paper in papers if normalize_space(paper.get("relevance_quality", "")).lower() == "medium")
    survey_only_count = max(0, len(evidence_papers) - len(gap_evidence_papers))
    evidence_paper_ids = {
        normalize_space(paper.get("id", ""))
        for paper in evidence_papers
        if normalize_space(paper.get("id", ""))
    }
    card_level_rank = {
        "metadata_only": 0,
        "abstract_only": 1,
        "supplemental_text": 2,
        "full_text": 3,
    }
    relevant_card_by_paper_id: dict[str, dict[str, Any]] = {}
    for card in paper_cards:
        paper_id = normalize_space(card.get("paper_id", ""))
        if paper_id not in evidence_paper_ids:
            continue
        current = relevant_card_by_paper_id.get(paper_id)
        current_level = (
            card_evidence_qualification(current).level
            if current
            else "metadata_only"
        )
        candidate_level = card_evidence_qualification(card).level
        if current is None or card_level_rank.get(candidate_level, -1) >= card_level_rank.get(current_level, -1):
            relevant_card_by_paper_id[paper_id] = card
    relevant_cards = list(relevant_card_by_paper_id.values())
    linked_card_count = len(relevant_cards)
    evidence_level_counts = count_card_evidence_levels(relevant_cards)
    if len(gap_evidence_papers) == 0:
        decision_status = "blocked"
    elif linked_card_count == 0 or evidence_level_counts["full_text"] == 0:
        decision_status = "partial"
    else:
        decision_status = "complete"
    return {
        "decision_status": decision_status,
        "total_paper_count": len(papers),
        "strong_match_count": strong_count,
        "medium_match_count": medium_count,
        "evidence_paper_count": len(evidence_papers),
        "gap_evidence_paper_count": len(gap_evidence_papers),
        "survey_only_count": survey_only_count,
        "linked_card_count": linked_card_count,
        "metadata_only_card_count": evidence_level_counts["metadata_only"],
        "abstract_only_card_count": evidence_level_counts["abstract_only"],
        "supplemental_text_card_count": evidence_level_counts["supplemental_text"],
        "full_text_card_count": evidence_level_counts["full_text"],
        "unknown_evidence_card_count": evidence_level_counts["unknown"],
        "minimum_true_gap_paper_count": 2,
        "minimum_true_gap_full_text_count": 2,
        "minimum_gap_consistency_score": 0.70,
    }


def count_card_evidence_levels(paper_cards: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "metadata_only": 0,
        "abstract_only": 0,
        "supplemental_text": 0,
        "full_text": 0,
        "unknown": 0,
    }
    for card in paper_cards:
        level = card_evidence_qualification(card).level
        if level not in counts:
            level = "unknown"
        counts[level] += 1
    return counts


def card_evidence_qualification(card: dict[str, Any] | None):
    card = card or {}
    paper = card.get("paper") if isinstance(card.get("paper"), dict) else {}
    has_abstract = bool(
        normalize_space(
            card.get("paper_abstract", "")
            or paper.get("abstract", ""),
        ),
    )
    return normalize_persisted_evidence_qualification(
        card.get("evidence_qualification"),
        card.get("full_text"),
        has_abstract=has_abstract,
    )


def card_has_verified_full_text(card: dict[str, Any] | None) -> bool:
    qualification = card_evidence_qualification(card)
    return qualification.level == "full_text" and qualification.verified


def build_evidence_quality_warnings(evidence_quality: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    gap_count = int(evidence_quality.get("gap_evidence_paper_count") or 0)
    linked_card_count = int(evidence_quality.get("linked_card_count") or 0)
    full_text_count = int(evidence_quality.get("full_text_card_count") or 0)
    limited_card_count = int(evidence_quality.get("metadata_only_card_count") or 0) + int(
        evidence_quality.get("abstract_only_card_count") or 0
    ) + int(evidence_quality.get("supplemental_text_card_count") or 0)
    if gap_count == 0:
        warnings.append("Gap evidence 不足：没有 strong/medium 且非 survey-only 的论文，不能下确定性研究结论。")
    if linked_card_count == 0:
        warnings.append("缺少绑定真实论文的 Paper Card；idea validation 只能给保守建议。")
    if limited_card_count > 0 and full_text_count == 0:
        warnings.append("当前 Paper Card 主要是摘要级/元数据级证据，不是全文级深读结论。")
    if int(evidence_quality.get("survey_only_count") or 0) > 0:
        warnings.append("Survey/review 论文只用于背景，不作为主要 gap evidence。")
    grounded_count = int(evidence_quality.get("grounded_gap_evidence_count") or 0)
    specific_count = int(evidence_quality.get("specific_gap_evidence_count") or 0)
    corroborated_count = int(evidence_quality.get("corroborated_gap_group_count") or 0)
    conflicted_count = int(evidence_quality.get("conflicted_gap_group_count") or 0)
    if gap_count > 0 and grounded_count == 0:
        warnings.append("未找到同时绑定 paper_id、原文 snippet 与 limitation 的 Gap evidence；不能生成确定性 gap。")
    elif grounded_count > 0 and specific_count < 2:
        warnings.append("可定位 limitation 中少于 2 条包含具体 failure mode、条件与后果；不能升级为方向级 gap。")
    elif grounded_count < 2:
        warnings.append("方向级 Gap 至少需要 2 篇独立论文的可定位限制证据；当前只能作为单篇观察。")
    elif corroborated_count == 0:
        warnings.append("现有 limitation 没有形成两篇全文、相似度不低于 0.70 的跨论文失败模式；不能认定 true gap。")
    if conflicted_count:
        warnings.append(f"发现 {conflicted_count} 个包含直接冲突信号的候选组；这些组不会升级为 true gap。")
    return warnings


def is_relevant_evidence_paper(paper: dict[str, Any]) -> bool:
    quality = normalize_space(paper.get("relevance_quality", "")).lower()
    if quality in {"strong", "medium"}:
        return True
    if quality in {"weak", "off_topic"}:
        return False
    priority = normalize_space(paper.get("priority", ""))
    return priority in {"High", "Medium"}


def select_experiment_anchor(
    papers: list[dict[str, Any]],
    paper_cards: list[dict[str, Any]],
    intent: DecisionIntent | None = None,
) -> ExperimentAnchor | None:
    paper_by_id = {paper.get("id", ""): paper for paper in papers if paper.get("id")}
    candidates: list[ExperimentAnchor] = []
    for card in paper_cards:
        paper = paper_by_id.get(card.get("paper_id", "") or "", {})
        if not is_real_paper_anchor(paper, card):
            continue
        merged_paper = merge_card_paper(card, paper)
        if is_survey_like(merged_paper, card):
            continue
        anchor = build_experiment_anchor_candidate(merged_paper, card, intent)
        if anchor and anchor.score >= 3.0:
            candidates.append(anchor)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.score, reverse=True)[0]


def is_real_paper_anchor(paper: dict[str, Any], card: dict[str, Any]) -> bool:
    paper_id = normalize_space(card.get("paper_id", ""))
    if not paper_id or paper.get("id") != paper_id:
        return False
    source = normalize_space(paper.get("source", "")).lower()
    venue = normalize_space(paper.get("venue", "")).lower()
    code = normalize_space(paper.get("code", "")).lower()
    title = normalize_space(paper.get("title", "")).lower()
    if source in {"", "seed"} or venue == "demo" or code == "demo" or title.startswith("synthetic example:"):
        return False
    if not normalize_space(paper.get("url", "")):
        return False
    if not card_has_verified_full_text(card):
        return False
    return True


def merge_card_paper(card: dict[str, Any], paper: dict[str, Any]) -> dict[str, Any]:
    merged = dict(paper)
    field_map = {
        "paper_title": "title",
        "paper_authors": "authors",
        "paper_abstract": "abstract",
        "paper_year": "year",
        "paper_type": "type",
        "paper_venue": "venue",
        "paper_source": "source",
        "paper_url": "url",
        "paper_relation": "relation",
        "paper_priority": "priority",
        "paper_code": "code",
        "paper_relevance_score": "relevance_score",
        "paper_relevance_quality": "relevance_quality",
        "paper_matched_terms_json": "matched_terms_json",
        "paper_review_required": "review_required",
    }
    for card_key, paper_key in field_map.items():
        value = card.get(card_key)
        if value not in (None, ""):
            merged[paper_key] = value
    if card.get("paper_id") and not merged.get("id"):
        merged["id"] = card["paper_id"]
    return merged


def build_experiment_anchor_candidate(
    paper: dict[str, Any],
    card: dict[str, Any],
    intent: DecisionIntent | None = None,
) -> ExperimentAnchor | None:
    title = normalize_space(paper.get("title") or card.get("paper_title") or card.get("id") or "Untitled paper")
    minimal = str(card.get("minimal_reproduction", "") or "").strip()
    verified_fields = verified_experiment_signal_values(card)
    if verified_fields is None:
        return None
    claim = verified_fields["claim"]
    dataset = verified_fields["dataset"]
    metrics = split_signal_values(verified_fields["metric"])
    baseline = verified_fields["baseline"]
    combined = normalize_space(
        " ".join(
            [
                title,
                paper.get("type", ""),
                claim,
                dataset,
                verified_fields["metric"],
                baseline,
                card.get("sections_json", ""),
                minimal,
            ],
        ),
    )
    score = 0.0
    reasons: list[str] = []
    goal_alignment = score_anchor_goal_alignment(combined, intent)
    if goal_alignment["excluded_matches"]:
        return None

    if claim:
        score += 1.4
        reasons.append("包含可测试 claim")
    if dataset:
        score += 1.4
        reasons.append("包含 dataset/subset")
    if metrics:
        score += 1.4
        reasons.append("包含 metric")
    if baseline:
        score += 0.8
        reasons.append("包含 baseline")
    if has_benchmark_signal(combined):
        score += 0.6
        reasons.append("包含 benchmark 信号")
    if has_method_signal(combined):
        score += 0.4
        reasons.append("包含 method 信号")
    if normalize_space(paper.get("priority", "")).lower() == "high":
        score += 0.2
        reasons.append("High priority paper")
    score += float(goal_alignment["score"]) / 100 * 2.4
    if goal_alignment["matched_required_terms"]:
        reasons.append(f"目标匹配：{', '.join(goal_alignment['matched_required_terms'])}")

    return ExperimentAnchor(
        paper_title=title,
        paper_id=paper.get("id", "") or card.get("paper_id", "") or "",
        card=card,
        paper=paper,
        claim=claim,
        dataset=dataset,
        baseline=baseline,
        metrics=metrics,
        minimal_reproduction=minimal,
        reason="；".join(reasons),
        score=score,
        goal_alignment=goal_alignment,
    )


def verified_experiment_signal_values(card: dict[str, Any]) -> dict[str, str] | None:
    if not card_has_verified_full_text(card):
        return None
    signals = card.get("signals") if isinstance(card.get("signals"), dict) else {}
    evidence_map = (
        signals.get("signal_evidence")
        if isinstance(signals.get("signal_evidence"), dict)
        else {}
    )
    output: dict[str, str] = {}
    for field_name in ["claim", "dataset", "metric", "baseline"]:
        evidence = evidence_map.get(field_name)
        values = verified_experiment_evidence_values(evidence)
        if values is None:
            return None
        value = ", ".join(values)
        if not value:
            return None
        output[field_name] = value
    return output


def verified_experiment_evidence_values(evidence: object) -> list[str] | None:
    if not isinstance(evidence, dict):
        return None
    validation_errors = evidence.get("validation_errors")
    if isinstance(validation_errors, list) and validation_errors:
        return None
    availability = normalize_space(evidence.get("availability", "")).lower()
    if availability and availability != "verified":
        return None

    refs_value = evidence.get("evidence_refs")
    if isinstance(refs_value, list) and refs_value:
        if not all(isinstance(ref, dict) for ref in refs_value):
            return None
        values: list[str] = []
        for ref in refs_value:
            if (
                normalize_space(ref.get("source", "")) != "pdf.full_text"
                or ref.get("validation_errors")
            ):
                return None
            value = clean_signal_value(ref.get("canonical_value", ""))
            if not value:
                return None
            values.append(value)
        return unique_preserve_order(values)

    if normalize_space(evidence.get("source", "")) != "pdf.full_text":
        return None
    value = clean_signal_value(evidence.get("canonical_value", ""))
    return [value] if value else None


def split_signal_values(value: str) -> list[str]:
    return unique_preserve_order(
        [
            normalize_space(item)
            for item in re.split(r"[,;，；]", value)
            if normalize_space(item)
        ],
    )


def build_unblock_suggestions(
    papers: list[dict[str, Any]],
    paper_cards: list[dict[str, Any]],
    intent: DecisionIntent | None = None,
) -> list[str]:
    suggestions: list[str] = []
    if intent and intent.required_terms:
        suggestions.append(
            f"候选匹配术语：{', '.join(intent.required_terms)}。"
            "显式 all_of 约束须逐项满足，any_of 约束须命中组内至少一项；"
            "当前候选未形成满足约束的全文级实验锚点。"
        )
    if intent and intent.excluded_terms:
        suggestions.append(f"排除约束：实验锚点不得依赖 {', '.join(intent.excluded_terms)}。")
    if not papers:
        suggestions.append("先运行 Literature Search，补充至少 2 篇非 survey/review 的独立候选论文。")
    if not paper_cards:
        suggestions.append("先为 1-3 篇 method/benchmark paper 生成 Paper Card，再抽取 claim、dataset、metric、baseline。")
        suggestions.append("缺 dataset：补充 `Dataset: ...` 或 `Minimal dataset/subset: ...`，至少给出可抽样的 benchmark/subset。")
        suggestions.append("缺 baseline：补充 `Baseline: ...`，至少包含一个公开强 baseline 和一个 simple/no-op baseline。")
        suggestions.append("缺 metric：补充 `Metric: ...`，至少包含论文主指标和一个 failure/counterexample 指标。")
        return suggestions

    paper_by_id = {paper.get("id", ""): paper for paper in papers if paper.get("id")}
    bound_cards = [
        card
        for card in paper_cards
        if card.get("paper_id") and paper_by_id.get(card.get("paper_id", "") or "", {})
    ]
    if not bound_cards:
        suggestions.append("当前 Paper Card 没有绑定真实检索论文；请先从 Paper Table 选择 arXiv/OpenAlex 论文生成 Paper Card。")
        suggestions.append("手工粘贴 title/abstract 可用于阅读草稿，但不会作为 ready 实验计划的 anchor。")
        return suggestions

    linked_real_cards = [
        card
        for card in bound_cards
        if is_real_paper_anchor(paper_by_id.get(card.get("paper_id", "") or "", {}), card)
    ]
    if not linked_real_cards:
        titles = unique_preserve_order(
            [
                normalize_space(card.get("paper_title", ""))
                or normalize_space(paper_by_id.get(card.get("paper_id", "") or "", {}).get("title", ""))
                for card in bound_cards
            ],
        )
        suggestions.append(
            f"缺全文证据：{'; '.join(titles[:3]) or '当前绑定论文'} 仍是 metadata/abstract-only。"
            "请上传或解析 PDF，再从全文抽取 claim、dataset、metric、baseline。"
        )
        return suggestions

    usable_cards = [
        (merge_card_paper(card, paper_by_id.get(card.get("paper_id", "") or "", {})), card)
        for card in linked_real_cards
    ]
    usable_cards = [(paper, card) for paper, card in usable_cards if not is_survey_like(paper, card)]
    if not usable_cards:
        suggestions.append("当前 Paper Card 全部像 survey/review/overview；请补充一篇明确提出方法或 benchmark 的论文。")
        return suggestions

    missing_by_field: dict[str, list[str]] = {"claim": [], "dataset": [], "baseline": [], "metric": []}
    for paper, card in usable_cards:
        paper_title = normalize_space(paper.get("title", "")) or "未命名论文"
        values = verified_experiment_signal_values(card)
        if values is None:
            signals = card.get("signals") if isinstance(card.get("signals"), dict) else {}
            evidence_map = (
                signals.get("signal_evidence")
                if isinstance(signals.get("signal_evidence"), dict)
                else {}
            )
            for field_name in missing_by_field:
                evidence = evidence_map.get(field_name)
                if verified_experiment_evidence_values(evidence) is None:
                    missing_by_field[field_name].append(paper_title)

    field_hints = {
        "claim": "从 PDF introduction/results 中定位可测试主张，并写入字段级 evidence_ref。",
        "dataset": "从 PDF experiment setup 中定位 dataset/subset，并为每个实体绑定 evidence_ref。",
        "baseline": "从 PDF comparison 段定位公开 baseline，并为每个实体绑定 evidence_ref。",
        "metric": "从 PDF evaluation 段定位论文主指标，并为每个实体绑定 evidence_ref。",
    }
    for field, titles in missing_by_field.items():
        if titles:
            suggestions.append(f"缺 {field}：来自 {'；'.join(unique_preserve_order(titles)[:3])}。{field_hints[field]}")
    if not suggestions:
        suggestions.append("字段存在但仍未形成 anchor：请检查四个字段是否都来自 PDF 全文且没有 validation error。")
    return suggestions


def build_experiment_plan_from_anchor(
    anchor: ExperimentAnchor | None,
    focus: str,
    unblock_suggestions: list[str] | None = None,
    intent: DecisionIntent | None = None,
) -> ExperimentPlan:
    if anchor is None:
        suggestions = unblock_suggestions or [
            "补充一篇非 survey/review 的方法或 benchmark 论文。",
            "在 Paper Card 中显式写出 claim、dataset、metric 和 baseline。",
        ]
        return ExperimentPlan(
            status="blocked",
            anchor_paper_id="",
            anchor_paper_title="",
            claim="缺少可复现 anchor",
            dataset="",
            baseline="",
            metrics=["anchor availability", "claim/dataset/metric/baseline completeness", "paper type is not survey/review"],
            ablations=[
                "补充 PDF 后重新抽取 claim、dataset、metric。",
                "排除 title/type 含 survey、review、overview 的论文。",
                "优先选择 benchmark 或 method paper，而不是综述。",
            ],
            resources="需要先补充至少一篇非 survey/review 的方法或 benchmark 论文，且 claim、dataset、metric、baseline 四个字段都具有 PDF 全文证据锚点。",
            timeline=[
                "Blocked: 需要先补充一篇非 survey/review 的方法或 benchmark 论文。",
                *[f"Unblock: {suggestion}" for suggestion in suggestions],
            ],
            success_criterion="找到一篇可实验论文，其 Paper Card 的 claim、dataset、metric、baseline 均通过 PDF 全文字段级证据校验。",
            failure_criterion="继续只能命中 survey/review/overview，或 Paper Card 明确写着需要补充 PDF/实验细节。",
            unblock_suggestions=suggestions,
            goal_alignment=blocked_goal_alignment(intent),
            readiness_checks={
                "anchor": "blocked: 缺少四个核心字段均通过 PDF 全文校验的 anchor",
                "dataset": "unknown: 尚无可信 anchor",
                "baseline": "unknown: 尚无可信 anchor",
                "metric": "unknown: 尚无可信 anchor",
                "code_or_api": "unknown: 尚无可信 anchor",
                "model_version": "unknown: 尚无可信 anchor",
                "sample_size": "unknown: 尚无可信 anchor",
                "seed": "unknown: 尚无可信 anchor",
                "run_protocol": "unknown: 尚无可信 anchor",
                "compute": "unknown: 尚无可信 anchor",
                "resource_budget": "unknown: 尚无可信 anchor",
                "annotation": "unknown: 尚无可信 anchor",
                "success_threshold": "unknown: 尚无可信 anchor",
                "stopping_threshold": "unknown: 尚无可信 anchor",
            },
            assumptions=[],
        )

    readiness_checks, assumptions = build_readiness_checks(anchor)
    if anchor.goal_alignment.get("status") == "mismatch":
        missing_constraints = [
            normalize_space(item)
            for item in [
                *anchor.goal_alignment.get("missing_hard_constraints", []),
                *anchor.goal_alignment.get("missing_required_terms", []),
            ]
            if normalize_space(item)
        ]
        missing_constraints = unique_preserve_order(missing_constraints)
        missing_label = "、".join(missing_constraints) or "未解析的目标硬约束"
        readiness_checks["goal_constraints"] = f"blocked: 缺少 {missing_label}"
        suggestions = [
            f"补齐目标硬约束：{missing_label}。",
            "如果约束来自用户资源上限，请补充模型版本、精度、batch size、显存估算和实测峰值。",
            "如果约束来自研究问题，请在 claim、dataset、metric、baseline 或 failure slice 中提供直接对应项。",
        ]
        return ExperimentPlan(
            status="blocked",
            anchor_paper_id=anchor.paper_id,
            anchor_paper_title=anchor.paper_title,
            claim=f"候选 anchor 尚未满足目标约束：{anchor.claim}",
            dataset=anchor.dataset,
            baseline=anchor.baseline,
            metrics=anchor.metrics,
            ablations=[],
            resources="候选论文具备基础实验字段，但用户显式硬约束尚未全部满足，不能视为可执行计划。",
            timeline=[f"Blocked: {suggestion}" for suggestion in suggestions],
            success_criterion="所有显式硬约束均有可验证的计划字段或资源证据后，才可进入 ready。",
            failure_criterion="任一硬约束缺失、仅靠关键词推断，或资源可行性未经估算。",
            unblock_suggestions=suggestions,
            goal_alignment=anchor.goal_alignment,
            readiness_checks=readiness_checks,
            assumptions=unique_preserve_order([*assumptions, *missing_constraints]),
        )
    execution_unknowns = [
        f"{key}: {value.removeprefix('unknown: ').removeprefix('blocked: ')}"
        for key, value in readiness_checks.items()
        if value.startswith(("unknown:", "blocked:"))
    ]
    plan_status = "partial" if execution_unknowns else "ready"
    partial_suggestions = [
        f"补齐执行条件 `{item}`。"
        for item in execution_unknowns
    ]
    timeline = build_intent_timeline(anchor, intent)
    budget_label = (
        f"{intent.time_budget_days} 天"
        if intent and intent.time_budget_days
        else "未指定周期"
    )
    return ExperimentPlan(
        status=plan_status,
        anchor_paper_id=anchor.paper_id,
        anchor_paper_title=anchor.paper_title,
        claim=f"Anchor paper: `{anchor.paper_title}`。待验证 claim：{anchor.claim}",
        dataset=anchor.dataset,
        baseline=anchor.baseline,
        metrics=unique_preserve_order([*anchor.metrics, "counterexample pass rate", "failure-mode frequency by slice"]),
        ablations=[
            "移除或遮挡 claim 依赖的关键输入证据，观察指标是否显著变化。",
            "替换属性词、物体上下文或选项顺序，检查 benchmark shortcut。",
            "按样本难度、问题类型和失败模式分层分析。",
        ],
        resources=(
            f"Anchor reason: {anchor.reason}。目标周期：{budget_label}。"
            + (
                "执行条件已经由 Paper Card 中的显式协议字段确认。"
                if plan_status == "ready"
                else "科研锚点完整，但样本量、算力、模型/API、seed 或阈值仍有未知项。"
            )
        ),
        timeline=timeline,
        success_criterion=(
            extract_execution_detail(anchor, ["Success threshold", "Success criterion", "成功阈值"])
            or f"在 `{anchor.paper_title}` 的预注册设置下达到明确成功阈值，并定位至少一个稳定失败模式。"
        ),
        failure_criterion=(
            extract_execution_detail(anchor, ["Stop threshold", "Stopping criterion", "停止阈值", "Failure threshold"])
            or "未达到预注册阈值或结果只来自个别样本时停止，不把不稳定现象解释为支持 anchor claim。"
        ),
        unblock_suggestions=partial_suggestions,
        goal_alignment=anchor.goal_alignment,
        readiness_checks=readiness_checks,
        assumptions=assumptions,
    )


def is_survey_like(paper: dict[str, Any], card: dict[str, Any]) -> bool:
    title = normalize_space(paper.get("title", "")).lower()
    paper_type = normalize_space(paper.get("type", "")).lower()
    minimal = normalize_space(card.get("minimal_reproduction", "")).lower()

    hard_markers = ["survey", "review", "overview", "taxonomy", "position paper", "综述", "调研", "文献图谱"]
    if any(marker in title for marker in hard_markers):
        return True
    if any(marker in paper_type for marker in hard_markers):
        return True
    if "不应作为一周复现实验 anchor" in minimal or "survey/review" in minimal:
        return True
    return False


def is_invalid_minimal_reproduction(value: str) -> bool:
    lower = value.lower()
    invalid_markers = [
        "status: blocked",
        "需要补充 pdf",
        "缺少 claim",
        "缺少可复现 anchor",
        "不应作为一周复现实验 anchor",
        "不适合按方法论文写",
        "survey/review",
        "not suitable",
        "insufficient evidence",
    ]
    return any(marker in lower for marker in invalid_markers)


def extract_anchor_claim(minimal: str, combined: str) -> str:
    line = extract_labeled_value(minimal, ["Claim to test", "Claim", "claim"])
    if line:
        return line
    match = re.search(r"(we show|we demonstrate|we find|核心 claim 证据：)([^。.!?\n]{12,220})", combined, flags=re.IGNORECASE)
    if match:
        return normalize_space(match.group(0))[:260]
    return ""


def extract_anchor_dataset(minimal: str, combined: str) -> str:
    line = extract_labeled_value(minimal, ["Minimal dataset/subset", "Dataset", "dataset"])
    if line:
        return line
    named = find_named_terms(
        combined,
        [
            "HallusionBench",
            "MMBench",
            "MMMU",
            "POPE",
            "CHAIR",
            "MM-Vet",
            "LLaVA-Bench",
            "SEED-Bench",
            "RealWorldQA",
            "ScienceQA",
            "MathVista",
            "ChartQA",
            "DocVQA",
            "TextVQA",
            "VQA v2",
            "OK-VQA",
            "GQA",
            "COCO",
            "ImageNet",
            "Set5",
            "Set14",
            "Urban100",
            "DIV2K",
        ],
    )
    if named:
        return ", ".join(named)
    if re.search(r"\b\d{2,4}\s*-\s*\d{2,4}\b.*?(samples|样本)", combined, flags=re.IGNORECASE):
        return "论文建议的小规模样本子集"
    return ""


def extract_anchor_metrics(minimal: str, combined: str) -> list[str]:
    metric_line = extract_labeled_value(minimal, ["Metric", "Metrics", "metric", "指标"])
    source = metric_line or combined
    candidates = find_named_terms(
        source,
        [
            "answer accuracy",
            "accuracy",
            "evidence consistency",
            "counterexample pass rate",
            "failure-mode frequency",
            "hallucination rate",
            "grounding accuracy",
            "faithfulness",
            "CHAIR score",
            "CHAIRs",
            "CHAIRi",
            "precision",
            "recall",
            "F1",
            "AUC",
            "mAP",
            "IoU",
            "PSNR",
            "SSIM",
            "LPIPS",
            "FID",
            "BLEU",
            "ROUGE",
            "CIDEr",
        ],
    )
    return unique_preserve_order(candidates)


def extract_anchor_baseline(minimal: str, combined: str) -> str:
    line = extract_labeled_value(minimal, ["Baseline", "baseline"])
    if line and not is_bad_baseline_line(line):
        return line

    names = find_named_terms(combined, KNOWN_BASELINES)
    if names:
        return ", ".join(names[:4])

    return ""


def is_bad_baseline_line(value: str) -> bool:
    lower = normalize_space(value).lower()
    if find_named_terms(value, KNOWN_BASELINES):
        return False
    bad_patterns = [
        "baseline 来验证",
        "baseline to validate",
        "baseline 来复核",
        "baseline 验证",
        "验证核心 claim",
        "validate core claim",
        "compare with baseline",
        "对比 baseline",
    ]
    if any(pattern in lower for pattern in bad_patterns):
        return True
    generic_terms = ["baseline", "strong baseline", "simple baseline", "公开强 baseline", "轻量 baseline"]
    return lower in generic_terms


def extract_labeled_value(text: str, labels: list[str]) -> str:
    for line in re.split(r"[\n\r]+", text):
        normalized = normalize_space(line)
        for label in labels:
            pattern = rf"^{re.escape(label)}\s*[:：]\s*(.+)$"
            match = re.match(pattern, normalized, flags=re.IGNORECASE)
            if match:
                return normalize_space(match.group(1))[:260]
    return ""


def find_named_terms(text: str, names: list[str]) -> list[str]:
    found: list[str] = []
    for name in names:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(name)
    return unique_preserve_order(found)


def has_benchmark_signal(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in ["benchmark", "dataset", "evaluation", "metric", "评测", "数据集", "指标"])


def has_method_signal(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in ["method", "model", "architecture", "framework", "training", "方法", "模型", "架构"])


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_space(value)
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_decision_intent(goal: str, focus: str) -> DecisionIntent:
    raw_goal = normalize_space(goal)
    contrast_terms = extract_goal_clause_terms(
        raw_goal,
        [
            r"(?:different from|different than|contrast with|versus|vs\.?)\s+"
            r"([A-Za-z][A-Za-z0-9._-]*(?:\s+[A-Z0-9][A-Za-z0-9._-]*){0,3})",
            r"(?:区别于|不同于|对比|相比)\s*([A-Za-z][A-Za-z0-9._-]*(?:\s+[A-Za-z0-9._-]+){0,3})",
        ],
    )
    excluded_terms = extract_goal_clause_terms(
        raw_goal,
        [
            r"(?:do not use|don't use|without|avoid|exclude)\s+"
            r"([A-Za-z][A-Za-z0-9._-]*(?:\s+[A-Z0-9][A-Za-z0-9._-]*){0,3})",
            r"(?:不使用|不要(?:使用|采用|依赖)?|排除|避免)\s*([A-Za-z][A-Za-z0-9._-]*(?:\s+[A-Za-z0-9._-]+){0,3})",
        ],
    )
    known_phrases = [
        phrase
        for phrase in [
            "object hallucination",
            "evidence faithfulness",
            "visual grounding",
            "counterexample evaluation",
            "multiple objects",
            "multi-object",
            "物体幻觉",
            "对象幻觉",
            "多物体",
            "证据忠实性",
            "视觉定位",
            "反例评测",
            "数据集",
            "指标",
            "baseline",
            "失败判据",
        ]
        if phrase.lower() in raw_goal.lower()
    ]
    excluded_keys = {term.lower() for term in [*contrast_terms, *excluded_terms]}
    required_terms = unique_preserve_order(
        [
            *known_phrases,
            *[
                term
                for term in extract_terms(raw_goal, limit=18)
                if is_goal_constraint_term(term)
                and term.lower() not in excluded_keys
                and term.lower() not in {"different", "contrast", "versus", "without", "avoid", "exclude"}
            ],
        ],
    )
    return DecisionIntent(
        raw_goal=raw_goal,
        focus=focus,
        required_terms=required_terms[:8],
        contrast_terms=contrast_terms[:5],
        excluded_terms=excluded_terms[:5],
        contribution_type=infer_goal_contribution_type(raw_goal),
        time_budget_days=infer_time_budget_days(raw_goal),
    )


def extract_goal_clause_terms(goal: str, patterns: list[str]) -> list[str]:
    values: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, goal, flags=re.IGNORECASE):
            clause = normalize_space(match.group(1))
            clause = re.sub(
                r"^(?:use|using|adopt|depend on|使用|采用|依赖)\s+",
                "",
                clause,
                flags=re.IGNORECASE,
            )
            values.extend(
                term
                for term in extract_terms(clause, limit=5, include_domain_phrases=True)
                if is_goal_constraint_term(term)
            )
            values.extend(re.findall(r"\b[A-Z][A-Za-z0-9._-]{2,}\b", clause))
    return unique_preserve_order(values)


def is_goal_constraint_term(term: str) -> bool:
    normalized = normalize_space(term)
    lower = normalized.lower()
    if not normalized or lower in GOAL_GENERIC_TERMS or lower.isdigit():
        return False
    if re.fullmatch(r"[\u4e00-\u9fff]+", normalized):
        if len(normalized) > 8 or any(marker in normalized for marker in GOAL_ACTION_MARKERS):
            return False
    return True


def infer_goal_contribution_type(goal: str) -> str:
    lower = goal.lower()
    if any(term in lower for term in ["failure analysis", "failure mode", "反例", "失败模式", "错误分析"]):
        return "failure_analysis"
    if any(term in lower for term in ["benchmark", "evaluation", "evaluate", "评测", "评价", "评估"]):
        return "evaluation"
    if any(term in lower for term in ["dataset", "data set", "数据集"]):
        return "dataset"
    if any(term in lower for term in ["method", "architecture", "training", "方法", "架构", "训练"]):
        return "method"
    return "unspecified"


def infer_time_budget_days(goal: str) -> int | None:
    lower = goal.lower()
    numeric_day = re.search(r"\b(\d{1,3})\s*(?:day|days)\b", lower)
    if numeric_day:
        return int(numeric_day.group(1))
    numeric_week = re.search(r"\b(\d{1,2})\s*(?:week|weeks)\b", lower)
    if numeric_week:
        return int(numeric_week.group(1)) * 7
    numeric_month = re.search(r"\b(\d{1,2})\s*(?:month|months)\b", lower)
    if numeric_month:
        return int(numeric_month.group(1)) * 30
    chinese_day = re.search(r"(\d{1,3})\s*天", goal)
    if chinese_day:
        return int(chinese_day.group(1))
    chinese_week = re.search(r"(\d{1,2})\s*(?:周|星期)", goal)
    if chinese_week:
        return int(chinese_week.group(1)) * 7
    chinese_month = re.search(r"(\d{1,2})\s*个?月", goal)
    if chinese_month:
        return int(chinese_month.group(1)) * 30
    if any(term in lower for term in ["one-week", "one week", "一周"]):
        return 7
    if any(term in lower for term in ["one-month", "one month", "一个月"]):
        return 30
    return None


def score_anchor_goal_alignment(combined: str, intent: DecisionIntent | None) -> dict[str, Any]:
    if intent is None:
        return {
            "status": "not_specified",
            "score": 0.0,
            "matched_required_terms": [],
            "missing_required_terms": [],
            "required_term_coverage": 1.0,
            "minimum_required_term_coverage": 0.0,
            "contrast_terms": [],
            "excluded_matches": [],
            "constraint_groups": [],
        }
    matched = [
        term
        for term in intent.required_terms
        if goal_term_present(combined.lower(), term)
    ]
    excluded_matches = score_term_overlap(
        combined,
        set(intent.excluded_terms),
        weight=0.1,
        max_score=1.0,
    ).matched_terms
    matched_keys = {term.lower() for term in matched}
    missing = [term for term in intent.required_terms if term.lower() not in matched_keys]
    required_term_coverage = (
        len(matched) / len(intent.required_terms)
        if intent.required_terms
        else 1.0
    )
    minimum_required_term_coverage = (
        0.0
        if not intent.required_terms
        else 1.0
        if len(intent.required_terms) == 1
        else 0.5
        if len(intent.required_terms) == 2
        else 0.6
    )
    hard_constraint_checks = evaluate_explicit_goal_constraints(combined, intent.raw_goal)
    constraint_groups = build_constraint_groups(combined, intent.raw_goal)
    matched_hard_constraints = [
        label for label, is_satisfied in hard_constraint_checks if is_satisfied
    ]
    missing_hard_constraints = [
        label for label, is_satisfied in hard_constraint_checks if not is_satisfied
    ]
    status = (
        "aligned"
        if not missing_hard_constraints
        and required_term_coverage >= minimum_required_term_coverage
        else "mismatch"
    )
    hard_constraint_coverage = (
        len(matched_hard_constraints) / len(hard_constraint_checks)
        if hard_constraint_checks
        else 1.0
    )
    alignment_score = round(
        100
        * (
            0.70 * required_term_coverage
            + 0.30 * hard_constraint_coverage
        ),
        1,
    )
    return {
        "status": "excluded" if excluded_matches else status,
        "score": alignment_score,
        "matched_required_terms": matched,
        "missing_required_terms": missing,
        "required_term_coverage": round(required_term_coverage, 4),
        "minimum_required_term_coverage": minimum_required_term_coverage,
        "matched_hard_constraints": matched_hard_constraints,
        "missing_hard_constraints": missing_hard_constraints,
        "hard_constraint_checks": {
            label: "ready" if is_satisfied else "blocked"
            for label, is_satisfied in hard_constraint_checks
        },
        "contrast_terms": intent.contrast_terms,
        "excluded_matches": excluded_matches,
        "constraint_groups": constraint_groups,
    }


def build_constraint_groups(combined: str, raw_goal: str) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    clauses = [
        ("required", extract_required_clause(raw_goal)),
        ("preferred", extract_preferred_clause(raw_goal)),
    ]
    for mode, clause in clauses:
        if not clause:
            continue
        values = [
            name
            for name in KNOWN_EXPERIMENT_DATASETS
            if goal_term_present(clause.lower(), name)
        ]
        if not values:
            continue
        operator = (
            "any_of"
            if len(values) > 1 and re.search(r"\b(?:or|either)\b|或", clause, flags=re.IGNORECASE)
            else "all_of"
        )
        matched_values = [
            value
            for value in values
            if goal_term_present(combined.lower(), value)
        ]
        satisfied = bool(matched_values) if operator == "any_of" else len(matched_values) == len(values)
        groups.append(
            {
                "mode": mode,
                "operator": operator,
                "values": values,
                "matched_values": matched_values,
                "status": "ready" if satisfied else "blocked" if mode == "required" else "preferred_missing",
            },
        )
    return groups


def evaluate_explicit_goal_constraints(combined: str, raw_goal: str) -> list[tuple[str, bool]]:
    goal = normalize_space(raw_goal)
    lower_goal = goal.lower()
    lower_combined = combined.lower()
    has_action_constraint = bool(
        re.search(r"\b(?:reproduce|replicate|compare)\b|复现|比较|对比", lower_goal)
    )
    if (
        not any(marker in lower_goal for marker in GOAL_REQUIRED_MARKERS)
        and not re.search(r"\b\d{1,3}\s*gb\b", lower_goal)
        and not has_action_constraint
    ):
        return []

    checks: list[tuple[str, bool]] = []

    def add_check(label: str, satisfied: bool) -> None:
        key = label.casefold()
        if any(existing.casefold() == key for existing, _ in checks):
            return
        checks.append((label, satisfied))

    memory_match = re.search(r"\b(\d{1,3})\s*gb\b", lower_goal)
    if memory_match:
        memory_label = f"{memory_match.group(1)}GB"
        add_check(memory_label, bool(re.search(rf"\b{memory_match.group(1)}\s*gb\b", lower_combined)))
    if re.search(r"(?:single|one)\s+(?:[a-z0-9-]+\s+){0,2}gpu|单张\s*\d*\s*(?:gb)?\s*gpu|单卡", lower_goal):
        add_check(
            "single GPU",
            bool(
                re.search(
                    r"(?:single|one)\s+(?:[a-z0-9-]+\s+){0,2}gpu|单张\s*\d*\s*(?:gb)?\s*gpu|单卡",
                    lower_combined,
                )
            ),
        )

    for first, second in extract_comparison_pairs(goal):
        add_check(first, goal_term_present(lower_combined, first))
        add_check(second, goal_term_present(lower_combined, second))
    for target in extract_reproduction_targets(goal):
        add_check(target, goal_term_present(lower_combined, target))
    for target in extract_comparison_terms(goal):
        add_check(target, goal_term_present(lower_combined, target))

    required_clause = extract_required_clause(goal)
    clause_lower = required_clause.lower()
    if required_clause:
        named_datasets = [
            name for name in KNOWN_EXPERIMENT_DATASETS if goal_term_present(clause_lower, name)
        ]
        if len(named_datasets) > 1 and re.search(r"\b(?:or|either)\b|或", clause_lower):
            add_check(
                " / ".join(named_datasets),
                any(goal_term_present(lower_combined, name) for name in named_datasets),
            )
        else:
            for name in named_datasets:
                add_check(name, goal_term_present(lower_combined, name))

        if "数据集" in required_clause or re.search(r"\bdataset\b", clause_lower):
            add_check(
                "dataset",
                "dataset:" in lower_combined
                or "数据集" in combined
                or any(goal_term_present(lower_combined, name) for name in KNOWN_EXPERIMENT_DATASETS),
            )
        if "baseline" in clause_lower:
            has_named_baseline = bool(find_named_terms(combined, KNOWN_BASELINES))
            if "强 baseline" in required_clause or "strong baseline" in clause_lower:
                add_check("strong baseline", has_named_baseline or "strong baseline" in lower_combined)
            else:
                add_check("baseline", has_named_baseline or "baseline:" in lower_combined)
        if "失败样本" in required_clause or "failure slice" in clause_lower or "failure-case" in clause_lower:
            add_check(
                "failure sample slices",
                any(
                    marker in lower_combined
                    for marker in ["失败样本", "failure slice", "failure-case", "failure case", "failure-mode"]
                ),
            )
        if "证据忠实性" in required_clause or "evidence faithfulness" in clause_lower:
            add_check(
                "evidence faithfulness metric",
                (
                    "证据忠实性" in combined
                    or "evidence faithfulness" in lower_combined
                    or "evidence consistency" in lower_combined
                )
                and any(marker in lower_combined for marker in ["metric", "指标", "score", "rate", "accuracy"]),
            )
        elif "指标" in required_clause or re.search(r"\bmetrics?\b", clause_lower):
            add_check(
                "metric",
                "metric:" in lower_combined
                or "指标" in combined
                or bool(extract_anchor_metrics("", combined)),
            )
    if not required_clause:
        for name in KNOWN_EXPERIMENT_DATASETS:
            if goal_term_present(lower_goal, name):
                add_check(name, goal_term_present(lower_combined, name))
    return checks


def extract_comparison_pairs(goal: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    patterns = [
        r"(?:compare|comparison of|contrast)\s+([A-Za-z0-9][A-Za-z0-9._-]*)"
        r"(?:\s+(?:hypothesis|mechanism))?\s+(?:and|with|versus|vs\.?)\s+"
        r"([A-Za-z0-9][A-Za-z0-9._-]*)",
        r"(?:比较|对比)\s*([A-Za-z0-9][A-Za-z0-9._-]*)"
        r"(?:\s*根因假设)?\s*(?:与|和|及|vs\.?)\s*"
        r"([A-Za-z0-9][A-Za-z0-9._-]*)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, goal, flags=re.IGNORECASE):
            pairs.append((normalize_space(match.group(1)), normalize_space(match.group(2))))
    return pairs


def extract_reproduction_targets(goal: str) -> list[str]:
    targets: list[str] = []
    patterns = [
        r"\b(?:reproduce|replicate)\s+([^,;。；]{2,100}?)(?=\s+(?:on|using|with)\b|[,;。；]|$)",
        r"复现\s*([^，,；;。]{2,100}?)(?=\s*(?:在|使用|采用)|[，,；;。]|$)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, goal, flags=re.IGNORECASE):
            target = normalize_space(match.group(1)).strip("`'\"")
            if target:
                targets.append(target)
    return unique_preserve_order(targets)


def extract_comparison_terms(goal: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(
        r"(?:compare|comparison|比较|对比)\s*([^；;。]{2,180})",
        goal,
        flags=re.IGNORECASE,
    ):
        clause = normalize_space(match.group(1))
        values.extend(re.findall(r"\b[A-Z][A-Z0-9._-]{1,}\b", clause))
        values.extend(
            token
            for token in re.findall(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)+\b", clause.lower())
            if token not in {"one-week", "single-gpu"}
        )
    return unique_preserve_order(values)


def extract_required_clause(goal: str) -> str:
    match = re.search(
        r"(?:must\s+(?:include|contain)|required?\s*:|include\s+|必须包含|需包含|需要包含|至少包含)"
        r"([^；;。]{1,240})",
        goal,
        flags=re.IGNORECASE,
    )
    return normalize_space(match.group(1)) if match else ""


def extract_preferred_clause(goal: str) -> str:
    match = re.search(
        r"(?:prefer(?:red)?|prioriti[sz]e|优先(?:使用|采用|包含)?)\s*[:：]?\s*"
        r"([^；;。]{1,240})",
        goal,
        flags=re.IGNORECASE,
    )
    return normalize_space(match.group(1)) if match else ""


def goal_term_present(text: str, term: str) -> bool:
    normalized_term = normalize_space(term).lower()
    if not normalized_term:
        return False
    alias_groups = {
        "数据集": ["dataset", "benchmark"],
        "指标": ["metric", "accuracy", "rate", "score"],
        "证据忠实性": ["evidence faithfulness", "evidence consistency", "faithfulness"],
        "失败判据": ["failure criterion", "failure criteria", "failure condition"],
        "强 baseline": ["strong baseline", *[name.lower() for name in KNOWN_BASELINES]],
    }
    aliases = alias_groups.get(normalized_term, [normalized_term])
    if any(
        goal_term_present(text, alias)
        for alias in aliases
        if alias != normalized_term
    ):
        return True
    if re.search(r"[\u4e00-\u9fff]", normalized_term):
        return normalized_term in text
    pattern = r"(?<![a-z0-9])" + r"[\s-]+".join(
        re.escape(part) for part in re.split(r"[\s-]+", normalized_term) if part
    ) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def blocked_goal_alignment(intent: DecisionIntent | None) -> dict[str, Any]:
    return {
        "status": "blocked",
        "score": 0.0,
        "matched_required_terms": [],
        "missing_required_terms": intent.required_terms if intent else [],
        "required_term_coverage": 0.0,
        "minimum_required_term_coverage": 0.6 if intent and intent.required_terms else 0.0,
        "matched_hard_constraints": [],
        "missing_hard_constraints": [],
        "hard_constraint_checks": {},
        "contrast_terms": intent.contrast_terms if intent else [],
        "excluded_matches": [],
        "constraint_groups": [],
    }


def build_readiness_checks(anchor: ExperimentAnchor) -> tuple[dict[str, str], list[str]]:
    paper = anchor.paper
    card = anchor.card
    combined = normalize_space(f"{card.get('minimal_reproduction', '')} {card.get('sections_json', '')}")
    lower = combined.lower()
    code_value = normalize_space(paper.get("code", ""))
    code_ready = bool(
        code_value
        and code_value.lower() not in {"unknown", "none", "n/a"}
        and re.match(r"https?://", code_value, flags=re.IGNORECASE)
    )
    api_provider = extract_execution_detail(anchor, ["Provider", "API provider"])
    api_model = extract_execution_detail(anchor, ["Model", "Model version"])
    api_access = extract_execution_detail(anchor, ["API access", "Access"])
    api_ready = bool(
        api_provider
        and api_model
        and re.search(r"\b(?:ready|granted|available|verified)\b|已开通|可用", api_access, flags=re.IGNORECASE)
    )
    model_version = (
        extract_execution_detail(anchor, ["Model version", "Model"])
        or next(
            (
                name
                for name in split_signal_values(anchor.baseline)
                if re.search(r"\d", name)
            ),
            "",
        )
    )
    sample_size = extract_execution_detail(anchor, ["Sample size", "Samples", "样本量"])
    seed = extract_execution_detail(anchor, ["Seed", "Random seed", "随机种子"])
    protocol = extract_execution_detail(anchor, ["Protocol", "Run protocol", "Command", "运行协议"])
    compute = extract_execution_detail(anchor, ["Compute", "Device", "Hardware", "算力", "设备"])
    if not compute:
        compute_match = re.search(
            r"\b(?:\d+\s*[x×]\s*)?(?:a100|h100|v100|rtx\s*\d{3,4}|gpu|cpu|tpu)"
            r"(?:\s+\d{1,3}\s*gb)?\b",
            combined,
            flags=re.IGNORECASE,
        )
        compute = normalize_space(compute_match.group(0)) if compute_match else ""
    resource_budget = extract_execution_detail(
        anchor,
        ["Resource budget", "Budget", "Request budget", "资源预算", "费用上限"],
    )
    success_threshold = extract_execution_detail(
        anchor,
        ["Success threshold", "Success criterion", "成功阈值"],
    )
    stopping_threshold = extract_execution_detail(
        anchor,
        ["Stop threshold", "Stopping criterion", "Failure threshold", "停止阈值"],
    )
    annotation_required = any(
        marker in lower
        for marker in ["annotat", "human evaluation", "labeling", "标注", "人工评测"]
    )
    annotation_protocol = extract_execution_detail(
        anchor,
        ["Annotation protocol", "Annotation", "标注协议"],
    )
    checks = {
        "anchor": f"ready: {anchor.paper_title}",
        "dataset": f"ready: {anchor.dataset}",
        "baseline": f"ready: {anchor.baseline}",
        "metric": f"ready: {', '.join(anchor.metrics)}",
        "code_or_api": (
            f"ready: {code_value}"
            if code_ready
            else f"ready: {api_provider} / {api_model} / access verified"
            if api_ready
            else "unknown: 未发现可验证代码仓库，或缺少 provider/model/API 权限状态"
        ),
        "model_version": f"ready: {model_version}" if model_version else "unknown: 未指定精确模型版本",
        "sample_size": f"ready: {sample_size}" if sample_size else "unknown: 未指定样本量或数据子集规模",
        "seed": f"ready: {seed}" if seed else "unknown: 未指定随机 seed",
        "run_protocol": f"ready: {protocol}" if protocol else "unknown: 未给出运行命令或冻结协议",
        "compute": f"ready: {compute}" if compute else "unknown: 未说明设备、显存或 API 配额",
        "resource_budget": (
            f"ready: {resource_budget}"
            if resource_budget
            else "unknown: 未说明运行时长、请求量或费用上限"
        ),
        "annotation": (
            f"ready: {annotation_protocol}"
            if annotation_required and annotation_protocol
            else "unknown: 实验需要人工评测，但未说明标注协议与工时"
            if annotation_required
            else "not_required: 使用既有标注与自动指标，不新增人工标注"
        ),
        "success_threshold": (
            f"ready: {success_threshold}"
            if success_threshold
            else "unknown: 未预注册数值化成功阈值"
        ),
        "stopping_threshold": (
            f"ready: {stopping_threshold}"
            if stopping_threshold
            else "unknown: 未预注册停止或失败阈值"
        ),
    }
    assumptions = [
        detail.replace("unknown: ", "")
        for detail in checks.values()
        if detail.startswith("unknown:")
    ]
    return checks, assumptions


def extract_execution_detail(anchor: ExperimentAnchor, labels: list[str]) -> str:
    source = "\n".join(
        [
            str(anchor.card.get("minimal_reproduction", "") or ""),
            str(anchor.card.get("sections_json", "") or ""),
        ],
    )
    return extract_labeled_value(source, labels)


def build_intent_timeline(anchor: ExperimentAnchor, intent: DecisionIntent | None) -> list[str]:
    budget_days = intent.time_budget_days if intent else None
    if budget_days is not None and budget_days <= 7:
        return [
            f"Day 1: 核验 `{anchor.paper_title}` 的 claim、dataset、metric、baseline 与目标约束。",
            f"Day 2-3: 在 `{anchor.dataset}` 上先跑通 `{anchor.baseline}`；样本量由可用算力和统计需求决定。",
            "Day 4-5: 构造反例与 failure slices，并记录所有协议变更。",
            "Day 6: 做最小 ablation 和稳定性检查。",
            "Day 7: 输出可复现记录、失败样本与继续/停止决策。",
        ]
    if budget_days is not None and budget_days <= 31:
        return [
            "Week 1: 核验锚点证据、代码/模型权限、数据许可与评测协议。",
            "Week 2: 复现论文基线并冻结实验配置。",
            "Week 3: 运行反例、切片和 ablation，记录不一致结果。",
            "Week 4: 复核统计稳定性，输出继续/停止决策与下一阶段计划。",
        ]
    return [
        "Phase 1: 核验锚点证据以及代码、数据、模型、算力和标注可用性。",
        "Phase 2: 先复现 baseline，再冻结数据与指标协议。",
        "Phase 3: 运行反例、failure slices 与 ablation。",
        "Phase 4: 根据预注册成功/失败标准做继续或停止决策。",
    ]


def infer_focus(project: dict[str, Any], papers: list[dict[str, Any]], paper_cards: list[dict[str, Any]], goal: str) -> str:
    text = " ".join(
        [
            project.get("title", ""),
            project.get("keyword", ""),
            project.get("field", ""),
            goal,
            " ".join(paper.get("title", "") for paper in papers[:5]),
            " ".join(card.get("weakest_assumption", "") for card in paper_cards[:3]),
        ],
    ).lower()
    if "hallucination" in text or "vlm" in text or "vision-language" in text:
        return "VLM hallucination and evidence faithfulness"
    if "agent" in text or "workflow" in text:
        return "AI research workflow agent reliability"
    if "benchmark" in text or "evaluation" in text:
        return "benchmark reliability and hidden failure modes"
    return project.get("field") or project.get("keyword") or "AI research reliability"


def render_gap_board_markdown(bundle: ResearchDecisionBundle) -> str:
    blocks = ["# Gap Board", f"Project: {bundle.project_title}"]
    if bundle.decision_intent:
        blocks.append(
            "\n".join(
                [
                    "## Decision Intent",
                    f"- Raw goal: {bundle.decision_intent.raw_goal or 'not specified'}",
                    f"- Required terms: {', '.join(bundle.decision_intent.required_terms) or 'none'}",
                    f"- Contrast terms: {', '.join(bundle.decision_intent.contrast_terms) or 'none'}",
                    f"- Excluded terms: {', '.join(bundle.decision_intent.excluded_terms) or 'none'}",
                    f"- Time budget: {bundle.decision_intent.time_budget_days or 'not specified'} days",
                ],
            ),
        )
    for gap in bundle.gaps:
        blocks.append(
            "\n".join(
                [
                    f"## {gap.title}",
                    f"- Type: {gap.kind}",
                    f"- Support: {gap.support_status}",
                    f"- Confidence: {gap.confidence}",
                    f"- Novelty risk: {gap.novelty_risk}",
                    f"- Feasibility: {gap.feasibility}",
                    f"- Evidence: {gap.evidence}",
                    f"- Weakness: {gap.weakness}",
                    f"- Opportunity: {gap.opportunity}",
                    "- Paper IDs: " + (", ".join(gap.paper_ids) if gap.paper_ids else "none"),
                    "- Evidence refs: "
                    + (
                        "; ".join(
                            f"{ref.get('paper_id', '')}/{ref.get('snippet_id', '')}/{ref.get('source', '')}"
                            for ref in gap.evidence_refs
                        )
                        if gap.evidence_refs
                        else "none"
                    ),
                    "- Validation requirements:\n"
                    + (
                        "\n".join(f"  - {item}" for item in gap.validation_requirements)
                        if gap.validation_requirements
                        else "  - none"
                    ),
                ],
            ),
        )
    return "\n\n".join(blocks)


def render_validation_markdown(bundle: ResearchDecisionBundle) -> str:
    report = bundle.validation
    return "\n\n".join(
        [
            "# Idea Validation Report",
            f"Project: {bundle.project_title}",
            f"## Idea\n{report.idea}",
            f"## Why Not Incremental\n{report.why_not_incremental}",
            f"## Difference From Existing Work\n{report.difference_from_existing_work}",
            f"## Novelty Risk\n{report.novelty_risk}",
            f"## Feasibility\n{report.feasibility}",
            "## Key Risks\n" + "\n".join(f"- {risk}" for risk in report.key_risks),
        ],
    )


def render_experiment_markdown(bundle: ResearchDecisionBundle) -> str:
    plan = bundle.experiment
    return "\n\n".join(
        [
            "# Experiment Plan",
            f"Project: {bundle.project_title}",
            f"Status: {plan.status}",
            f"Anchor: {plan.anchor_paper_title or 'N/A'}",
            f"## Claim\n{plan.claim}",
            f"## Dataset\n{plan.dataset}",
            f"## Baseline\n{plan.baseline}",
            "## Metrics\n" + "\n".join(f"- {metric}" for metric in plan.metrics),
            "## Ablations\n" + "\n".join(f"- {ablation}" for ablation in plan.ablations),
            f"## Resources\n{plan.resources}",
            "## Goal Alignment\n"
            + "\n".join(f"- {key}: {value}" for key, value in plan.goal_alignment.items()),
            "## Readiness Checks\n"
            + "\n".join(f"- {key}: {value}" for key, value in plan.readiness_checks.items()),
            "## Explicit Assumptions\n"
            + ("\n".join(f"- {item}" for item in plan.assumptions) if plan.assumptions else "- none"),
            "## Timeline\n" + "\n".join(f"- {step}" for step in plan.timeline),
            f"## Success Criterion\n{plan.success_criterion}",
            f"## Failure Criterion\n{plan.failure_criterion}",
            "## Unblock Suggestions\n"
            + ("\n".join(f"- {suggestion}" for suggestion in plan.unblock_suggestions) if plan.unblock_suggestions else "- none"),
        ],
    )


def render_decision_json(bundle: ResearchDecisionBundle) -> str:
    return json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2)


def first_nonempty(values: list[str]) -> str:
    for value in values:
        if value:
            return value
    return ""
