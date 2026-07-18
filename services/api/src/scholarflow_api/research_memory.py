from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from scholarflow_api.literature import build_query_intent
from scholarflow_api.text_utils import extract_terms, normalize_space, normalize_terms, score_term_overlap

RESEARCH_MEMORY_SCHEMA_VERSION = "research_memory_answer.v3"
MIN_RELIABLE_MEMORY_SCORE = 0.28


@dataclass
class PaperMemoryHit:
    memory: dict[str, Any]
    score: float
    title_score: float
    keyword_score: float
    section_score: float
    priority_score: float
    snippets: list[str]

    def to_dict(self) -> dict[str, Any]:
        paper = memory_record_to_paper(self.memory, self.score)
        evidence_refs = memory_evidence_refs(self.memory)
        return {
            "paper": paper,
            "direction": self.memory.get("direction", ""),
            "round": int(self.memory.get("round_index") or 0),
            "score": self.score,
            "title_score": self.title_score,
            "keyword_score": self.keyword_score,
            "section_score": self.section_score,
            "priority_score": self.priority_score,
            "snippets": self.snippets,
            "evidence_quality": memory_evidence_quality(self.memory),
            "evidence_refs": evidence_refs,
            "abstract_translation": self.memory.get("abstract_translation", ""),
            "weakest_assumption": self.memory.get("weakest_assumption", ""),
            "minimal_reproduction": self.memory.get("minimal_reproduction", ""),
            "counterexample": self.memory.get("counterexample", ""),
            "follow_up_idea": self.memory.get("follow_up_idea", ""),
            "why_selected": self.memory.get("why_selected", ""),
            "research_sight": safe_json_dict(self.memory.get("research_sight_json", "{}")),
            "self_read_priority": bool(int(self.memory.get("self_read_priority") or 0)),
        }


@dataclass
class PaperMemoryScore:
    title_score: float
    keyword_score: float
    section_score: float
    priority_score: float

    @property
    def total(self) -> float:
        return round(self.title_score + self.keyword_score + self.section_score + self.priority_score, 4)


FIELD_INTENTS: dict[str, dict[str, list[str]]] = {
    "experiment": {
        "triggers": ["experiment", "reproduce", "reproduction", "复现", "实验", "验证"],
        "fields": ["minimal_reproduction", "sections_json"],
        "terms": ["minimal reproduction", "dataset", "metric", "baseline", "ablation", "实验", "复现"],
    },
    "gap": {
        "triggers": ["gap", "limitation", "weakness", "缺口", "空白", "局限", "不足"],
        "fields": ["weakest_assumption", "follow_up_idea", "research_sight_json", "sections_json"],
        "terms": ["limitation", "weakest assumption", "better angle", "follow up", "gap", "局限", "缺口"],
    },
    "baseline": {
        "triggers": ["baseline", "baselines", "comparison", "对比", "基线", "参照"],
        "fields": ["research_sight_json", "minimal_reproduction", "sections_json"],
        "terms": ["baseline", "baseline comparison", "strong baseline", "comparison", "基线", "参照"],
    },
    "counterexample": {
        "triggers": ["counterexample", "counterexamples", "反例", "攻击", "failure case"],
        "fields": ["counterexample", "weakest_assumption", "research_sight_json"],
        "terms": ["counterexample", "failure mode", "failure", "反例", "失败模式"],
    },
}


@dataclass
class DirectionMemorySnapshot:
    direction: str
    total_papers: int
    round_count: int
    summary: str
    paper_ids: list[str]
    baseline_map: dict[str, Any]
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryClaim:
    id: str
    statement: str
    support_status: str
    confidence: str
    paper_ids: list[str]
    evidence_refs: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchMemoryAnswer:
    question: str
    top_k: int
    answer: str
    hits: list[PaperMemoryHit]
    direction_memory: DirectionMemorySnapshot | None
    total_memories: int
    reliability_status: str
    reliability_reason: str
    warnings: list[str]
    answer_summary: str = ""
    claims: list[MemoryClaim] = field(default_factory=list)
    unanswered_parts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RESEARCH_MEMORY_SCHEMA_VERSION,
            "question": self.question,
            "top_k": self.top_k,
            "answer": self.answer,
            "hits": [hit.to_dict() for hit in self.hits],
            "direction_memory": self.direction_memory.to_dict() if self.direction_memory else None,
            "total_memories": self.total_memories,
            "reliability_status": self.reliability_status,
            "reliability_reason": self.reliability_reason,
            "warnings": self.warnings,
            "answer_summary": self.answer_summary,
            "claims": [claim.to_dict() for claim in self.claims],
            "unanswered_parts": self.unanswered_parts,
        }


def upsert_direction_reading_memories(
    connection,
    project_id: str,
    direction: str,
    round_index: int,
    readings: list[Any],
    now: str,
) -> list[str]:
    memory_ids: list[str] = []
    for reading in readings:
        if not is_relevant_memory_paper(reading.paper):
            continue
        payload = build_memory_payload_from_reading(project_id, direction, round_index, reading, now)
        upsert_paper_memory_payload(connection, payload)
        memory_ids.append(payload["id"])
    return memory_ids


