from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


ARXIV_API_URL = "https://export.arxiv.org/api/query"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
DEFAULT_TIMEOUT_SECONDS = 20


@dataclass
class PaperCandidate:
    title: str
    year: str
    authors: str
    abstract: str
    type: str
    venue: str
    source: str
    url: str
    relation: str
    priority: str
    code: str = "unknown"
    relevance_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LiteratureSearchResult:
    query: str
    expanded_queries: list[str]
    papers: list[PaperCandidate]
    errors: list[str]


def search_literature(query: str, max_results: int = 12, sources: list[str] | None = None) -> LiteratureSearchResult:
    selected_sources = sources or ["arxiv", "openalex"]
    expanded_queries = expand_queries(query)
    per_query_limit = max(3, min(10, max_results))
    candidates: list[PaperCandidate] = []
    errors: list[str] = []

    for expanded_query in expanded_queries:
        if "arxiv" in selected_sources:
            try:
                candidates.extend(search_arxiv(expanded_query, per_query_limit))
            except Exception as error:  # noqa: BLE001 - preserve API failure detail for timeline/debugging.
                errors.append(f"arxiv:{expanded_query}: {error}")
        if "openalex" in selected_sources:
            try:
                candidates.extend(search_openalex(expanded_query, per_query_limit))
            except Exception as error:  # noqa: BLE001
                errors.append(f"openalex:{expanded_query}: {error}")

    ranked = rank_and_deduplicate(candidates, query)
    return LiteratureSearchResult(
        query=query,
        expanded_queries=expanded_queries,
        papers=ranked[:max_results],
        errors=errors,
    )


def expand_queries(query: str) -> list[str]:
    normalized = normalize_space(query)
    expansions = [normalized]
    lower = normalized.lower()

    if "vlm" in lower or "vision language" in lower or "multimodal" in lower or "多模态" in lower:
        expansions.extend(
            [
                f"{normalized} vision language model",
                f"{normalized} multimodal evaluation",
            ],
        )
    if "hallucination" in lower or "幻觉" in lower:
        expansions.extend(
            [
                f"{normalized} object hallucination",
                f"{normalized} visual grounding",
            ],
        )
    if "agent" in lower or "workflow" in lower or "科研" in lower:
        expansions.extend(
            [
                f"{normalized} research agent",
                f"{normalized} scientific discovery workflow",
            ],
        )

    return unique_preserve_order([item for item in expansions if item])


def search_arxiv(query: str, max_results: int) -> list[PaperCandidate]:
    params = {
        "search_query": build_arxiv_query(query),
        "start": "0",
        "max_results": str(max_results),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    response = request_text(f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}")
    root = ET.fromstring(response)
    namespace = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    papers: list[PaperCandidate] = []

    for entry in root.findall("atom:entry", namespace):
        title = normalize_space(find_text(entry, "atom:title", namespace))
        abstract = normalize_space(find_text(entry, "atom:summary", namespace))
        published = find_text(entry, "atom:published", namespace)
        year = published[:4] if published else ""
        authors = ", ".join(
            normalize_space(author.findtext("atom:name", default="", namespaces=namespace))
            for author in entry.findall("atom:author", namespace)
        )
        url = ""
        for link in entry.findall("atom:link", namespace):
            if link.attrib.get("rel") == "alternate":
                url = link.attrib.get("href", "")
                break
        primary_category = entry.find("arxiv:primary_category", namespace)
        category = primary_category.attrib.get("term", "") if primary_category is not None else ""
        papers.append(
            PaperCandidate(
                title=title,
                year=year,
                authors=authors,
                abstract=abstract,
                type="Preprint",
                venue=f"arXiv {category}".strip(),
                source="arxiv",
                url=url,
                relation="待排序：由 ScholarFlow 根据关键词相关性计算。",
                priority="Medium",
            ),
        )

    return papers


def build_arxiv_query(query: str) -> str:
    terms = [term for term in re.split(r"\s+", query.strip()) if term]
    if len(terms) <= 1:
        return f"all:{query}"
    return " AND ".join(f"all:{term}" for term in terms[:8])


def search_openalex(query: str, max_results: int) -> list[PaperCandidate]:
    params = {
        "search": query,
        "per-page": str(max_results),
        "select": ",".join(
            [
                "id",
                "doi",
                "display_name",
                "publication_year",
                "authorships",
                "abstract_inverted_index",
                "primary_location",
                "type",
                "cited_by_count",
            ],
        ),
    }
    email = os.getenv("OPENALEX_EMAIL") or os.getenv("CROSSREF_MAILTO")
    api_key = os.getenv("OPENALEX_API_KEY")
    if email:
        params["mailto"] = email
    if api_key:
        params["api_key"] = api_key

    payload = json.loads(request_text(f"{OPENALEX_WORKS_URL}?{urllib.parse.urlencode(params)}"))
    papers: list[PaperCandidate] = []
    for work in payload.get("results", []):
        title = normalize_space(work.get("display_name") or "")
        if not title:
            continue

        primary_location = work.get("primary_location") or {}
        source = primary_location.get("source") or {}
        url = primary_location.get("landing_page_url") or work.get("doi") or work.get("id") or ""
        authors = ", ".join(extract_openalex_authors(work.get("authorships") or []))
        abstract = reconstruct_openalex_abstract(work.get("abstract_inverted_index") or {})
        papers.append(
            PaperCandidate(
                title=title,
                year=str(work.get("publication_year") or ""),
                authors=authors,
                abstract=abstract,
                type=normalize_space(work.get("type") or "work"),
                venue=normalize_space(source.get("display_name") or "OpenAlex"),
                source="openalex",
                url=url,
                relation="待排序：由 ScholarFlow 根据关键词相关性计算。",
                priority="Medium",
                relevance_score=min(float(work.get("cited_by_count") or 0) / 3000.0, 0.35),
            ),
        )
    return papers


def extract_openalex_authors(authorships: list[dict[str, Any]]) -> list[str]:
    authors: list[str] = []
    for authorship in authorships[:8]:
        author = authorship.get("author") or {}
        display_name = normalize_space(author.get("display_name") or "")
        if display_name:
            authors.append(display_name)
    return authors


def reconstruct_openalex_abstract(index: dict[str, list[int]]) -> str:
    if not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in index.items():
        for position in indexes:
            positions.append((position, word))
    return " ".join(word for _, word in sorted(positions))


def request_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, application/atom+xml, text/xml",
            "User-Agent": "ScholarFlow/0.1 (local research workflow agent)",
        },
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


