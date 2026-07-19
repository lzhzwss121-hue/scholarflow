from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from scholarflow_api.evidence import EvidenceSnippet, build_baseline_reference_evidence


TOP_VENUE_KEYWORDS = [
    "neurips",
    "nips",
    "icml",
    "iclr",
    "cvpr",
    "iccv",
    "eccv",
    "acl",
    "emnlp",
    "naacl",
    "aaai",
    "ijcai",
    "kdd",
    "sigir",
    "www",
    "the web conference",
    "tmlr",
    "jmlr",
    "tpami",
    "ijcv",
]

COMMON_BENCHMARK_TERMS = [
    "imagenet",
    "coco",
    "vqa",
    "gqa",
    "mme",
    "mmbench",
    "pope",
    "set5",
    "set14",
    "bsd100",
    "urban100",
    "div2k",
    "human preference",
    "win rate",
]


@dataclass
class BaselineVerification:
    evidence_level: str
    selection_basis: str
    citation_status: str
    citation_note: str
    code_status: str
    code_url: str
    code_source: str
    reproduction_status: str
    checks: dict[str, str]
    missing_evidence: list[str]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_level": self.evidence_level,
            "selection_basis": self.selection_basis,
            "citation_status": self.citation_status,
            "citation_note": self.citation_note,
            "code_status": self.code_status,
            "code_url": self.code_url,
            "code_source": self.code_source,
            "reproduction_status": self.reproduction_status,
            "checks": self.checks,
            "missing_evidence": self.missing_evidence,
            "summary": self.summary,
        }


@dataclass
class BaselineReference:
    title: str
    year: str
    venue: str
    source: str
    url: str
    category: str
    method_family: str
    reason: str
    strengths: str
    risks: str
    evidence_snippets: list[EvidenceSnippet]
    confidence: str
    evidence_gap: str
    verification: BaselineVerification

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "year": self.year,
            "venue": self.venue,
            "source": self.source,
            "url": self.url,
            "category": self.category,
            "method_family": self.method_family,
            "reason": self.reason,
            "strengths": self.strengths,
            "risks": self.risks,
            "evidence_snippets": [snippet.to_dict() for snippet in self.evidence_snippets],
            "confidence": self.confidence,
            "evidence_gap": self.evidence_gap,
            "verification": self.verification.to_dict(),
        }


@dataclass
class BaselineMap:
    direction: str
    task_definition: str
    classic_baselines: list[BaselineReference]
    recent_strong_baselines: list[BaselineReference]
    alternative_paradigms: list[BaselineReference]
    common_benchmarks: list[str]
    evaluation_risks: list[str]
    open_questions: list[str]
    generated_from: list[str]
    evidence_summary: str
    curator_notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "task_definition": self.task_definition,
            "classic_baselines": [baseline.to_dict() for baseline in self.classic_baselines],
            "recent_strong_baselines": [baseline.to_dict() for baseline in self.recent_strong_baselines],
            "alternative_paradigms": [baseline.to_dict() for baseline in self.alternative_paradigms],
            "common_benchmarks": self.common_benchmarks,
            "evaluation_risks": self.evaluation_risks,
            "open_questions": self.open_questions,
            "generated_from": self.generated_from,
            "evidence_summary": self.evidence_summary,
            "curator_notes": self.curator_notes,
        }