def upsert_paper_memory_payload(connection, payload: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO paper_memories (
            id, project_id, paper_id, direction, round_index, title, authors, year, venue, source,
            url, abstract_translation, sections_json, weakest_assumption, minimal_reproduction,
            counterexample, follow_up_idea, why_selected, research_sight_json, memory_text,
            keywords_json, self_read_priority, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            direction = excluded.direction,
            round_index = excluded.round_index,
            title = excluded.title,
            authors = excluded.authors,
            year = excluded.year,
            venue = excluded.venue,
            source = excluded.source,
            url = excluded.url,
            abstract_translation = excluded.abstract_translation,
            sections_json = excluded.sections_json,
            weakest_assumption = excluded.weakest_assumption,
            minimal_reproduction = excluded.minimal_reproduction,
            counterexample = excluded.counterexample,
            follow_up_idea = excluded.follow_up_idea,
            why_selected = excluded.why_selected,
            research_sight_json = excluded.research_sight_json,
            memory_text = excluded.memory_text,
            keywords_json = excluded.keywords_json,
            self_read_priority = excluded.self_read_priority,
            updated_at = excluded.updated_at
        """,
        (
            payload["id"],
            payload["project_id"],
            payload["paper_id"],
            payload["direction"],
            payload["round_index"],
            payload["title"],
            payload["authors"],
            payload["year"],
            payload["venue"],
            payload["source"],
            payload["url"],
            payload["abstract_translation"],
            payload["sections_json"],
            payload["weakest_assumption"],
            payload["minimal_reproduction"],
            payload["counterexample"],
            payload["follow_up_idea"],
            payload["why_selected"],
            payload["research_sight_json"],
            payload["memory_text"],
            payload["keywords_json"],
            1 if payload["self_read_priority"] else 0,
            payload["created_at"],
            payload["updated_at"],
        ),
    )


def build_memory_payload_from_reading(
    project_id: str,
    direction: str,
    round_index: int,
    reading: Any,
    now: str,
) -> dict[str, Any]:
    paper = reading.paper
    if hasattr(reading, "card"):
        sections = [section.to_dict() for section in reading.card.sections]
        weakest_assumption = reading.card.weakest_assumption
        minimal_reproduction = reading.card.minimal_reproduction
        counterexample = reading.card.counterexample
        follow_up_idea = reading.card.follow_up_idea
    else:
        sections = list(getattr(reading, "sections", []) or [])
        weakest_assumption = getattr(reading, "weakest_assumption", "")
        minimal_reproduction = getattr(reading, "minimal_reproduction", "")
        counterexample = getattr(reading, "counterexample", "")
        follow_up_idea = getattr(reading, "follow_up_idea", "")
    return build_memory_payload(
        project_id=project_id,
        direction=direction,
        round_index=round_index,
        paper=paper,
        abstract_translation=reading.abstract_translation,
        sections=sections,
        weakest_assumption=weakest_assumption,
        minimal_reproduction=minimal_reproduction,
        counterexample=counterexample,
        follow_up_idea=follow_up_idea,
        why_selected=reading.why_selected,
        research_sight=reading.research_sight.to_dict(),
        self_read_priority=reading.self_read_priority,
        now=now,
    )


def build_memory_payload(
    project_id: str,
    direction: str,
    round_index: int,
    paper: dict[str, Any],
    abstract_translation: str,
    sections: list[dict[str, Any]],
    weakest_assumption: str,
    minimal_reproduction: str,
    counterexample: str,
    follow_up_idea: str,
    why_selected: str,
    self_read_priority: bool,
    now: str,
    research_sight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    research_sight = research_sight or {}
    memory_text = build_memory_text(
        paper,
        abstract_translation,
        sections,
        weakest_assumption,
        minimal_reproduction,
        counterexample,
        follow_up_idea,
        why_selected,
        research_sight,
    )
    keywords = extract_memory_keywords(memory_text)
    paper_id = paper.get("id") or ""
    return {
        "id": build_memory_id(project_id, paper_id, paper.get("title", ""), direction),
        "project_id": project_id,
        "paper_id": paper_id or None,
        "direction": normalize_space(direction),
        "round_index": round_index,
        "title": normalize_space(paper.get("title", "")),
        "authors": normalize_space(paper.get("authors", "")),
        "year": normalize_space(str(paper.get("year", ""))),
        "venue": normalize_space(paper.get("venue", "")),
        "source": normalize_space(paper.get("source", "")),
        "url": normalize_space(paper.get("url", "")),
        "abstract_translation": normalize_space(abstract_translation),
        "sections_json": json.dumps(sections, ensure_ascii=False, indent=2),
        "weakest_assumption": normalize_space(weakest_assumption),
        "minimal_reproduction": normalize_space(minimal_reproduction),
        "counterexample": normalize_space(counterexample),
        "follow_up_idea": normalize_space(follow_up_idea),
        "why_selected": normalize_space(why_selected),
        "research_sight_json": json.dumps(research_sight, ensure_ascii=False, indent=2),
        "memory_text": memory_text,
        "keywords_json": json.dumps(keywords, ensure_ascii=False),
        "self_read_priority": self_read_priority,
        "created_at": now,
        "updated_at": now,
    }


def build_memory_text(
    paper: dict[str, Any],
    abstract_translation: str,
    sections: list[dict[str, Any]],
    weakest_assumption: str,
    minimal_reproduction: str,
    counterexample: str,
    follow_up_idea: str,
    why_selected: str,
    research_sight: dict[str, Any],
) -> str:
    section_text = " ".join(
        f"{section.get('title', '')}: {section.get('content', '')}" for section in sections
    )
    sight_text = " ".join(f"{key}: {value}" for key, value in research_sight.items())
    return normalize_space(
        " ".join(
            [
                paper.get("title", ""),
                paper.get("abstract", ""),
                paper.get("venue", ""),
                abstract_translation,
                section_text,
                weakest_assumption,
                minimal_reproduction,
                counterexample,
                follow_up_idea,
                why_selected,
                sight_text,
            ],
        ),
    )


def upsert_direction_memory_snapshot(
    connection,
    project_id: str,
    direction: str,
    now: str,
    baseline_map: dict[str, Any] | None = None,
) -> DirectionMemorySnapshot:
    if baseline_map is None:
        baseline_map = fetch_existing_direction_baseline_map(connection, project_id, direction)
    records = fetch_memory_records(connection, project_id, direction)
    snapshot = build_direction_memory_snapshot(direction, records, now, baseline_map)
    snapshot_id = build_direction_memory_id(project_id, direction)
    connection.execute(
        """
        INSERT INTO direction_memories (
            id, project_id, direction, total_papers, round_count, summary, paper_ids_json,
            baseline_map_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            total_papers = excluded.total_papers,
            round_count = excluded.round_count,
            summary = excluded.summary,
            paper_ids_json = excluded.paper_ids_json,
            baseline_map_json = excluded.baseline_map_json,
            updated_at = excluded.updated_at
        """,
        (
            snapshot_id,
            project_id,
            snapshot.direction,
            snapshot.total_papers,
            snapshot.round_count,
            snapshot.summary,
            json.dumps(snapshot.paper_ids, ensure_ascii=False),
            json.dumps(snapshot.baseline_map, ensure_ascii=False, indent=2),
            now,
            now,
        ),
    )
    return snapshot


def fetch_existing_direction_baseline_map(connection, project_id: str, direction: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT baseline_map_json FROM direction_memories
        WHERE project_id = ? AND lower(direction) = lower(?)
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (project_id, normalize_space(direction)),
    ).fetchone()
    if not row:
        return {}
    return safe_json_dict(dict(row).get("baseline_map_json", "{}"))


def build_direction_memory_snapshot(
    direction: str,
    records: list[dict[str, Any]],
    now: str,
    baseline_map: dict[str, Any] | None = None,
) -> DirectionMemorySnapshot:
    unique_records = records[:30]
    paper_ids = [record.get("paper_id") or record["id"] for record in unique_records]
    round_count = max([int(record.get("round_index") or 0) for record in unique_records] or [0])
    key_terms = extract_memory_keywords(" ".join(record.get("memory_text", "") for record in unique_records), limit=8)
    recommended = [record["title"] for record in unique_records if int(record.get("self_read_priority") or 0) == 1][:5]
    sight_focus = extract_sight_focus(unique_records)
    baseline_note = build_baseline_memory_note(baseline_map or {})
    summary = (
        f"Direction Memory `{direction}` 当前覆盖 {len(unique_records)} 篇论文，来自 {round_count} 轮方向精读。"
        f" 主要记忆关键词：{', '.join(key_terms) if key_terms else '暂无稳定关键词'}。"
        f" 优先精读线索：{'; '.join(recommended) if recommended else '暂无显式推荐论文'}。"
        f" 科研审美线索：{sight_focus or '暂无 ResearchSight 聚合线索'}。"
        f" BaselineMap 线索：{baseline_note}"
        " 用户提问时应先检索相关论文，再基于命中的 paper memory 回答，而不是把全部论文塞入一次模型上下文。"
    )
    return DirectionMemorySnapshot(
        direction=direction,
        total_papers=len(unique_records),
        round_count=round_count,
        summary=summary,
        paper_ids=paper_ids,
        baseline_map=baseline_map or {},
        updated_at=now,
    )


def query_research_memory(
    connection,
    project_id: str,
    question: str,
    top_k: int,
    now: str,
    direction: str = "",
) -> ResearchMemoryAnswer:
    backfill_project_research_memory(connection, project_id, now)
    records = fetch_memory_records(connection, project_id, direction)
    ranked_hits = search_memory_records(records, question, top_k)
    snapshot = fetch_direction_memory_snapshot(connection, project_id, direction)
    warnings: list[str] = []
    reliability_status = "reliable"
    reliability_reason = "命中至少一篇具有问题词项证据的 paper memory。"
    if not records:
        warnings.append("当前项目还没有 paper memory。请先执行方向精读，或生成 paper cards。")
        reliability_status = "no_memory"
        reliability_reason = "当前项目没有可检索的 paper memory。"
    reliable_hits = [hit for hit in ranked_hits if is_reliable_memory_hit(hit, question)]
    missing_terms: list[str] = []
    if records and not reliable_hits:
        missing_terms = missing_memory_query_terms(records, question)
        reliability_status = "no_reliable_hit"
        reliability_reason = (
            "检索候选没有达到可靠命中门槛：需要至少一个来自标题、metadata.abstract 或 pdf.full_text 的问题词项证据，"
            f"且总分不低于 {MIN_RELIABLE_MEMORY_SCORE:.2f}。"
        )
        warnings.append(
            "当前记忆没有可靠证据回答此问题；未把零分或弱相关论文包装成最相关命中。"
        )
        warnings.append("建议先重新检索该方向，或上传/解析相关 PDF 后再生成 Paper Card 与 Memory。")
        if missing_terms:
            warnings.append(f"当前原文证据未覆盖主题词：{', '.join(missing_terms[:5])}。")
            warnings.append(f"可尝试改写为：{' '.join(missing_terms[:3])} + 具体任务/数据集/指标，或重新运行 Literature Search。")

    answer_summary, claims, unanswered_parts = build_memory_synthesis(
        question,
        reliable_hits,
        reliability_status,
        missing_terms,
    )
    answer_text = (
        render_memory_synthesis_text(answer_summary, claims, unanswered_parts)
        if reliable_hits
        else build_memory_answer(question, reliable_hits, snapshot, reliability_status, missing_terms)
    )
    return ResearchMemoryAnswer(
        question=question,
        top_k=top_k,
        answer=answer_text,
        hits=reliable_hits,
        direction_memory=snapshot,
        total_memories=len(records),
        reliability_status=reliability_status,
        reliability_reason=reliability_reason,
        warnings=warnings,
        answer_summary=answer_summary,
        claims=claims,
        unanswered_parts=unanswered_parts,
    )


def fetch_memory_records(connection, project_id: str, direction: str = "") -> list[dict[str, Any]]:
    if direction.strip():
        rows = connection.execute(
            """
            SELECT * FROM paper_memories
            WHERE project_id = ? AND lower(direction) = lower(?)
            ORDER BY round_index ASC, self_read_priority DESC, updated_at ASC
            """,
            (project_id, normalize_space(direction)),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM paper_memories
            WHERE project_id = ?
            ORDER BY round_index ASC, self_read_priority DESC, updated_at ASC
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_direction_memory_snapshot(
    connection,
    project_id: str,
    direction: str = "",
) -> DirectionMemorySnapshot | None:
    if direction.strip():
        row = connection.execute(
            """
            SELECT * FROM direction_memories
            WHERE project_id = ? AND lower(direction) = lower(?)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (project_id, normalize_space(direction)),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT * FROM direction_memories
            WHERE project_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    return DirectionMemorySnapshot(
        direction=data["direction"],
        total_papers=int(data["total_papers"] or 0),
        round_count=int(data["round_count"] or 0),
        summary=data["summary"],
        paper_ids=safe_json_list(data.get("paper_ids_json", "[]")),
        baseline_map=safe_json_dict(data.get("baseline_map_json", "{}")),
        updated_at=data["updated_at"],
    )


def search_memory_records(
    records: list[dict[str, Any]],
    question: str,
    top_k: int,
    allow_weak: bool = False,
) -> list[PaperMemoryHit]:
    terms = memory_query_terms(question)
    scored: list[PaperMemoryHit] = []
    for record in records:
        breakdown = score_memory_record(record, terms, question)
        if breakdown.total > 0 or allow_weak:
            scored.append(
                PaperMemoryHit(
                    memory=record,
                    score=breakdown.total,
                    title_score=breakdown.title_score,
                    keyword_score=breakdown.keyword_score,
                    section_score=breakdown.section_score,
                    priority_score=breakdown.priority_score,
                    snippets=build_memory_snippets(record, terms),
                ),
            )
    scored.sort(key=lambda hit: hit.score, reverse=True)
    return scored[:top_k]


def is_reliable_memory_hit(hit: PaperMemoryHit, question: str) -> bool:
    if hit.score < MIN_RELIABLE_MEMORY_SCORE:
        return False
    terms = memory_query_terms(question)
    if not terms:
        return False
    direct_text = " ".join(
        [
            str(hit.memory.get("title", "")),
            *[reference.get("text", "") for reference in memory_evidence_refs(hit.memory)],
        ],
    )
    direct_match = score_term_overlap(direct_text, terms, weight=0.1, max_score=1.0)
    return bool(direct_match.matched_terms)


def score_memory_record(record: dict[str, Any], terms: set[str], question: str) -> PaperMemoryScore:
    title = str(record.get("title", ""))
    text = str(record.get("memory_text", ""))
    keywords = normalize_terms(safe_json_list(record.get("keywords_json", "[]")))
    title_overlap = score_term_overlap(title, terms, weight=0.42, max_score=1.6)
    keyword_overlap = score_term_overlap(" ".join(sorted(keywords)), terms, weight=0.36, max_score=1.4)
    section_overlap = score_term_overlap(text, terms, weight=0.08, max_score=1.4)
    intent_overlap = score_field_intents(record, terms, question)
    normalized_question = normalize_space(question)
    if len(normalized_question) >= 12:
        section_overlap.score = round(
            min(
                1.7,
                section_overlap.score
                + score_term_overlap(text, {normalized_question}, weight=0.3, max_score=0.3).score,
            ),
            4,
        )
    section_score = round(min(2.2, section_overlap.score + intent_overlap), 4)
    evidence_score = title_overlap.score + keyword_overlap.score + section_score
    return PaperMemoryScore(
        title_score=title_overlap.score,
        keyword_score=keyword_overlap.score,
        section_score=section_score,
        priority_score=0.15 if evidence_score > 0 and int(record.get("self_read_priority") or 0) == 1 else 0.0,
    )


def score_field_intents(record: dict[str, Any], terms: set[str], question: str) -> float:
    intents = detect_memory_intents(question)
    if not intents:
        return 0.0
    score = 0.0
    for intent in intents:
        config = FIELD_INTENTS[intent]
        field_text = " ".join(memory_field_text(record, field) for field in config["fields"])
        if not normalize_space(field_text):
            continue
        intent_terms = set(terms) | set(config["terms"])
        overlap = score_term_overlap(field_text, intent_terms, weight=0.16, max_score=0.9)
        presence_bonus = 0.18 if field_text else 0.0
        score += min(1.0, overlap.score + presence_bonus)
    return round(min(score, 1.4), 4)


def detect_memory_intents(question: str) -> list[str]:
    normalized = normalize_space(question).lower()
    intents: list[str] = []
    for intent, config in FIELD_INTENTS.items():
        if any(trigger in normalized for trigger in config["triggers"]):
            intents.append(intent)
    return intents


def memory_field_text(record: dict[str, Any], field: str) -> str:
    if field != "research_sight_json":
        return normalize_space(record.get(field, ""))
    sight = safe_json_dict(record.get("research_sight_json", "{}"))
    return normalize_space(
        " ".join(
            [
                sight.get("why_not_good", ""),
                sight.get("better_angle", ""),
                sight.get("baseline_comparison", ""),
                sight.get("next_step_proposal", ""),
            ],
        ),
    )


def build_memory_snippets(record: dict[str, Any], terms: set[str]) -> list[str]:
    snippets: list[str] = []
    for reference in memory_evidence_refs(record):
        text = normalize_space(reference.get("text", ""))
        if terms and not score_term_overlap(text, terms, weight=0.1, max_score=1.0).matched_terms:
            continue
        snippets.append(f"[{reference.get('id', 'source')}|{reference.get('source', 'unknown')}] {text[:260]}")
        if len(snippets) >= 3:
            break
    if not snippets:
        title = normalize_space(record.get("title", ""))
        if title:
            snippets.append(f"[title|metadata.title] {title[:260]}")
    return snippets


def build_memory_synthesis(
    question: str,
    hits: list[PaperMemoryHit],
    reliability_status: str,
    missing_terms: list[str] | None = None,
) -> tuple[str, list[MemoryClaim], list[str]]:
    if not hits:
        if reliability_status == "no_memory":
            return "当前项目还没有可用于回答的论文记忆。", [], ["先完成方向精读并生成 Paper Card。"]
        missing = f"；未覆盖：{', '.join((missing_terms or [])[:5])}" if missing_terms else ""
        return (
            f"当前记忆没有达到可靠证据门槛的命中{missing}。",
            [],
            ["补充与问题直接相关的全文证据，或用任务、数据集、指标和失败模式重新表述问题。"],
        )

    terms = memory_query_terms(question)
    selected: list[tuple[PaperMemoryHit, dict[str, str]]] = []
    coverage: dict[str, set[str]] = {}
    for hit in hits[:5]:
        reference = best_memory_evidence_ref(hit.memory, question)
        if reference is None:
            continue
        paper_id = normalize_space(hit.memory.get("paper_id", "")) or normalize_space(hit.memory.get("id", ""))
        selected.append((hit, reference))
        matched = score_term_overlap(reference.get("text", ""), terms, weight=0.1, max_score=1.0).matched_terms
        for term in matched:
            coverage.setdefault(term, set()).add(paper_id)

    shared_terms = [
        term
        for term, paper_ids in sorted(coverage.items(), key=lambda item: (-len(item[1]), item[0]))
        if len(paper_ids) >= 2
    ]
    full_text_card_count = sum(1 for hit, _ in selected if memory_evidence_quality(hit.memory) == "full_text")
    selected_pdf_count = sum(1 for _, reference in selected if reference.get("source") == "pdf.full_text")
    if shared_terms:
        answer_summary = (
            f"现有可靠证据中，{len(selected)} 篇论文的原文共同覆盖 "
            f"`{', '.join(shared_terms[:3])}`；{selected_pdf_count} 条回答证据直接来自 PDF 全文，"
            f"{full_text_card_count} 篇 Paper Card 整体达到全文级。"
            "这支持“这些主题在多篇文献中被直接讨论”，但不自动证明论文结论一致或已经形成方向级共识。"
        )
    else:
        answer_summary = (
            f"当前找到 {len(selected)} 篇可靠命中；{selected_pdf_count} 条回答证据直接来自 PDF 全文，"
            f"{full_text_card_count} 篇 Paper Card 整体达到全文级；"
            "证据可以定位与问题直接相关的单篇陈述，但尚未形成可跨论文复核的一致结论。"
        )

    claims: list[MemoryClaim] = []
    for index, (hit, reference) in enumerate(selected[:3], start=1):
        paper_id = normalize_space(hit.memory.get("paper_id", "")) or normalize_space(hit.memory.get("id", ""))
        quality = "full_text" if reference.get("source") == "pdf.full_text" else "abstract_only"
        confidence = normalize_memory_claim_confidence(quality, reference.get("confidence", "low"))
        evidence_ref = {
            "paper_id": paper_id,
            "paper_title": normalize_space(hit.memory.get("title", "")) or "Untitled",
            "snippet_id": reference.get("id", "source"),
            "source": reference.get("source", "unknown"),
            "section": reference.get("section", ""),
            "page": reference.get("page", ""),
            "text": reference.get("text", ""),
            "confidence": confidence,
        }
        claims.append(
            MemoryClaim(
                id=f"memory-claim-{index}",
                statement=f"{evidence_ref['paper_title']}：{reference.get('text', '')}",
                support_status="single_source",
                confidence=confidence,
                paper_ids=[paper_id],
                evidence_refs=[evidence_ref],
            ),
        )

    unanswered_parts: list[str] = []
    if missing_terms:
        unanswered_parts.append(f"原文证据尚未覆盖：{', '.join(missing_terms[:5])}。")
    if len(selected) < 2:
        unanswered_parts.append("缺少第二篇独立论文，不能判断该观察是否可复现或具有方向代表性。")
    if selected_pdf_count < len(selected):
        unanswered_parts.append("部分命中仅有摘要证据，方法、实验设置和失败边界仍需回到 PDF 核验。")
    if not shared_terms and len(selected) >= 2:
        unanswered_parts.append("多篇命中的原文没有形成共同问题词项，不能把它们合并为统一结论。")
    return answer_summary, claims, list(dict.fromkeys(unanswered_parts))


def normalize_memory_claim_confidence(evidence_quality: str, source_confidence: str) -> str:
    confidence = normalize_space(source_confidence).lower()
    if evidence_quality != "full_text":
        return "low"
    if confidence == "high":
        return "high"
    if confidence == "medium":
        return "medium"
    return "low"


def render_memory_synthesis_text(
    answer_summary: str,
    claims: list[MemoryClaim],
    unanswered_parts: list[str],
) -> str:
    claim_lines = [
        (
            f"- [{claim.id}; confidence={claim.confidence}; paper_id={','.join(claim.paper_ids)}] "
            f"{claim.statement}"
        )
        for claim in claims
    ]
    unanswered_lines = [f"- {item}" for item in unanswered_parts]
    parts = [answer_summary]
    if claim_lines:
        parts.append("可追溯证据：\n" + "\n".join(claim_lines))
    if unanswered_lines:
        parts.append("仍未回答：\n" + "\n".join(unanswered_lines))
    return "\n".join(parts)


def build_memory_answer(
    question: str,
    hits: list[PaperMemoryHit],
    snapshot: DirectionMemorySnapshot | None,
    reliability_status: str = "reliable",
    missing_terms: list[str] | None = None,
) -> str:
    if not hits:
        if reliability_status == "no_reliable_hit":
            missing_note = f" 当前缺失主题词：{', '.join((missing_terms or [])[:5])}。" if missing_terms else ""
            return (
                "当前记忆没有可靠证据回答此问题。系统没有把零分或弱相关论文当作可靠命中。"
                f"{missing_note}"
                "请先用更具体的任务对象、失败模式、数据集或指标改写问题并重新检索，"
                "或上传相关 PDF 以补齐 claim、dataset、metric、baseline 与原文片段。"
            )
        return (
            "当前项目的 Paper Memory Bank 还没有可用命中。请先执行方向精读，让系统至少读取一轮 10 篇论文，"
            "再用该问题检索记忆。"
        )

    direction_prefix = f"方向 `{snapshot.direction}`；" if snapshot else ""
    evidence_lines: list[str] = []
    for hit in hits[:3]:
        paper_id = normalize_space(hit.memory.get("paper_id", "")) or normalize_space(hit.memory.get("id", ""))
        quality = memory_evidence_quality(hit.memory)
        reference = best_memory_evidence_ref(hit.memory, question)
        if reference is None:
            continue
        evidence_lines.append(
            f"[paper_id={paper_id}; evidence_quality={quality}; snippet={reference.get('id', 'source')}] "
            f"{hit.memory.get('title', 'Untitled')}: {reference.get('text', '')}"
        )
    if not evidence_lines:
        return "当前命中分数达到阈值，但没有 title/abstract/full_text 原文片段可用于回答；请补充 PDF 后重试。"
    return (
        f"{direction_prefix}问题 `{question}` 命中 {len(hits)} 篇具有原文证据的 paper memory。"
        "当前只返回可追溯证据摘要，不把多篇摘要自动拼成方向级定论：\n"
        + "\n".join(f"- {line}" for line in evidence_lines)
        + "\n需要形成综合结论时，应逐条回到以上 paper_id 对应原文核对；abstract_only 不等同于全文结论。"
    )


def memory_query_terms(question: str) -> set[str]:
    intent = build_query_intent(question)
    return set(extract_terms(question, limit=16)) | set(intent.core_terms) | set(intent.direction_specific_terms)


def memory_evidence_refs(record: dict[str, Any]) -> list[dict[str, str]]:
    sight = safe_json_dict(record.get("research_sight_json", "{}"))
    pack = sight.get("evidence_pack") if isinstance(sight.get("evidence_pack"), dict) else {}
    raw_snippets = pack.get("snippets") if isinstance(pack.get("snippets"), list) else []
    references: list[dict[str, str]] = []
    for snippet in raw_snippets:
        if not isinstance(snippet, dict):
            continue
        source = normalize_space(snippet.get("source", ""))
        text = normalize_space(snippet.get("text", ""))
        if source not in {"metadata.abstract", "pdf.full_text"} or not text:
            continue
        references.append(
            {
                "id": normalize_space(snippet.get("id", "source")) or "source",
                "source": source,
                "text": text,
                "confidence": normalize_space(snippet.get("confidence", "low")) or "low",
                "section": normalize_space(snippet.get("section", "")),
                "page": normalize_space(snippet.get("page", "")),
            },
        )
    if references:
        return references
    title = normalize_space(record.get("title", ""))
    return [
        {
            "id": "title",
            "source": "metadata.title",
            "text": title,
            "confidence": "low",
            "section": "title",
            "page": "",
        },
    ] if title else []


def memory_evidence_quality(record: dict[str, Any]) -> str:
    sight = safe_json_dict(record.get("research_sight_json", "{}"))
    pack = sight.get("evidence_pack") if isinstance(sight.get("evidence_pack"), dict) else {}
    level = normalize_space(pack.get("evidence_level", "")).lower().replace("-", "_")
    if level in {"metadata_only", "abstract_only", "full_text"}:
        return level
    sources = {reference.get("source") for reference in memory_evidence_refs(record)}
    if "pdf.full_text" in sources:
        return "full_text"
    if "metadata.abstract" in sources:
        return "abstract_only"
    return "metadata_only"


def best_memory_evidence_ref(record: dict[str, Any], question: str) -> dict[str, str] | None:
    references = memory_evidence_refs(record)
    if not references:
        return None
    terms = memory_query_terms(question)
    mechanism_question = any(
        marker in question.lower()
        for marker in ["why", "how", "cause", "mechanism", "failure", "原因", "机制", "为何", "为什么", "导致", "失败"]
    )
    mechanism_markers = [
        "because",
        "due to",
        "caused by",
        "results from",
        "failure",
        "fails",
        "misalignment",
        "conflict",
        "shortcut",
        "bias",
        "原因",
        "机制",
        "导致",
        "由于",
        "失败",
    ]
    confidence_rank = {"high": 2, "medium": 1, "low": 0}

    def reference_rank(reference: dict[str, str]) -> tuple[int, int, int, int]:
        overlap = score_term_overlap(reference.get("text", ""), terms, weight=0.1, max_score=1.0)
        text = reference.get("text", "").lower()
        mechanism_score = sum(1 for marker in mechanism_markers if mechanism_question and marker in text)
        source_score = 1 if reference.get("source") == "pdf.full_text" else 0
        semantic_score = len(overlap.matched_terms) * 3 + mechanism_score * 2 + source_score
        return (
            1 if overlap.matched_terms else 0,
            semantic_score,
            source_score,
            confidence_rank.get(reference.get("confidence", "low"), 0),
        )

    return max(references, key=reference_rank)


def missing_memory_query_terms(records: list[dict[str, Any]], question: str) -> list[str]:
    terms = memory_query_terms(question)
    evidence_text = " ".join(
        reference.get("text", "")
        for record in records
        for reference in memory_evidence_refs(record)
    ).lower()
    missing = [term for term in terms if term and term not in evidence_text]
    return sorted(missing, key=lambda term: (-len(term), term))[:8]


def render_research_memory_answer_markdown(answer: ResearchMemoryAnswer) -> str:
    rows = [
        "| Rank | Paper | Score | Breakdown | Round | Snippet |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for index, hit in enumerate(answer.hits, start=1):
        memory = hit.memory
        rows.append(
            " | ".join(
                [
                    f"| {index}",
                    escape_table(memory.get("title", "")),
                    f"{hit.score:.2f}",
                    escape_table(
                        f"title={hit.title_score:.2f}, keyword={hit.keyword_score:.2f}, "
                        f"section={hit.section_score:.2f}, priority={hit.priority_score:.2f}",
                    ),
                    str(memory.get("round_index", "")),
                    escape_table(hit.snippets[0] if hit.snippets else ""),
                ],
            )
            + " |",
        )
    direction = answer.direction_memory.summary if answer.direction_memory else "No direction memory snapshot."
    return "\n\n".join(
        [
            "# Research Memory Answer",
            f"Question: {answer.question}",
            f"Top K: {answer.top_k}",
            f"Reliability: {answer.reliability_status}",
            f"Reliability reason: {answer.reliability_reason}",
            "## Direction Memory",
            direction,
            "## Answer",
            answer.answer,
            "## Structured Claims",
            "\n".join(
                f"- [{claim.id}; {claim.support_status}; {claim.confidence}] {claim.statement}"
                for claim in answer.claims
            )
            or "- none",
            "## Unanswered Parts",
            "\n".join(f"- {item}" for item in answer.unanswered_parts) or "- none",
            "## Retrieved Paper Memories",
            "\n".join(rows),
        ],
    )


def backfill_project_research_memory(connection, project_id: str, now: str) -> int:
    round_directions = fetch_direction_by_round(connection, project_id)
    rows = connection.execute(
        """
        SELECT * FROM artifacts
        WHERE project_id = ? AND title LIKE 'direction_round_%_paper_card_%'
        ORDER BY created_at ASC
        """,
        (project_id,),
    ).fetchall()
    count = 0
    touched_directions: set[str] = set()
    for row in rows:
        artifact = dict(row)
        round_index = parse_round_index(artifact.get("title", ""))
        direction = round_directions.get(round_index, "")
        if not direction:
            continue
        try:
            payload = json.loads(artifact.get("content_json") or "{}")
        except json.JSONDecodeError:
            continue
        paper = payload.get("paper") or {}
        if not is_relevant_memory_paper(paper):
            continue
        card = payload.get("card") or {}
        memory_payload = build_memory_payload(
            project_id=project_id,
            direction=direction,
            round_index=round_index,
            paper=paper,
            abstract_translation=payload.get("abstract_translation", ""),
            sections=payload.get("sections") or card.get("sections", []),
            weakest_assumption=payload.get("weakest_assumption") or card.get("weakest_assumption", ""),
            minimal_reproduction=payload.get("minimal_reproduction") or card.get("minimal_reproduction", ""),
            counterexample=payload.get("counterexample") or card.get("counterexample", ""),
            follow_up_idea=payload.get("follow_up_idea") or card.get("follow_up_idea", ""),
            why_selected=payload.get("why_selected", ""),
            self_read_priority=bool(payload.get("self_read_priority", False)),
            now=now,
            research_sight=payload.get("research_sight", {}),
        )
        upsert_paper_memory_payload(connection, memory_payload)
        touched_directions.add(direction)
        count += 1
    for direction in touched_directions:
        upsert_direction_memory_snapshot(connection, project_id, direction, now)
    return count


def is_relevant_memory_paper(paper: dict[str, Any]) -> bool:
    quality = normalize_space(paper.get("relevance_quality", "")).lower()
    if quality in {"strong", "medium"}:
        return True
    if quality in {"weak", "off_topic"}:
        return False
    priority = normalize_space(paper.get("priority", ""))
    return priority in {"High", "Medium"}


def fetch_direction_by_round(connection, project_id: str) -> dict[int, str]:
    rows = connection.execute(
        """
        SELECT title, content_json FROM artifacts
        WHERE project_id = ? AND title LIKE 'direction_review_round_%'
        ORDER BY created_at ASC
        """,
        (project_id,),
    ).fetchall()
    mapping: dict[int, str] = {}
    for row in rows:
        artifact = dict(row)
        round_index = parse_round_index(artifact.get("title", ""))
        try:
            payload = json.loads(artifact.get("content_json") or "{}")
        except json.JSONDecodeError:
            continue
        direction = normalize_space(payload.get("direction", ""))
        if direction:
            mapping[round_index] = direction
    return mapping


def parse_round_index(title: str) -> int:
    match = re.search(r"round_(\d+)", title)
    return int(match.group(1)) if match else 0


def extract_memory_keywords(text: str, limit: int = 18) -> list[str]:
    return extract_terms(text, limit=limit)


def build_memory_id(project_id: str, paper_id: str, title: str, direction: str) -> str:
    digest = hashlib.sha1(f"{project_id}:{paper_id}:{title}:{direction}".lower().encode("utf-8")).hexdigest()[:16]
    return f"memory_{digest}"


def build_direction_memory_id(project_id: str, direction: str) -> str:
    digest = hashlib.sha1(f"{project_id}:{direction}".lower().encode("utf-8")).hexdigest()[:16]
    return f"direction_memory_{digest}"


def safe_json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def safe_json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def memory_record_to_paper(memory: dict[str, Any], score: float = 0.0) -> dict[str, Any]:
    self_read_priority = bool(int(memory.get("self_read_priority") or 0))
    return {
        "id": memory.get("paper_id") or memory.get("id", ""),
        "project_id": memory.get("project_id", ""),
        "title": memory.get("title", ""),
        "authors": memory.get("authors", ""),
        "abstract": "",
        "year": memory.get("year", ""),
        "type": "memory",
        "venue": memory.get("venue", ""),
        "source": memory.get("source", ""),
        "url": memory.get("url", ""),
        "relation": memory.get("why_selected", ""),
        "priority": "High" if self_read_priority else "Medium",
        "code": "unknown",
        "relevance_score": float(score),
        "created_at": memory.get("created_at", ""),
    }


def extract_sight_focus(records: list[dict[str, Any]]) -> str:
    critiques: list[str] = []
    angles: list[str] = []
    for record in records:
        sight = safe_json_dict(record.get("research_sight_json", "{}"))
        if sight.get("why_not_good"):
            critiques.append(normalize_space(sight["why_not_good"]))
        if sight.get("better_angle"):
            angles.append(normalize_space(sight["better_angle"]))
    critique = first_nonempty(critiques)
    angle = first_nonempty(angles)
    if critique and angle:
        return f"主要批判：{critique[:180]}；破局角度：{angle[:180]}"
    return critique[:220] or angle[:220]


def build_baseline_memory_note(baseline_map: dict[str, Any]) -> str:
    if not baseline_map:
        return "暂无 BaselineMap。"
    recent = baseline_map.get("recent_strong_baselines") or []
    alternatives = baseline_map.get("alternative_paradigms") or []
    recent_titles = [item.get("title", "") for item in recent if isinstance(item, dict)][:2]
    alternative_titles = [item.get("title", "") for item in alternatives if isinstance(item, dict)][:2]
    pieces: list[str] = []
    if recent_titles:
        pieces.append(f"近三年强参照：{'; '.join(recent_titles)}")
    if alternative_titles:
        pieces.append(f"异质范式：{'; '.join(alternative_titles)}")
    return "；".join(pieces) if pieces else "BaselineMap 已保存但候选参照不足。"


def first_research_sight_value(hits: list[PaperMemoryHit], key: str) -> str:
    for hit in hits:
        sight = safe_json_dict(hit.memory.get("research_sight_json", "{}"))
        value = normalize_space(sight.get(key, ""))
        if value:
            return value
    return ""


def first_nonempty(values) -> str:
    for value in values:
        normalized = normalize_space(value)
        if normalized:
            return normalized
    return ""


def escape_table(value: str) -> str:
    return normalize_space(value).replace("|", "\\|")