def rank_and_deduplicate(candidates: list[PaperCandidate], query: str) -> list[PaperCandidate]:
    deduped: dict[str, PaperCandidate] = {}
    for candidate in candidates:
        key = normalize_title_key(candidate.title)
        existing = deduped.get(key)
        if existing is None or source_rank(candidate.source) > source_rank(existing.source):
            deduped[key] = candidate

    query_terms = significant_terms(query)
    ranked: list[PaperCandidate] = []
    for candidate in deduped.values():
        score, reason = score_candidate(candidate, query_terms)
        candidate.relevance_score = round(score, 4)
        candidate.priority = priority_from_score(score)
        candidate.relation = reason
        ranked.append(candidate)

    return sorted(ranked, key=lambda paper: paper.relevance_score, reverse=True)


def score_candidate(candidate: PaperCandidate, query_terms: set[str]) -> tuple[float, str]:
    haystack = f"{candidate.title} {candidate.abstract} {candidate.venue}".lower()
    matched_terms = sorted(term for term in query_terms if term in haystack)
    current_year = datetime.now(timezone.utc).year
    year = int(candidate.year) if candidate.year.isdigit() else current_year - 8
    recency_score = max(0.0, 1.0 - min(max(current_year - year, 0), 8) / 8)
    source_score = 0.25 if candidate.source == "arxiv" else 0.18
    title_bonus = sum(0.2 for term in query_terms if term in candidate.title.lower())
    match_score = len(matched_terms) / max(len(query_terms), 1)
    score = match_score + recency_score * 0.35 + source_score + title_bonus + candidate.relevance_score

    if matched_terms:
        reason = f"匹配关键词：{', '.join(matched_terms[:6])}；年份 {candidate.year or 'unknown'}；来源 {candidate.source}。"
    else:
        reason = f"弱匹配：由 {candidate.source} 返回，年份 {candidate.year or 'unknown'}，需要人工复核。"
    return score, reason


def priority_from_score(score: float) -> str:
    if score >= 1.35:
        return "High"
    if score >= 0.75:
        return "Medium"
    return "Watch"


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
        "方向",
        "论文",
        "科研",
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


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def source_rank(source: str) -> int:
    return {"arxiv": 3, "openalex": 2}.get(source, 1)


def find_text(element: ET.Element, path: str, namespace: dict[str, str]) -> str:
    found = element.find(path, namespace)
    return found.text if found is not None and found.text is not None else ""


def render_paper_table_markdown(result: LiteratureSearchResult) -> str:
    rows = [
        "| Paper | Year | Authors | Venue | Source | Priority | Relation | URL |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for paper in result.papers:
        rows.append(
            " | ".join(
                [
                    f"| {escape_table(paper.title)}",
                    escape_table(paper.year),
                    escape_table(truncate(paper.authors, 80)),
                    escape_table(paper.venue),
                    escape_table(paper.source),
                    escape_table(paper.priority),
                    escape_table(paper.relation),
                    escape_table(paper.url),
                ],
            )
            + " |",
        )

    errors = "\n".join(f"- {error}" for error in result.errors) if result.errors else "- none"
    return "\n\n".join(
        [
            "# Paper Table",
            f"Query: {result.query}",
            "## Expanded Queries",
            "\n".join(f"- {query}" for query in result.expanded_queries),
            "## Ranked Papers",
            "\n".join(rows),
            "## Retrieval Notes",
            errors,
        ],
    )


def render_paper_table_json(result: LiteratureSearchResult) -> str:
    return json.dumps(
        {
            "query": result.query,
            "expanded_queries": result.expanded_queries,
            "papers": [paper.to_dict() for paper in result.papers],
            "errors": result.errors,
        },
        ensure_ascii=False,
        indent=2,
    )


def escape_table(value: str) -> str:
    return normalize_space(value).replace("|", "\\|")


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."