def build_baseline_map(direction: str, candidate_papers: list[dict[str, Any]], selected_papers: list[dict[str, Any]]) -> BaselineMap:
    normalized_direction = normalize_space(direction)
    # The selected papers may contain verified PDF text and structured Paper
    # Card signals. Keep those richer records ahead of metadata-only candidates.
    papers = dedupe_papers([*selected_papers, *candidate_papers])
    scored = sorted(papers, key=lambda paper: score_reference_candidate(paper, normalized_direction), reverse=True)
    family_buckets = group_by_method_family(scored)
    recent = select_recent_strong_baselines(scored, normalized_direction, limit=5)
    classic = select_classic_baselines(scored, recent, normalized_direction, limit=4)
    alternatives = select_alternative_paradigms(family_buckets, recent, classic, normalized_direction, limit=5)
    benchmarks = infer_common_benchmarks(normalized_direction, scored)
    risks = infer_evaluation_risks(normalized_direction, benchmarks, scored)
    questions = infer_open_questions(normalized_direction, alternatives, risks)
    generated_from = [paper.get("title", "") for paper in scored[:12] if paper.get("title")]

    return BaselineMap(
        direction=normalized_direction,
        task_definition=build_task_definition(normalized_direction),
        classic_baselines=classic,
        recent_strong_baselines=recent,
        alternative_paradigms=alternatives,
        common_benchmarks=benchmarks,
        evaluation_risks=risks,
        open_questions=questions,
        generated_from=generated_from,
        evidence_summary=build_baseline_evidence_summary(scored, recent, classic, alternatives),
        curator_notes=(
            "BaselineMap 优先使用本轮已解析 PDF 和 Paper Card 的本文方法证据，再补充检索候选池元数据。"
            "异质范式只在标题、摘要自述或 method 证据明确支持时标注。"
            "代码链接可从 paper metadata 或 PDF 文本提取，但 link_present 不代表仓库可访问、官方归属或代码可运行；"
            "引用关系仍需 citation graph 复核。"
        ),
    )


def render_baseline_map_markdown(baseline_map: BaselineMap) -> str:
    sections = [
        f"# BaselineMap: {baseline_map.direction}",
        "## Task Definition",
        baseline_map.task_definition,
        "## Classic Baselines",
        render_reference_list(baseline_map.classic_baselines),
        "## Recent Strong Baselines",
        render_reference_list(baseline_map.recent_strong_baselines),
        "## Alternative Paradigms",
        render_reference_list(baseline_map.alternative_paradigms),
        "## Common Benchmarks",
        "\n".join(f"- {item}" for item in baseline_map.common_benchmarks) or "- No stable benchmark signal yet.",
        "## Evaluation Risks",
        "\n".join(f"- {item}" for item in baseline_map.evaluation_risks),
        "## Open Questions",
        "\n".join(f"- {item}" for item in baseline_map.open_questions),
        "## Evidence Summary",
        baseline_map.evidence_summary,
        "## Curator Notes",
        baseline_map.curator_notes,
    ]
    return "\n\n".join(sections)


def render_reference_list(references: list[BaselineReference]) -> str:
    if not references:
        return "- No reliable reference found in current candidate pool."
    return "\n".join(
        " ".join(
            [
                f"- **{item.title}** ({item.year or 'year unknown'}, {item.venue or item.source or 'source unknown'}):",
                item.reason,
                f"Confidence: {item.confidence}.",
                (
                    f"Verification: {item.verification.evidence_level}; "
                    f"citation={item.verification.citation_status}; "
                    f"code={item.verification.code_status}; "
                    f"reproduction={item.verification.reproduction_status}."
                ),
                f"Evidence gap: {item.evidence_gap}",
            ],
        )
        for item in references
    )


def build_task_definition(direction: str) -> str:
    lower = direction.lower()
    if any(term in lower for term in ["hallucination", "幻觉", "faithfulness", "可信", "trustworthy"]):
        return (
            f"`{direction}` 的任务核心是识别模型输出是否被真实证据支撑，并区分 benchmark 分数提升与真实可靠性提升。"
        )
    if any(term in lower for term in ["agent", "workflow", "科研"]):
        return f"`{direction}` 的任务核心是把检索、阅读、批判、记忆和实验规划组织成可追溯的科研工作流。"
    if any(term in lower for term in ["restoration", "super-resolution", "超分", "image"]):
        return f"`{direction}` 的任务核心是恢复视觉细节，同时平衡感知质量、计算成本和可部署性。"
    return f"`{direction}` 的任务核心需要同时界定研究对象、失败模式、评价协议和可验证的改进目标。"


