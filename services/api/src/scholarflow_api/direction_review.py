from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from scholarflow_api.baseline_map import BaselineMap, render_baseline_map_markdown
from scholarflow_api.full_text import FullTextResult, resolve_open_full_texts
from scholarflow_api.literature import (
    PaperCandidate,
    build_query_intent,
    expand_queries,
    format_relevance_coverage,
    merge_candidate_access,
    priority_from_score,
    score_candidate,
    search_literature,
    significant_terms as literature_significant_terms,
)
from scholarflow_api.paper_card import DeepPaperCard, generate_deep_paper_card
from scholarflow_api.research_sight import ResearchSight, build_research_sight


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
    "nature",
    "science",
    "cell",
]

DIRECTION_REVIEW_SCHEMA_VERSION = "direction_review.v2"


@dataclass
class DirectionScope:
    direction: str
    round: int
    year_range: str
    included_scope: str
    excluded_scope: str
    subtopics: list[str]
    queries: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DirectionPaperReading:
    paper: dict[str, Any]
    abstract_translation: str
    card: DeepPaperCard
    full_text: dict[str, Any]
    research_sight: ResearchSight
    why_selected: str
    venue_signal: str
    self_read_priority: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper": self.paper,
            "abstract_translation": self.abstract_translation,
            "evidence_level": self.card.evidence_level,
            "full_text": self.full_text,
            "signals": self.card.signals.to_dict(),
            "sections": [section.to_dict() for section in self.card.sections],
            "research_sight": self.research_sight.to_dict(),
            "weakest_assumption": self.card.weakest_assumption,
            "minimal_reproduction": self.card.minimal_reproduction,
            "counterexample": self.card.counterexample,
            "follow_up_idea": self.card.follow_up_idea,
            "why_selected": self.why_selected,
            "venue_signal": self.venue_signal,
            "self_read_priority": self.self_read_priority,
        }


@dataclass
class DirectionReviewBundle:
    direction: str
    round: int
    review_status: str
    target_paper_count: int
    relevant_read_count: int
    low_relevance_count: int
    off_topic_count: int
    relevance_coverage: dict[str, int]
    scope: DirectionScope
    baseline_map: BaselineMap
    readings: list[DirectionPaperReading]
    recommended_paper_ids: list[str]
    direction_summary: str
    total_read_count: int
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DIRECTION_REVIEW_SCHEMA_VERSION,
            "direction": self.direction,
            "round": self.round,
            "review_status": self.review_status,
            "target_paper_count": self.target_paper_count,
            "round_read_count": len(self.readings),
            "relevant_read_count": self.relevant_read_count,
            "low_relevance_count": self.low_relevance_count,
            "off_topic_count": self.off_topic_count,
            "relevance_coverage": self.relevance_coverage,
            "scope": self.scope.to_dict(),
            "baseline_map": self.baseline_map.to_dict(),
            "papers": [reading.to_dict() for reading in self.readings],
            "recommended_paper_ids": self.recommended_paper_ids,
            "direction_summary": self.direction_summary,
            "total_read_count": self.total_read_count,
            "errors": self.errors,
        }


def build_direction_scope(direction: str, round_index: int) -> DirectionScope:
    normalized = normalize_space(direction)
    current_year = datetime.now(timezone.utc).year
    start_year = current_year - 2
    subtopics = infer_subtopics(normalized)
    bilingual_queries = expand_queries(normalized)
    queries = [
        normalized,
        *bilingual_queries[1:8],
        *[f"{normalized} {subtopic}" for subtopic in subtopics[:5]],
    ]
    return DirectionScope(
        direction=normalized,
        round=round_index,
        year_range=f"{start_year}-{current_year}",
        included_scope=(
            f"围绕 `{normalized}` 的近三年 AI 顶会/顶刊相关论文，优先覆盖方法、评测、benchmark、数据集、"
            "失败模式和综述性工作。"
        ),
        excluded_scope="排除弱相关应用堆叠、没有明确研究问题的工程报告、年份过旧且缺少近三年延续价值的论文。",
        subtopics=subtopics,
        queries=unique_preserve_order(queries),
    )


