from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from scholarflow_api.text_utils import extract_terms, normalize_space, normalize_terms, score_term_overlap


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
        return {
            "memory": self.memory,
            "score": self.score,
            "title_score": self.title_score,
            "keyword_score": self.keyword_score,
            "section_score": self.section_score,
            "priority_score": self.priority_score,
            "snippets": self.snippets,
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
class ResearchMemoryAnswer:
    question: str
    top_k: int
    answer: str
    hits: list[PaperMemoryHit]
    direction_memory: DirectionMemorySnapshot | None
    total_memories: int
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "top_k": self.top_k,
            "answer": self.answer,
            "hits": [hit.to_dict() for hit in self.hits],
            "direction_memory": self.direction_memory.to_dict() if self.direction_memory else None,
            "total_memories": self.total_memories,
            "warnings": self.warnings,
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
    sections = [section.to_dict() for section in reading.card.sections]
    return build_memory_payload(
        project_id=project_id,
        direction=direction,
        round_index=round_index,
        paper=paper,
        abstract_translation=reading.abstract_translation,
        sections=sections,
        weakest_assumption=reading.card.weakest_assumption,
        minimal_reproduction=reading.card.minimal_reproduction,
        counterexample=reading.card.counterexample,
        follow_up_idea=reading.card.follow_up_idea,
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
    hits = search_memory_records(records, question, top_k)
    snapshot = fetch_direction_memory_snapshot(connection, project_id, direction)
    warnings: list[str] = []
    if not records:
        warnings.append("当前项目还没有 paper memory。请先执行方向精读，或生成 paper cards。")
    if records and not hits:
        warnings.append("没有找到强相关论文，回答只能基于当前 memory bank 的弱匹配。")
        hits = search_memory_records(records, question, min(top_k, len(records)), allow_weak=True)

    return ResearchMemoryAnswer(
        question=question,
        top_k=top_k,
        answer=build_memory_answer(question, hits, snapshot),
        hits=hits,
        direction_memory=snapshot,
        total_memories=len(records),
        warnings=warnings,
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
    terms = set(extract_terms(question, limit=16))
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


def score_memory_record(record: dict[str, Any], terms: set[str], question: str) -> PaperMemoryScore:
    title = str(record.get("title", ""))
    text = str(record.get("memory_text", ""))
    keywords = normalize_terms(safe_json_list(record.get("keywords_json", "[]")))
    title_overlap = score_term_overlap(title, terms, weight=0.42, max_score=1.6)
    keyword_overlap = score_term_overlap(" ".join(sorted(keywords)), terms, weight=0.36, max_score=1.4)
    section_overlap = score_term_overlap(text, terms, weight=0.08, max_score=1.4)
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
    return PaperMemoryScore(
        title_score=title_overlap.score,
        keyword_score=keyword_overlap.score,
        section_score=section_overlap.score,
        priority_score=0.15 if int(record.get("self_read_priority") or 0) == 1 else 0.0,
    )


def build_memory_snippets(record: dict[str, Any], terms: set[str]) -> list[str]:
    text = normalize_space(record.get("memory_text", ""))
    sentences = re.split(r"(?<=[。！？.!?])\s+", text)
    snippets: list[str] = []
    for sentence in sentences:
        if terms and not score_term_overlap(sentence, terms, weight=0.1, max_score=1.0).matched_terms:
            continue
        snippets.append(sentence[:260])
        if len(snippets) >= 3:
            break
    if not snippets:
        fallback = record.get("why_selected") or record.get("abstract_translation") or record.get("weakest_assumption") or text
        snippets.append(normalize_space(fallback)[:260])
    return snippets


def build_memory_answer(
    question: str,
    hits: list[PaperMemoryHit],
    snapshot: DirectionMemorySnapshot | None,
) -> str:
    if not hits:
        return (
            "当前项目的 Paper Memory Bank 还没有可用命中。请先执行方向精读，让系统至少读取一轮 10 篇论文，"
            "再用该问题检索记忆。"
        )

    titles = [hit.memory.get("title", "") for hit in hits[:3]]
    weakest = first_nonempty(hit.memory.get("weakest_assumption", "") for hit in hits)
    minimal = first_nonempty(hit.memory.get("minimal_reproduction", "") for hit in hits)
    counterexample = first_nonempty(hit.memory.get("counterexample", "") for hit in hits)
    why_not_good = first_research_sight_value(hits, "why_not_good")
    better_angle = first_research_sight_value(hits, "better_angle")
    direction_prefix = f"在 `{snapshot.direction}` 的方向记忆中，" if snapshot else ""
    return (
        f"{direction_prefix}针对问题 `{question}`，ScholarFlow 从 Paper Memory Bank 中检索到 {len(hits)} 篇相关论文。"
        f"最相关的证据来自：{'; '.join(titles)}。"
        "综合这些论文，当前更可靠的回答方式是先看它们共同暴露的失败模式，而不是直接平均所有论文结论。"
        f" 关键脆弱点：{weakest or '当前命中没有明确记录最脆弱假设'}"
        f" 审美批判：{why_not_good or '当前命中没有明确 ResearchSight 批判字段'}"
        f" 更好角度：{better_angle or '当前命中没有明确 ResearchSight 破局视角'}"
        f" 可执行验证：{minimal or '当前命中没有明确记录最小复现实验'}"
        f" 反例方向：{counterexample or '当前命中没有明确记录反例设计'}"
        " 这份回答只基于已保存的 paper memory，不等同于全文证据；正式写作前仍应回到原论文核对。"
    )


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
            "## Direction Memory",
            direction,
            "## Answer",
            answer.answer,
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
        card = payload.get("card") or {}
        memory_payload = build_memory_payload(
            project_id=project_id,
            direction=direction,
            round_index=round_index,
            paper=paper,
            abstract_translation=payload.get("abstract_translation", ""),
            sections=card.get("sections", []),
            weakest_assumption=card.get("weakest_assumption", ""),
            minimal_reproduction=card.get("minimal_reproduction", ""),
            counterexample=card.get("counterexample", ""),
            follow_up_idea=card.get("follow_up_idea", ""),
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