def select_recent_strong_baselines(papers: list[dict[str, Any]], direction: str, limit: int) -> list[BaselineReference]:
    recent = [paper for paper in papers if parse_year(paper.get("year", "")) >= 2024]
    if len(recent) < limit:
        recent.extend([paper for paper in papers if paper not in recent])
    return [
        to_reference(
            paper,
            "recent_strong",
            build_reason(paper, direction, "近三年强相关候选，可作为当前路线的直接比较对象。"),
            direction,
        )
        for paper in recent[:limit]
    ]


def select_classic_baselines(
    papers: list[dict[str, Any]],
    recent: list[BaselineReference],
    direction: str,
    limit: int,
) -> list[BaselineReference]:
    recent_titles = {normalize_title_key(item.title) for item in recent}
    older_or_foundational = [
        paper
        for paper in papers
        if normalize_title_key(paper.get("title", "")) not in recent_titles and parse_year(paper.get("year", "")) <= 2023
    ]
    return [
        to_reference(
            paper,
            "classic",
            "在候选池中更像该方向的基础参照；用于判断新论文是否真的超越了已有问题定义或方法范式。",
            direction,
        )
        for paper in older_or_foundational[:limit]
    ]


def select_alternative_paradigms(
    family_buckets: dict[str, list[dict[str, Any]]],
    recent: list[BaselineReference],
    classic: list[BaselineReference],
    direction: str,
    limit: int,
) -> list[BaselineReference]:
    used = {normalize_title_key(item.title) for item in [*recent, *classic]}
    output: list[BaselineReference] = []
    if not family_buckets:
        return output
    dominant_family = max(
        family_buckets,
        key=lambda family: (len(family_buckets[family]), family),
    )
    ordered_families = sorted(
        family_buckets,
        key=lambda family: (-len(family_buckets[family]), family),
    )
    for family in ordered_families:
        if family == dominant_family:
            continue
        papers = family_buckets[family]
        for paper in papers:
            key = normalize_title_key(paper.get("title", ""))
            if key in used:
                continue
            output.append(
                to_reference(
                    paper,
                    "alternative_paradigm",
                    f"代表 `{family}` 路线，可用于检查目标论文是否只是同范式内微调，或是否存在降维打击角度。",
                    direction,
                    method_family=family,
                ),
            )
            used.add(key)
            break
        if len(output) >= limit:
            break
    return output