def retrieve_direction_candidate_pool(
    direction: str,
    round_index: int,
    previously_read_titles: list[str],
) -> tuple[DirectionScope, list[PaperCandidate], list[PaperCandidate], list[str], dict[str, int]]:
    scope = build_direction_scope(direction, round_index)
    candidates: list[PaperCandidate] = []
    errors: list[str] = []

    for query in scope.queries:
        result = search_literature(query, max_results=30, sources=["arxiv", "openalex"])
        candidates.extend(result.papers)
        errors.extend(result.errors)

    selected = select_top_direction_papers(candidates, direction, previously_read_titles, limit=10)
    relevance_coverage = summarize_direction_candidate_pool(candidates, direction)
    relevance_coverage["read_count"] = len(selected)
    return scope, candidates, selected, errors, relevance_coverage


def retrieve_direction_candidates(direction: str, round_index: int, previously_read_titles: list[str]) -> tuple[DirectionScope, list[PaperCandidate], list[str]]:
    scope, _candidate_pool, selected, errors, _coverage = retrieve_direction_candidate_pool(direction, round_index, previously_read_titles)
    return scope, selected, errors


def select_top_direction_papers(
    candidates: list[PaperCandidate],
    direction: str,
    previously_read_titles: list[str],
    limit: int,
) -> list[PaperCandidate]:
    current_year = datetime.now(timezone.utc).year
    min_year = current_year - 2
    previous_keys = {normalize_title_key(title) for title in previously_read_titles}
    deduped: dict[str, PaperCandidate] = {}
    direction_intent = build_query_intent(direction)

    for candidate in candidates:
        key = normalize_title_key(candidate.title)
        if not key or key in previous_keys:
            continue
        # Candidates are retrieved through several expanded subqueries. Re-score
        # every one against the user's original direction before it can enter the
        # reading set; otherwise a broad expansion can promote cross-domain work.
        relevance = score_candidate(candidate, direction_intent)
        candidate.relevance_score = relevance.score
        candidate.relevance_quality = relevance.quality
        candidate.priority = priority_from_score(relevance.score, relevance.quality)
        candidate.relation = relevance.reason
        candidate.matched_terms = relevance.matched_terms
        candidate.review_required = relevance.review_required
        if not is_relevant_candidate(candidate):
            continue
        year = parse_year(candidate.year)
        if year and year < min_year:
            continue
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = candidate
        elif score_direction_paper(candidate, direction) > score_direction_paper(existing, direction):
            merge_candidate_access(candidate, existing)
            deduped[key] = candidate
        else:
            merge_candidate_access(existing, candidate)

    ranked = sorted(deduped.values(), key=lambda paper: score_direction_paper(paper, direction), reverse=True)
    return ranked[:limit]


def build_direction_readings(
    papers: list[dict[str, Any]],
    direction: str,
    baseline_map: BaselineMap,
) -> list[DirectionPaperReading]:
    readings: list[DirectionPaperReading] = []
    full_text_results = resolve_open_full_texts(papers)
    for paper, full_text in zip(papers, full_text_results, strict=True):
        paper_for_evidence = build_full_text_evidence_paper(paper, full_text)
        card = generate_deep_paper_card(paper, full_text.text if full_text.is_extracted else "")
        sections = [section.to_dict() for section in card.sections]
        research_sight = build_research_sight(paper_for_evidence, sections, baseline_map, direction, card.signals)
        readings.append(
            DirectionPaperReading(
                paper=paper,
                abstract_translation=translate_abstract_to_chinese(paper),
                card=card,
                full_text=full_text.to_provenance(),
                research_sight=research_sight,
                why_selected=build_selection_reason(paper_for_evidence, direction, card),
                venue_signal=detect_venue_signal(paper.get("venue", "")),
                self_read_priority=False,
            ),
        )
    recommended_keys = {
        paper_identity(reading.paper)
        for reading in sorted(readings, key=lambda item: score_direction_reading(item, direction), reverse=True)[:3]
    }
    for reading in readings:
        reading.self_read_priority = paper_identity(reading.paper) in recommended_keys
    enforce_research_sight_diversity(readings)
    return readings