def group_by_method_family(papers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for paper in papers:
        family = infer_method_family(paper)
        if not family:
            continue
        buckets.setdefault(family, []).append(paper)
    return buckets


def infer_method_family(paper: dict[str, Any]) -> str:
    title = normalize_space(paper.get("title", ""))
    abstract = normalize_space(paper.get("abstract", ""))
    signals = paper.get("paper_signals") if isinstance(paper.get("paper_signals"), dict) else {}
    method = normalize_space(signals.get("method", ""))
    contribution_type = normalize_space(signals.get("contribution_type", "")).lower()
    owned_text = normalize_space(f"{title}. {method or select_owned_method_text(abstract, paper.get('full_text', ''))}")
    lower = owned_text.lower()
    title_lower = title.lower()

    if (
        contribution_type in {"benchmark", "evaluation"}
        and any(marker in lower for marker in ["metric", "score", "benchmark", "evaluation", "protocol"])
    ) or (
        re.search(r"\b(?:[a-z0-9-]*score|metric)\b", title_lower)
        and re.search(r"\b(?:evaluation|metric|faithful|hallucination)\b", lower)
    ):
        return "evaluation-metric"
    if re.search(r"\b(?:visual prompt|prompt engineering|prompt tuning)\b", lower):
        return "visual-prompting"
    if re.search(r"\bcircuits?\b", title_lower):
        return "mechanistic-analysis"
    if re.search(r"\bdistractors?\b", title_lower):
        return "evaluation-protocol"
    if (
        re.search(r"\b(?:mamba|state[- ]space|selective scan)\b", title_lower)
        or re.search(r"\b(?:mamba|state[- ]space|selective scan)\s+(?:model|architecture|backbone)\b", lower)
    ):
        return "state-space"
    if (
        re.search(r"\bdiffusion\b", title_lower)
        or re.search(r"\b(?:diffusion|score-based)\s+(?:model|architecture|framework|process)\b", lower)
    ):
        return "diffusion"
    if (
        re.search(r"\b(?:retrieval-augmented|rag)\b", title_lower)
        or re.search(r"\b(?:retrieval-augmented|rag|retrieve and)\b", lower)
    ):
        return "retrieval"
    if (
        re.search(r"\b(?:agent|workflow)\b", title_lower)
        or re.search(r"\b(?:agent|tool-using|workflow)\s+(?:system|framework|architecture)\b", lower)
    ):
        return "agent"
    if re.search(r"\b(?:rlhf|dpo|preference optimization|alignment objective)\b", lower):
        return "alignment"
    if re.search(r"\b(?:logit|decoding|calibration|contrastive decoding)\b", lower):
        return "decoding-intervention"
    if re.search(r"\battention\b", lower) and re.search(
        r"\b(?:intervention|steering|manipulation|reweight|boost|suppress|mitigat|reduc)\w*\b",
        lower,
    ):
        return "attention-intervention"
    if re.search(r"\b(?:visual grounding|grounded|grounding)\b", lower):
        return "grounding"
    if (
        re.search(r"\b(?:transformer|swin|vision transformer|vit)\b", title_lower)
        or re.search(r"\b(?:transformer|swin|vision transformer|vit)\s+(?:model|architecture|backbone)\b", lower)
    ):
        return "transformer"
    if contribution_type == "benchmark":
        return "evaluation-protocol"
    return ""


def build_baseline_verification(
    paper: dict[str, Any],
    method_family: str,
) -> BaselineVerification:
    signals_value = paper.get("paper_signals")
    if isinstance(signals_value, dict):
        signals = signals_value
    elif hasattr(signals_value, "to_dict"):
        signals = signals_value.to_dict()
    else:
        signals = {}

    provenance = paper.get("full_text_provenance") if isinstance(paper.get("full_text_provenance"), dict) else {}
    full_text = normalize_space(paper.get("full_text", ""))
    full_text_ready = bool(full_text) and (
        not provenance or normalize_space(provenance.get("status", "")).lower() == "extracted"
    )
    explicit_level = normalize_space(paper.get("evidence_level", "")).lower().replace("-", "_")
    if full_text_ready:
        evidence_level = "full_text"
    elif explicit_level in {"metadata_only", "abstract_only"}:
        evidence_level = explicit_level
    elif normalize_space(paper.get("abstract", "")):
        evidence_level = "abstract_only"
    else:
        evidence_level = "metadata_only"

    method_ready = signal_is_available(signals.get("method", "")) or bool(method_family)
    dataset_ready = signal_is_available(signals.get("dataset", ""))
    metric_ready = signal_is_available(signals.get("metric", ""))
    baseline_ready = signal_is_available(signals.get("baseline", ""))
    code_value = normalize_space(paper.get("code", ""))
    code_url = extract_repository_url(code_value)
    code_source = "metadata.code" if code_url else ""
    if not code_url and full_text_ready:
        code_url = extract_repository_url(full_text)
        code_source = "pdf.full_text" if code_url else ""
    if code_url:
        code_status = "link_present"
    elif code_value.lower() not in {"", "unknown", "none", "n/a", "no", "false"}:
        code_status = "claimed_unverified"
    else:
        code_status = "not_found"

    checks = {
        "full_text": "ready" if full_text_ready else "missing",
        "method": "ready" if method_ready else "missing",
        "dataset": "ready" if dataset_ready else "missing",
        "metric": "ready" if metric_ready else "missing",
        "baseline": "ready" if baseline_ready else "missing",
        "code": "ready" if code_url else ("unverified" if code_status == "claimed_unverified" else "missing"),
    }
    if all(value == "ready" for value in checks.values()):
        reproduction_status = "ready"
    elif full_text_ready and sum(
        checks[name] == "ready" for name in ["method", "dataset", "metric", "baseline"]
    ) >= 3:
        reproduction_status = "partial"
    else:
        reproduction_status = "blocked"

    missing_labels = {
        "full_text": "可定位的 PDF 全文",
        "method": "可定位的方法证据",
        "dataset": "明确 dataset/benchmark",
        "metric": "明确评价指标",
        "baseline": "明确对照方法",
        "code": "可核验的代码仓库链接",
    }
    missing_evidence = [
        label
        for key, label in missing_labels.items()
        if checks[key] != "ready"
    ]
    if full_text_ready and method_ready:
        selection_basis = "full_text_method_evidence"
    elif full_text_ready:
        selection_basis = "full_text_topic_evidence"
    elif evidence_level == "abstract_only" and method_ready:
        selection_basis = "abstract_method_evidence"
    elif evidence_level == "abstract_only":
        selection_basis = "abstract_topic_evidence"
    else:
        selection_basis = "metadata_candidate"

    status_label = {
        "ready": "具备最小复现入口",
        "partial": "只具备部分复现条件",
        "blocked": "复现仍被关键证据阻塞",
    }[reproduction_status]
    return BaselineVerification(
        evidence_level=evidence_level,
        selection_basis=selection_basis,
        citation_status="not_checked",
        citation_note="尚未运行引用图或参考文献关系验证；当前只能确认候选论文自身的方向与方法证据。",
        code_status=code_status,
        code_url=code_url,
        code_source=code_source or ("metadata.code" if code_status == "claimed_unverified" else ""),
        reproduction_status=reproduction_status,
        checks=checks,
        missing_evidence=missing_evidence,
        summary=f"{status_label}；缺口：{'、'.join(missing_evidence) if missing_evidence else '无'}。",
    )


def signal_is_available(value: Any) -> bool:
    text = normalize_space(value)
    return bool(text) and not text.startswith(("当前证据不足", "未发现", "无法判断"))


def extract_repository_url(value: str) -> str:
    match = re.search(
        r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/[^\s)\]}>,'\"]+",
        value,
        flags=re.IGNORECASE,
    )
    return match.group(0).rstrip(".,;:") if match else ""