def build_full_text_evidence_paper(paper: dict[str, Any], result: FullTextResult) -> dict[str, Any]:
    evidence_paper = dict(paper)
    evidence_paper["full_text_provenance"] = result.to_provenance()
    if result.is_extracted:
        evidence_paper["evidence_level"] = "full_text"
        evidence_paper["full_text"] = result.text
    return evidence_paper


def enforce_research_sight_diversity(readings: list[DirectionPaperReading]) -> None:
    fields = ("why_good", "why_not_good", "better_angle", "next_step_proposal")
    fingerprints: dict[str, list[set[str]]] = {field: [] for field in fields}
    follow_up_fingerprints: list[set[str]] = []
    for reading in readings:
        for field in fields:
            current = sight_fingerprint(str(getattr(reading.research_sight, field, "")))
            if any(jaccard_similarity(current, previous) >= 0.72 for previous in fingerprints[field]):
                setattr(
                    reading.research_sight,
                    field,
                    bounded_duplicate_judgment(reading, field),
                )
                upsert_critique_evidence_rationale(
                    reading.research_sight,
                    field,
                    f"同轮 {field} 与其他论文重复度过高；未复用模板，已降级为需要该论文原文证据的判断。",
                )
                current = sight_fingerprint(str(getattr(reading.research_sight, field, "")))
            fingerprints[field].append(current)

        follow_up = sight_fingerprint(reading.card.follow_up_idea)
        if any(jaccard_similarity(follow_up, previous) >= 0.72 for previous in follow_up_fingerprints):
            reading.card.follow_up_idea = (
                f"无法提出独立 follow-up：`{reading.paper.get('title', '该论文')}` 的 limitation/claim/evaluation 原文证据"
                "不足以支持与同轮其他论文不同的研究设想。请先补充 PDF 后再判断。"
            )
            follow_up = sight_fingerprint(reading.card.follow_up_idea)
        follow_up_fingerprints.append(follow_up)


def bounded_duplicate_judgment(reading: DirectionPaperReading, field: str) -> str:
    title = reading.paper.get("title", "该论文")
    evidence = reading.card.signals.contribution_evidence or "未定位贡献类型原文证据"
    return (
        f"无法判断：`{title}` 的 {field} 与同轮论文出现模板化重复。"
        f"当前只能保留其自身的贡献证据线索：{evidence}；需要补充该论文的摘要/PDF 原文后再作独立判断。"
    )


def upsert_critique_evidence_rationale(research_sight: ResearchSight, field: str, rationale: str) -> None:
    for judgment in research_sight.critique_evidence:
        if judgment.field == field:
            judgment.rationale = rationale
            return


def sight_fingerprint(value: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", value.lower())
    stop_words = {"the", "and", "that", "with", "this", "paper", "good", "地方", "好的", "它的", "如果", "价值"}
    return {token for token in tokens if token not in stop_words}


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def build_direction_review_bundle(
    direction: str,
    round_index: int,
    scope: DirectionScope,
    baseline_map: BaselineMap,
    readings: list[DirectionPaperReading],
    previous_read_count: int,
    errors: list[str],
    relevance_coverage: dict[str, int] | None = None,
) -> DirectionReviewBundle:
    recommended = [reading.paper.get("id", "") for reading in readings if reading.self_read_priority]
    coverage = normalize_direction_coverage(relevance_coverage, readings)
    relevant_read_count = sum(1 for reading in readings if is_relevant_paper_dict(reading.paper))
    coverage["read_count"] = relevant_read_count
    total_read_count = previous_read_count + relevant_read_count
    target_paper_count = 10
    review_status = determine_review_status(
        relevant_read_count=relevant_read_count,
        low_relevance_count=coverage.get("weak_match_count", 0),
        off_topic_count=coverage.get("off_topic_count", 0),
        target_paper_count=target_paper_count,
    )
    if review_status in {"partial", "blocked"}:
        errors = [
            *errors,
            (
                f"{review_status}_direction_review: only {relevant_read_count}/{target_paper_count} strong/medium papers were read; "
                f"low_relevance={coverage.get('weak_match_count', 0)}, off_topic={coverage.get('off_topic_count', 0)}. "
                "this is not a complete ten-paper direction review."
            ),
        ]
    return DirectionReviewBundle(
        direction=direction,
        round=round_index,
        review_status=review_status,
        target_paper_count=target_paper_count,
        relevant_read_count=relevant_read_count,
        low_relevance_count=coverage.get("weak_match_count", 0),
        off_topic_count=coverage.get("off_topic_count", 0),
        relevance_coverage=coverage,
        scope=scope,
        baseline_map=baseline_map,
        readings=readings,
        recommended_paper_ids=recommended,
        direction_summary=build_direction_summary(direction, readings, total_read_count, baseline_map, review_status, target_paper_count),
        total_read_count=total_read_count,
        errors=errors,
    )


def normalize_direction_coverage(
    relevance_coverage: dict[str, int] | None,
    readings: list[DirectionPaperReading],
) -> dict[str, int]:
    coverage = empty_relevance_coverage()
    if relevance_coverage:
        coverage.update({key: int(value) for key, value in relevance_coverage.items() if isinstance(value, int)})
    if coverage.get("returned_count", 0) == 0 and readings:
        relevant_count = sum(1 for reading in readings if is_relevant_paper_dict(reading.paper))
        coverage.update(
            {
                "candidate_count": len(readings),
                "returned_count": len(readings),
                "strong_match_count": sum(
                    1 for reading in readings if reading.paper.get("relevance_quality") == "strong"
                ),
                "medium_match_count": sum(
                    1 for reading in readings if reading.paper.get("relevance_quality") != "strong"
                ),
                "weak_match_count": 0,
                "off_topic_count": 0,
                "filtered_count": 0,
            },
        )
        if relevant_count and not coverage.get("strong_match_count") and not coverage.get("medium_match_count"):
            coverage["medium_match_count"] = relevant_count
    return coverage


def determine_review_status(
    relevant_read_count: int,
    low_relevance_count: int,
    off_topic_count: int,
    target_paper_count: int,
) -> str:
    if relevant_read_count <= 0:
        return "blocked"
    # A direction round has a ten-paper target. Do not turn a smaller but clean
    # set into a completed review merely because it passed the five-paper minimum.
    if relevant_read_count < target_paper_count:
        return "partial"
    if low_relevance_count + off_topic_count > relevant_read_count * 2:
        return "partial"
    return "complete"


def build_direction_summary(
    direction: str,
    readings: list[DirectionPaperReading],
    total_read_count: int,
    baseline_map: BaselineMap,
    review_status: str,
    target_paper_count: int,
) -> str:
    venues = unique_preserve_order([reading.paper.get("venue", "") for reading in readings if reading.paper.get("venue")])
    top_titles = [reading.paper.get("title", "") for reading in readings if reading.self_read_priority]
    focus_terms = ", ".join(infer_subtopics(direction)[:4])
    baseline_titles = [item.title for item in baseline_map.recent_strong_baselines[:2]]
    baseline_note = "; ".join(baseline_titles) if baseline_titles else "当前 baseline 信号不足，需要继续检索"
    evidence_note = render_evidence_coverage_note(readings)
    if review_status != "complete":
        status_label = "Blocked Direction Review" if review_status == "blocked" else "Partial Direction Review"
        return (
            f"{status_label}：本轮仅完成 {len(readings)}/{target_paper_count} 篇强/中相关候选论文的证据边界阅读，"
            "未达到 10 篇方向级阅读目标，因此不能声称已完成一轮十篇论文综述。"
            f"{evidence_note}"
            f"当前累计已读 {total_read_count} 篇，ScholarFlow 只能给出临时判断："
            f"`{direction}` 暂时应围绕 {focus_terms or '任务定义、评价方式和失败模式'} 继续补充候选论文。"
            f" BaselineMap 当前线索：{baseline_note}。"
            f" 本轮可优先人工复核：{'; '.join(top_titles) if top_titles else '暂无足够候选，需要继续检索或人工上传论文'}。"
            f" 主要 venue/source 信号包括：{', '.join(venues[:6]) if venues else 'venue metadata insufficient'}。"
        )
    return (
        f"基于当前累计已读 {total_read_count} 篇论文，ScholarFlow 对 `{direction}` 的理解是："
        f"{evidence_note}"
        f"这个方向的核心不只是提出一个新模型，而是围绕 {focus_terms or '任务定义、评价方式和失败模式'} "
        "建立可验证的问题边界。近三年的高相关论文通常分成三类：第一类定义任务或 benchmark，"
        "第二类提出方法或系统改进，第三类暴露现有评测和方法的脆弱假设。"
        f"本轮 BaselineMap 显示应重点对照：{baseline_note}。"
        "用户下一步不应平均阅读所有论文，而应先亲自精读三篇最能代表问题定义、方法路线和评测缺陷的论文。"
        f"本轮最值得亲自精读的是：{'; '.join(top_titles) if top_titles else '当前结果不足三篇，需要继续检索或人工补充'}。"
        f" 主要 venue/source 信号包括：{', '.join(venues[:6]) if venues else 'venue metadata insufficient'}。"
    )


def render_evidence_coverage_note(readings: list[DirectionPaperReading]) -> str:
    counts = evidence_level_counts(readings)
    return (
        " 证据覆盖："
        f"metadata_only={counts.get('metadata_only', 0)}，"
        f"abstract_only={counts.get('abstract_only', 0)}，"
        f"full_text={counts.get('full_text', 0)}。"
        "Direction Review 的 complete 只表示方向级候选阅读达到阈值，不表示这些论文都经过完整正文阅读。"
    )


def evidence_level_counts(readings: list[DirectionPaperReading]) -> dict[str, int]:
    counts = {"metadata_only": 0, "abstract_only": 0, "full_text": 0}
    for reading in readings:
        level = normalize_space(reading.card.evidence_level) or "metadata_only"
        if level not in counts:
            level = "metadata_only"
        counts[level] += 1
    return counts


def render_direction_review_markdown(bundle: DirectionReviewBundle) -> str:
    recommended = [
        reading for reading in bundle.readings if reading.paper.get("id") in set(bundle.recommended_paper_ids)
    ]
    rows = [
        "| Priority | Paper | Year | Venue | Why selected |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, reading in enumerate(bundle.readings, start=1):
        paper = reading.paper
        rows.append(
            " | ".join(
                [
                    f"| {index}",
                    escape_table(paper.get("title", "")),
                    escape_table(str(paper.get("year", ""))),
                    escape_table(paper.get("venue", "")),
                    escape_table(reading.why_selected),
                ],
            )
            + " |",
        )

    return "\n\n".join(
        [
            f"# {'Direction Review' if bundle.review_status == 'complete' else bundle.review_status.title() + ' Direction Review'} Round {bundle.round}",
            f"Direction: {bundle.direction}",
            f"Status: {bundle.review_status}",
            f"Coverage: {bundle.relevant_read_count}/{bundle.target_paper_count}",
            f"Relevance coverage: {format_relevance_coverage(bundle.relevance_coverage)}",
            f"Evidence coverage: {render_evidence_coverage_note(bundle.readings)}",
            (
                "Warning: this review is partial/blocked and must not be presented as a completed ten-paper direction review."
                if bundle.review_status != "complete"
                else "Coverage note: completed enough strong/medium candidates for a direction-level review; this is not a full-text reading guarantee."
            ),
            f"Year range: {bundle.scope.year_range}",
            "## Scope",
            bundle.scope.included_scope,
            f"Excluded: {bundle.scope.excluded_scope}",
            "## Direction Summary",
            bundle.direction_summary,
            "## BaselineMap",
            render_baseline_map_markdown(bundle.baseline_map),
            "## Three Papers Worth Personal Deep Reading",
            "\n".join(
                f"- {reading.paper.get('title', '')}: {reading.why_selected}" for reading in recommended
            )
            or "- Not enough candidates.",
            "## Reading Set",
            "\n".join(rows),
            "## Retrieval Warnings",
            "\n".join(f"- {error}" for error in bundle.errors) if bundle.errors else "- none",
            "## UI Note",
            "摘要中文翻译和 12 条精读内容保存在每张论文卡片中，前端点击后进入独立阅读页，不在列表页直接铺开。",
        ],
    )


def render_direction_review_json(bundle: DirectionReviewBundle) -> str:
    return json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2)


def score_direction_paper(candidate: PaperCandidate, direction: str) -> float:
    return score_direction_paper_dict(candidate.to_dict(), direction)


def is_relevant_candidate(candidate: PaperCandidate) -> bool:
    quality = normalize_space(getattr(candidate, "relevance_quality", "")).lower()
    if quality in {"strong", "medium"}:
        return True
    if quality in {"weak", "off_topic"}:
        return False
    return candidate.priority in {"High", "Medium"} and float(candidate.relevance_score or 0.0) >= 0.75


def is_relevant_paper_dict(paper: dict[str, Any]) -> bool:
    quality = normalize_space(str(paper.get("relevance_quality", ""))).lower()
    if quality in {"strong", "medium"}:
        return True
    if quality in {"weak", "off_topic"}:
        return False
    return paper.get("priority") in {"High", "Medium"} and float(paper.get("relevance_score") or 0.0) >= 0.75


def score_direction_paper_dict(paper: dict[str, Any], direction: str) -> float:
    title = str(paper.get("title", "")).lower()
    abstract = str(paper.get("abstract", "")).lower()
    text = f"{title} {abstract} {paper.get('venue', '')}".lower()
    matched_terms = candidate_matched_terms(paper)
    direct_focus_terms = [
        term
        for term in matched_terms
        if term in {"object hallucination", "pope", "visual grounding", "evidence grounding", "faithfulness", "visual question answering"}
    ]
    # Relevance already passed the hard gate. This second ranking only decides
    # which papers are recommended for self-reading, so it favours direct title
    # or abstract evidence before recency and venue prestige.
    title_direct = sum(0.8 for term in direct_focus_terms if term in title)
    abstract_direct = sum(0.45 for term in direct_focus_terms if term in abstract)
    direct_evidence = 0.75 if normalize_space(abstract) else 0.0
    matched_coverage = min(1.2, 0.22 * len(matched_terms))
    year = parse_year(str(paper.get("year", "")))
    current_year = datetime.now(timezone.utc).year
    recency = 0.3 if year and year >= current_year - 2 else 0.08 if year else 0.0
    venue = 0.35 if is_top_venue(str(paper.get("venue", ""))) else 0.08
    base = float(paper.get("relevance_score") or 0.0)
    return base + title_direct + abstract_direct + direct_evidence + matched_coverage + recency + venue


def empty_relevance_coverage() -> dict[str, int]:
    return {
        "candidate_count": 0,
        "returned_count": 0,
        "strong_match_count": 0,
        "medium_match_count": 0,
        "weak_match_count": 0,
        "off_topic_count": 0,
        "filtered_count": 0,
        "read_count": 0,
    }


def build_selection_reason(
    paper: dict[str, Any],
    direction: str,
    card: DeepPaperCard | None = None,
) -> str:
    terms = candidate_matched_terms(paper) or [
        term for term in significant_terms(direction) if term in f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
    ]
    venue = detect_venue_signal(str(paper.get("venue", "")))
    quality = normalize_space(str(paper.get("relevance_quality", ""))) or "medium"
    evidence_level = card.evidence_level if card else ("abstract_only" if normalize_space(paper.get("abstract", "")) else "metadata_only")
    source_snippet = selection_evidence_snippet(paper, terms)
    signal_names = []
    if card:
        signal_names = [
            field
            for field in ("claim", "dataset", "metric", "baseline")
            if has_card_signal(getattr(card.signals, field, ""))
        ]
    if terms:
        return (
            f"相关性 {quality}；核心匹配词：{', '.join(terms[:5])}；"
            f"可核验证据：{source_snippet}；证据等级：{evidence_level}；"
            f"已定位信号：{', '.join(signal_names) if signal_names else '未定位 claim/dataset/metric/baseline'}；"
            f"{venue}；年份 {paper.get('year') or 'unknown'}。"
        )
    return f"未定位方向核心词，不应进入推荐精读；证据等级：{evidence_level}；{venue}。"


def score_direction_reading(reading: DirectionPaperReading, direction: str) -> float:
    evidence_weight = {"metadata_only": 0.0, "abstract_only": 0.45, "full_text": 1.1}.get(
        normalize_space(reading.card.evidence_level),
        0.0,
    )
    signal_count = sum(
        has_card_signal(getattr(reading.card.signals, field, ""))
        for field in ("claim", "dataset", "metric", "baseline")
    )
    return score_direction_paper_dict(reading.paper, direction) + evidence_weight + signal_count * 0.28


def selection_evidence_snippet(paper: dict[str, Any], matched_terms: list[str]) -> str:
    source_values = [
        ("pdf.full_text", normalize_space(paper.get("full_text", ""))),
        ("metadata.abstract", normalize_space(paper.get("abstract", ""))),
        ("metadata.title", normalize_space(paper.get("title", ""))),
    ]
    for source, value in source_values:
        if not value:
            continue
        sentences = [normalize_space(item) for item in re.split(r"(?<=[.!?。！？])\s+", value) if normalize_space(item)]
        sentence = next(
            (item for item in sentences if any(term and term in item.lower() for term in matched_terms)),
            sentences[0] if sentences else value,
        )
        return f"{source}=`{truncate_text(sentence, 180)}`"
    return "没有 title/abstract/full_text 原文片段"


def has_card_signal(value: str) -> bool:
    normalized = normalize_space(value)
    return bool(normalized) and not normalized.startswith("当前证据不足") and not normalized.startswith("未识别")


def paper_identity(paper: dict[str, Any]) -> str:
    return normalize_space(paper.get("id", "")) or normalize_title_key(paper.get("title", ""))


def summarize_direction_candidate_pool(candidates: list[PaperCandidate], direction: str) -> dict[str, int]:
    intent = build_query_intent(direction)
    deduped: dict[str, PaperCandidate] = {}
    for candidate in candidates:
        key = normalize_title_key(candidate.title)
        if key and key not in deduped:
            deduped[key] = candidate
    counts = {"strong": 0, "medium": 0, "weak": 0, "off_topic": 0}
    for candidate in deduped.values():
        relevance = score_candidate(candidate, intent)
        counts[relevance.quality] = counts.get(relevance.quality, 0) + 1
    returned_count = counts["strong"] + counts["medium"]
    filtered_count = counts["weak"] + counts["off_topic"]
    return {
        "candidate_count": len(deduped),
        "returned_count": returned_count,
        "strong_match_count": counts["strong"],
        "medium_match_count": counts["medium"],
        "weak_match_count": counts["weak"],
        "off_topic_count": counts["off_topic"],
        "filtered_count": filtered_count,
        "read_count": 0,
    }


def candidate_matched_terms(paper: dict[str, Any]) -> list[str]:
    direct = paper.get("matched_terms")
    if isinstance(direct, list):
        values = [normalize_space(item) for item in direct]
        return [value for value in values if value]
    return safe_json_list(paper.get("matched_terms_json", "[]"))


def translate_abstract_to_chinese(paper: dict[str, Any]) -> str:
    abstract = normalize_space(str(paper.get("abstract") or ""))
    if not abstract:
        return "当前候选论文没有可用 abstract。需要用户上传 PDF、粘贴摘要，或继续检索补充元数据。"
    title = normalize_space(str(paper.get("title") or "该论文"))
    if contains_cjk(abstract):
        return abstract
    first_sentence = abstract.split(". ")[0].strip()
    return (
        f"中文摘要翻译/概述：`{title}` 主要研究 {first_sentence[:260]}。"
        " 这段内容由 ScholarFlow 基于英文摘要生成，用于快速阅读入口；正式引用前仍应核对原文。"
    )


def infer_subtopics(direction: str) -> list[str]:
    lower = direction.lower()
    subtopics: list[str] = []
    if "vlm" in lower or "vision" in lower or "multimodal" in lower or "多模态" in lower:
        subtopics.extend(["vision-language model", "large vision-language model", "multimodal evaluation", "visual grounding"])
    if "视觉问答" in lower or "visual question" in lower or "vqa" in lower:
        subtopics.extend(["visual question answering", "VQA faithfulness", "grounded evidence VQA"])
    if "证据" in lower or "忠实" in lower or "faithfulness" in lower or "grounding" in lower:
        subtopics.extend(["evidence faithfulness", "visual grounding", "grounded evidence"])
        if "多模态" in lower or "视觉问答" in lower or "vlm" in lower or "vision" in lower:
            subtopics.extend(["object hallucination", "POPE object hallucination", "LVLM hallucination benchmark"])
    if "hallucination" in lower or "幻觉" in lower:
        subtopics.extend(["hallucination benchmark", "object hallucination", "evidence faithfulness"])
    if "agent" in lower or "workflow" in lower or "科研" in lower:
        subtopics.extend(["research agent", "tool-augmented agent", "scientific discovery workflow"])
    if "alignment" in lower or "trustworthy" in lower or "可信" in lower:
        subtopics.extend(["trustworthy AI", "alignment", "reliability evaluation"])
    if not subtopics:
        subtopics.extend(["benchmark", "method", "survey", "evaluation", "dataset"])
    return unique_preserve_order(subtopics)


def detect_venue_signal(venue: str) -> str:
    normalized = normalize_space(venue)
    if is_top_venue(normalized):
        matched = next(keyword for keyword in TOP_VENUE_KEYWORDS if keyword in normalized.lower())
        return f"top venue/journal signal: {matched.upper()}"
    if "arxiv" in normalized.lower():
        return "arXiv preprint; venue needs verification"
    if normalized:
        return f"venue/source: {normalized}"
    return "venue metadata unavailable"


def is_top_venue(venue: str) -> bool:
    lower = venue.lower()
    return any(keyword in lower for keyword in TOP_VENUE_KEYWORDS)


def parse_year(value: str) -> int | None:
    if not value:
        return None
    match = re.search(r"(19|20)\d{2}", str(value))
    return int(match.group(0)) if match else None


def significant_terms(query: str) -> set[str]:
    expanded_terms = literature_significant_terms(query)
    if expanded_terms:
        return expanded_terms
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


def normalize_title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def truncate_text(value: str, limit: int) -> str:
    normalized = normalize_space(value)
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 3]}..."


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower()
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))


def safe_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def escape_table(value: str) -> str:
    return normalize_space(value).replace("|", "\\|")