def select_owned_method_text(abstract: str, full_text: Any) -> str:
    candidates: list[str] = []
    for source in [abstract, extract_method_sections(str(full_text or ""))]:
        for sentence in split_sentences(source):
            lower = sentence.lower()
            if re.search(
                r"\bwe\s+(?:propose|introduce|present|develop|design|build|construct)\b"
                r"|\bour\s+(?:method|approach|framework|model|system|algorithm)\b",
                lower,
            ):
                candidates.append(sentence)
    return " ".join(candidates[:3])


def extract_method_sections(text: str) -> str:
    if not normalize_space(text):
        return ""
    current_section = "unknown"
    selected: list[str] = []
    for line in str(text).splitlines():
        section_match = re.fullmatch(r"\[Section: ([a-z_]+)\]", line.strip())
        if section_match:
            current_section = section_match.group(1)
            continue
        if current_section in {"abstract", "method"} and line.strip():
            selected.append(line.strip())
    return " ".join(selected)


def infer_common_benchmarks(direction: str, papers: list[dict[str, Any]]) -> list[str]:
    text = " ".join(paper_text(paper) for paper in papers)
    found = [term for term in COMMON_BENCHMARK_TERMS if term in text]
    lower = direction.lower()
    if "hallucination" in lower and "POPE" not in found:
        found.append("POPE / object hallucination style evaluation")
    if ("super-resolution" in lower or "超分" in lower) and "DIV2K" not in found:
        found.extend(["DIV2K", "Set5 / Set14 / Urban100"])
    if not found:
        found.extend(["task-specific benchmark", "human or expert validation", "cross-dataset generalization"])
    return unique_preserve_order(found)[:8]


def infer_evaluation_risks(direction: str, benchmarks: list[str], papers: list[dict[str, Any]]) -> list[str]:
    risks = [
        "只在对方法有利的单一 benchmark 上刷分，无法证明真实场景稳健性。",
        "指标可能测到表层相关性，而不是用户真正关心的可靠性、感知质量或任务完成质量。",
        "缺少跨数据集、跨模型族或长尾场景验证时，claim 容易被 benchmark bias 放大。",
    ]
    lower = direction.lower()
    if any(term in lower for term in ["hallucination", "faithfulness", "可信", "multimodal", "vlm"]):
        risks.append("VLM 评价如果只看答案对错，可能忽略输出是否被图像证据支撑。")
    if any(term in lower for term in ["agent", "workflow", "科研"]):
        risks.append("科研 Agent 评估如果只看生成文本流畅度，无法证明它真的减少科研时间或降低新手门槛。")
    if any("psnr" in paper_text(paper) or "ssim" in paper_text(paper) for paper in papers):
        risks.append("PSNR/SSIM 提升不一定对应人类感知质量提升，需要感知指标或用户研究补充。")
    if benchmarks:
        risks.append(f"当前候选池反复出现 `{benchmarks[0]}`，需要防止 benchmark-specific tuning。")
    return unique_preserve_order(risks)[:6]


def infer_open_questions(direction: str, alternatives: list[BaselineReference], risks: list[str]) -> list[str]:
    questions = [
        "这个方向真正不可替代的问题定义是什么，还是只是把旧任务包装成新术语？",
        "是否存在一个更简单的机制可以解释同样的性能提升，从而削弱复杂方法的必要性？",
        "如果把评价从平均分数改成失败模式定位，当前方法是否仍然成立？",
    ]
    if alternatives:
        family = alternatives[0].method_family or "异质范式"
        questions.append(f"与 `{family}` 路线相比，目标方法的优势是否来自核心机制，而不是实验设置？")
    if risks:
        questions.append("能否设计一个反例 benchmark，专门打穿当前方法最依赖的假设？")
    return questions[:5]


def to_reference(
    paper: dict[str, Any],
    category: str,
    reason: str,
    direction: str,
    *,
    method_family: str = "",
) -> BaselineReference:
    text = paper_text(paper)
    snippets, confidence, gap = build_baseline_reference_evidence(paper, direction, category)
    resolved_method_family = method_family or infer_method_family(paper)
    return BaselineReference(
        title=normalize_space(paper.get("title", "")) or "Untitled paper",
        year=normalize_space(str(paper.get("year", ""))),
        venue=normalize_space(paper.get("venue", "")),
        source=normalize_space(paper.get("source", "")),
        url=normalize_space(paper.get("url", "")),
        category=category,
        method_family=resolved_method_family,
        reason=reason,
        strengths=build_strength_signal(text),
        risks=build_risk_signal(text),
        evidence_snippets=snippets,
        confidence=confidence,
        evidence_gap=gap,
        verification=build_baseline_verification(paper, resolved_method_family),
    )


def build_baseline_evidence_summary(
    scored: list[dict[str, Any]],
    recent: list[BaselineReference],
    classic: list[BaselineReference],
    alternatives: list[BaselineReference],
) -> str:
    references = [*recent, *classic, *alternatives]
    reference_count = len(references)
    confidence_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    reproduction_counts: dict[str, int] = {"ready": 0, "partial": 0, "blocked": 0}
    for reference in references:
        confidence_counts[reference.confidence] = confidence_counts.get(reference.confidence, 0) + 1
        status = reference.verification.reproduction_status
        reproduction_counts[status] = reproduction_counts.get(status, 0) + 1
    code_link_count = sum(reference.verification.code_status == "link_present" for reference in references)
    citation_checked_count = sum(reference.verification.citation_status != "not_checked" for reference in references)
    full_text_count = sum(
        1
        for paper in scored
        if normalize_space(paper.get("full_text", ""))
        and (
            not isinstance(paper.get("full_text_provenance"), dict)
            or normalize_space(paper["full_text_provenance"].get("status", "")) == "extracted"
        )
    )
    return (
        f"BaselineMap 基于 {len(scored)} 篇候选论文生成，共形成 {reference_count} 个对比参照。"
        f" 证据覆盖：full_text={full_text_count}，metadata_or_abstract={max(0, len(scored) - full_text_count)}。"
        f" 置信度分布：high={confidence_counts.get('high', 0)}, "
        f"medium={confidence_counts.get('medium', 0)}, low={confidence_counts.get('low', 0)}。"
        f" 验证覆盖：code_link={code_link_count}/{reference_count}, "
        f"citation_graph_checked={citation_checked_count}/{reference_count}；"
        f"复现准备度：ready={reproduction_counts.get('ready', 0)}, "
        f"partial={reproduction_counts.get('partial', 0)}, blocked={reproduction_counts.get('blocked', 0)}。"
        " 已解析 PDF 会优先用于证据片段和方法范式判断；代码链接仅表示已定位，引用关系与仓库可运行性尚未外部验证。"
    )


def build_reason(paper: dict[str, Any], direction: str, fallback: str) -> str:
    overlap = [term for term in significant_terms(direction) if term in paper_text(paper)]
    venue = paper.get("venue") or paper.get("source") or "source metadata insufficient"
    if overlap:
        return f"匹配方向关键词：{', '.join(overlap[:4])}；来源信号：{venue}。{fallback}"
    return f"来源信号：{venue}。{fallback}"


def build_strength_signal(text: str) -> str:
    if "benchmark" in text or "evaluation" in text:
        return "可能强在任务定义或评价协议，可用于检查目标论文的评估真实性。"
    if "attention" in text or "transformer" in text:
        return "可能强在架构表达能力，可作为复杂模型路线的直接参照。"
    if "dataset" in text:
        return "可能强在数据构造，可用于判断方法提升是否依赖数据分布。"
    return "提供同方向问题定义或方法路线参照。"


def build_risk_signal(text: str) -> str:
    if "benchmark" in text:
        return "需要警惕 benchmark 设计是否偏向特定模型或答案分布。"
    if "large" in text or "scale" in text:
        return "需要警惕性能提升是否主要来自规模或算力。"
    if "attention" in text:
        return "需要关注复杂度和部署成本。"
    return "需要人工复核其与当前方向的真实相关性。"


def score_reference_candidate(paper: dict[str, Any], direction: str) -> float:
    text = paper_text(paper)
    terms = significant_terms(direction)
    score = sum(0.4 for term in terms if term in text)
    if any(keyword in text for keyword in TOP_VENUE_KEYWORDS):
        score += 0.7
    year = parse_year(paper.get("year", ""))
    if year >= 2024:
        score += 0.5
    if "benchmark" in text or "survey" in text or "baseline" in text:
        score += 0.35
    score += float(paper.get("relevance_score") or 0.0)
    return score


def dedupe_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for paper in papers:
        key = normalize_title_key(paper.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(paper)
    return output


def paper_text(paper: dict[str, Any]) -> str:
    signals = paper.get("paper_signals") if isinstance(paper.get("paper_signals"), dict) else {}
    return normalize_space(
        " ".join(
            [
                str(paper.get("title", "")),
                str(paper.get("abstract", "")),
                str(paper.get("venue", "")),
                str(paper.get("source", "")),
                str(signals.get("method", "")),
                str(signals.get("dataset", "")),
                str(signals.get("metric", "")),
                str(paper.get("full_text", ""))[:16000],
            ],
        ),
    ).lower()


def split_sentences(text: str) -> list[str]:
    normalized = normalize_space(text)
    if not normalized:
        return []
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。！？])\s+", normalized)
        if sentence.strip()
    ]


def parse_year(value: Any) -> int:
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else 0


def significant_terms(query: str) -> set[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "based",
        "model",
        "models",
        "paper",
        "research",
        "direction",
        "方向",
        "论文",
        "科研",
        "研究",
        "了解",
    }
    return {
        term
        for term in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", query.lower())
        if len(term) > 1 and term not in stop_words
    }


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = normalize_space(value)
        key = normalized.lower()
        if key and key not in seen:
            seen.add(key)
            output.append(normalized)
    return output


def normalize_title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
