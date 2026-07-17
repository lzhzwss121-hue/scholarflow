from __future__ import annotations

import json
import os
import re
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from scholarflow_api.database import get_connection, new_id, utc_now
from scholarflow_api.text_utils import extract_terms, score_term_overlap

try:
    import certifi
except ImportError:  # pragma: no cover - requirements install certifi; keep fallback for system envs.
    certifi = None


ARXIV_API_URL = "https://export.arxiv.org/api/query"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("SCHOLARFLOW_REQUEST_TIMEOUT_SECONDS", "12"))
REQUEST_CACHE_TTL_SECONDS = int(os.getenv("SCHOLARFLOW_REQUEST_CACHE_TTL_SECONDS", "900"))
RETRIEVAL_CACHE_TTL_SECONDS = int(os.getenv("SCHOLARFLOW_RETRIEVAL_CACHE_TTL_SECONDS", "86400"))
LOW_RECALL_THRESHOLD = 5
TRANSIENT_HTTP_STATUS = {429, 500, 502, 503, 504}
REQUEST_CACHE: dict[str, tuple[float, str]] = {}
SSL_CONTEXT: ssl.SSLContext | None = None
SOURCE_FAILURE_THRESHOLD = 1
RELEVANCE_QUALITIES = {"strong", "medium", "weak", "off_topic"}
SUPPORT_ONLY_TERMS = {
    "assessment",
    "benchmark",
    "evaluating",
    "evaluation",
    "evidence",
    "metric",
}

DOMAIN_MISMATCH_PATTERNS: dict[str, list[str]] = {
    "education": [
        "classroom",
        "student",
        "teacher",
        "school",
        "pedagogy",
        "curriculum",
        "assessment and classroom learning",
    ],
    "clinical_meta": [
        "prisma",
        "systematic review",
        "meta-analysis",
        "clinical trial",
        "patients",
        "tuberculosis",
        "treatment outcomes",
    ],
    "medical_segmentation": [
        "brats",
        "brain tumor",
        "glioma",
        "mri",
        "medical image segmentation",
        "segmentation challenge",
    ],
    "medical_domain": [
        "medical hallucination",
        "medical large vision language model",
        "clinical",
        "patient",
        "radiology",
        "diagnosis",
        "healthcare",
        "biomedical",
        "medicine",
        "医学",
        "临床",
        "患者",
    ],
    "document_ocr": [
        "ocr",
        "optical character recognition",
        "document understanding",
        "document image",
        "text recognition",
        "scene text",
        "文档理解",
        "文字识别",
    ],
    "humanities_domain": [
        "ancient greek",
        "classical greek",
        "philology",
        "classics",
        "manuscript studies",
        "历史文献",
        "古希腊",
        "古典学",
    ],
}

DOMAIN_QUERY_ALLOWLIST: dict[str, list[str]] = {
    "education": ["education", "classroom", "school", "student", "teacher", "教育", "课堂", "教学"],
    "clinical_meta": ["clinical", "medical", "patient", "healthcare", "prisma", "systematic review", "医学", "临床"],
    "medical_segmentation": ["medical", "segmentation", "brats", "mri", "brain tumor", "医学", "分割", "肿瘤"],
    "medical_domain": ["medical", "clinical", "patient", "healthcare", "biomedical", "medicine", "医学", "临床", "患者"],
    "document_ocr": ["ocr", "document", "text recognition", "文档", "文字识别", "光学字符"],
    "humanities_domain": ["ancient greek", "classics", "philology", "古希腊", "古典学", "历史文献"],
}

OBJECT_HALLUCINATION_DIRECTION_MARKERS = {
    "object hallucination",
    "object hallucinations",
    "对象幻觉",
    "物体幻觉",
    "pope",
    "object probing",
}
OBJECT_HALLUCINATION_PRIMARY_PATTERNS = (
    "object hallucination",
    "object hallucinations",
    "visual object hallucination",
    "pope",
    "object probing",
    "object grounding",
    "grounded object",
)
OBJECT_HALLUCINATION_VISUAL_CONTEXT_PATTERNS = (
    "vision language",
    "vision-language",
    "large vision language",
    "vlm",
    "lvlm",
    "multimodal",
    "visual question",
    "vqa",
)
OBJECT_HALLUCINATION_EVALUATION_PATTERNS = (
    "evaluation",
    "benchmark",
    "assess",
    "detect",
    "measure",
    "probe",
)


@dataclass
class QueryIntent:
    query_text: str
    terms: set[str]
    core_terms: set[str]
    groups: dict[str, set[str]]
    core_groups: set[str]
    object_groups: set[str]
    problem_groups: set[str]
    support_groups: set[str]
    direction_specific_terms: set[str]


@dataclass
class CandidateRelevance:
    score: float
    reason: str
    quality: str
    matched_terms: list[str]
    review_required: bool


@dataclass
class RankedPaperSet:
    papers: list["PaperCandidate"]
    coverage: dict[str, int]


class SourceDegradedError(RuntimeError):
    def __init__(self, source: str, query: str, status: int | None, message: str) -> None:
        self.source = source
        self.query = query
        self.status = status
        super().__init__(f"{source}:{query}: degraded status={status or 'unknown'}: {message}")


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
    pdf_url: str = ""
    code: str = "unknown"
    relevance_score: float = 0.0
    relevance_quality: str = "medium"
    matched_terms: list[str] = field(default_factory=list)
    review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LiteratureSearchResult:
    query: str
    expanded_queries: list[str]
    papers: list[PaperCandidate]
    errors: list[str]
    relevance_coverage: dict[str, int] = field(default_factory=dict)


def search_literature(query: str, max_results: int = 12, sources: list[str] | None = None) -> LiteratureSearchResult:
    selected_sources = sources or ["arxiv", "openalex"]
    expanded_queries = expand_queries(query)
    per_query_limit = max(3, min(10, max_results))
    candidates: list[PaperCandidate] = []
    errors: list[str] = []
    source_failures: dict[str, int] = {}

    for expanded_query in expanded_queries:
        candidates.extend(search_sources_for_query(expanded_query, per_query_limit, selected_sources, errors, source_failures))

    ranked_result = rank_and_deduplicate_result(candidates, query)
    if len(ranked_result.papers) < LOW_RECALL_THRESHOLD:
        relaxed_queries = build_relaxed_queries(query, expanded_queries)
        for relaxed_query in relaxed_queries:
            errors.append(f"query_relaxed:{relaxed_query}: 初始检索召回不足，已自动放宽检索式。")
            candidates.extend(
                search_sources_for_query(
                    relaxed_query,
                    per_query_limit,
                    selected_sources,
                    errors,
                    source_failures,
                    relaxed=True,
                ),
            )
            ranked_result = rank_and_deduplicate_result(candidates, query)
            if len(ranked_result.papers) >= LOW_RECALL_THRESHOLD:
                break

    ranked_result = rank_and_deduplicate_result(candidates, query)
    eligible_count = len(ranked_result.papers)
    visible_papers = ranked_result.papers[:max_results]
    relevance_coverage = {
        **ranked_result.coverage,
        "eligible_count": eligible_count,
        "returned_count": len(visible_papers),
        "truncated_count": max(0, eligible_count - len(visible_papers)),
    }
    if has_relevance_filtering(relevance_coverage):
        errors.append(f"relevance_coverage:{format_relevance_coverage(relevance_coverage)}")
    if len(visible_papers) < LOW_RECALL_THRESHOLD:
        errors.append(
            f"low_recall: only {len(visible_papers)} strong/medium papers returned after query expansion and relaxation; "
            "results are partial and should not be treated as a complete direction survey.",
        )
    return LiteratureSearchResult(
        query=query,
        expanded_queries=expanded_queries,
        papers=visible_papers,
        errors=compact_retrieval_errors(errors),
        relevance_coverage=relevance_coverage,
    )


def search_sources_for_query(
    query: str,
    per_query_limit: int,
    selected_sources: list[str],
    errors: list[str],
    source_failures: dict[str, int] | None = None,
    relaxed: bool = False,
) -> list[PaperCandidate]:
    source_failures = source_failures if source_failures is not None else {}
    candidates: list[PaperCandidate] = []
    if "arxiv" in selected_sources:
        if should_skip_source("arxiv", source_failures):
            errors.append(f"arxiv_rate_limited:{query}: arXiv 已在本轮触发限流或临时失败，后续 query 暂停该 source。")
        else:
            source_errors: list[str] = []
            cached = get_cached_retrieval("arxiv", cache_query_key(query, relaxed), per_query_limit)
            if cached is not None:
                cached_papers, cached_errors = cached
                candidates.extend(cached_papers)
                errors.append(f"using_cached_results:arxiv:{query}: 使用 24 小时内 SQLite 检索缓存。")
                errors.extend(cached_errors)
            else:
                try:
                    papers = search_arxiv(query, per_query_limit, relaxed=relaxed)
                    candidates.extend(papers)
                    save_cached_retrieval("arxiv", cache_query_key(query, relaxed), per_query_limit, papers, source_errors)
                except SourceDegradedError as error:
                    record_source_failure(source_failures, error.source, error.status)
                    errors.append(format_source_degraded_error(error))
                except Exception as error:  # noqa: BLE001 - preserve API failure detail for timeline/debugging.
                    errors.append(f"arxiv:{query}: {error}")
    if "openalex" in selected_sources:
        if should_skip_source("openalex", source_failures):
            errors.append(f"openalex_cooldown:{query}: OpenAlex 已在本轮触发 429/503/504，后续 query 暂停该 source。")
        else:
            source_errors = []
            cached = get_cached_retrieval("openalex", query, per_query_limit)
            if cached is not None:
                cached_papers, cached_errors = cached
                candidates.extend(cached_papers)
                errors.append(f"using_cached_results:openalex:{query}: 使用 24 小时内 SQLite 检索缓存。")
                errors.extend(cached_errors)
            else:
                try:
                    papers = search_openalex(query, per_query_limit)
                    candidates.extend(papers)
                    save_cached_retrieval("openalex", query, per_query_limit, papers, source_errors)
                except SourceDegradedError as error:
                    record_source_failure(source_failures, error.source, error.status)
                    errors.append(format_source_degraded_error(error))
                except Exception as error:  # noqa: BLE001
                    errors.append(f"openalex:{query}: {error}")
    return candidates


def should_skip_source(source: str, source_failures: dict[str, int]) -> bool:
    return source_failures.get(source, 0) >= SOURCE_FAILURE_THRESHOLD


def record_source_failure(source_failures: dict[str, int], source: str, status: int | None) -> None:
    if status in {429, 503, 504}:
        source_failures[source] = source_failures.get(source, 0) + 1


def format_source_degraded_error(error: SourceDegradedError) -> str:
    if error.source == "openalex" and error.status in {429, 503, 504}:
        return f"openalex_cooldown:{error.query}: {error}"
    if error.source == "arxiv" and error.status == 429:
        return f"arxiv_rate_limited:{error.query}: {error}"
    return str(error)


def cache_query_key(query: str, relaxed: bool) -> str:
    return f"{query} :: relaxed={int(relaxed)}"


def get_cached_retrieval(
    source: str,
    query: str,
    max_results: int,
) -> tuple[list[PaperCandidate], list[str]] | None:
    if RETRIEVAL_CACHE_TTL_SECONDS <= 0:
        return None
    try:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT response_json, errors_json, created_at
                FROM retrieval_cache
                WHERE source = ? AND query = ? AND max_results = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (source, query, max_results),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    created_at = parse_iso_datetime(row["created_at"])
    if created_at is None:
        return None
    age = (datetime.now(timezone.utc) - created_at).total_seconds()
    if age > RETRIEVAL_CACHE_TTL_SECONDS:
        return None
    try:
        paper_payload = json.loads(row["response_json"] or "[]")
        errors_payload = json.loads(row["errors_json"] or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(paper_payload, list):
        return None
    papers = [PaperCandidate(**item) for item in paper_payload if isinstance(item, dict)]
    errors = [str(item) for item in errors_payload] if isinstance(errors_payload, list) else []
    return papers, errors


def save_cached_retrieval(
    source: str,
    query: str,
    max_results: int,
    papers: list[PaperCandidate],
    errors: list[str],
) -> None:
    if RETRIEVAL_CACHE_TTL_SECONDS <= 0:
        return
    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO retrieval_cache (
                    id, source, query, max_results, response_json, errors_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("retrieval_cache"),
                    source,
                    query,
                    max_results,
                    json.dumps([paper.to_dict() for paper in papers], ensure_ascii=False),
                    json.dumps(errors, ensure_ascii=False),
                    utc_now(),
                ),
            )
    except sqlite3.Error:
        return


def parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def expand_queries(query: str) -> list[str]:
    normalized = normalize_space(query)
    expansions = [normalized]
    lower = normalized.lower()
    expansions.extend(build_bilingual_intent_queries(normalized))

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
    if "图像修复" in lower:
        expansions.extend([f"{normalized} image restoration", "image restoration benchmark"])
    if "超分辨率" in lower:
        expansions.extend([f"{normalized} super resolution", "single image super resolution"])
    if "医学" in lower or "medical" in lower:
        expansions.extend([f"{normalized} medical image", f"{normalized} healthcare AI"])

    return unique_preserve_order([item for item in expansions if item])


def build_relaxed_queries(query: str, already_used: list[str]) -> list[str]:
    normalized = normalize_space(query)
    relaxed: list[str] = []
    relaxed.extend(build_bilingual_intent_queries(normalized))
    if contains_cjk(normalized):
        relaxed.extend(chinese_relaxation_queries(normalized))

    intent = build_query_intent(normalized)
    core_terms = sorted(term for term in intent.direction_specific_terms if not is_support_only_query(term))
    if not relaxed and len(core_terms) >= 2:
        relaxed.append(" ".join(core_terms[:3]))
    relaxed.extend(term for term in core_terms[:6] if is_safe_standalone_relaxed_query(term))

    used = {item.lower() for item in already_used}
    return [
        item
        for item in unique_preserve_order(relaxed)
        if item and item.lower() not in used and not is_support_only_query(item)
    ]


def chinese_relaxation_queries(query: str) -> list[str]:
    lower = query.lower()
    queries: list[str] = []
    if "图像修复" in lower:
        queries.extend(["image restoration", "blind image restoration"])
    if "幻觉" in lower:
        queries.extend(["hallucination benchmark", "object hallucination", "visual grounding"])
    if "多模态" in lower:
        queries.extend(["vision language model", "large vision language model", "LVLM hallucination"])
    if "视觉问答" in lower:
        queries.extend(["visual question answering", "VQA visual grounding"])
    if "证据" in lower or "忠实" in lower:
        queries.extend(["evidence faithfulness", "grounded evidence", "visual grounding faithfulness"])
    if ("多模态" in lower or "视觉问答" in lower) and ("证据" in lower or "忠实" in lower or "评估" in lower):
        queries.extend(
            [
                "POPE object hallucination",
                "object hallucination large vision language model",
                "faithful visual question answering grounded evidence",
            ],
        )
    return queries


def build_bilingual_intent_queries(query: str) -> list[str]:
    intent = build_query_intent(query)
    variants: list[str] = []
    has_vlm = "multimodal_vlm" in intent.object_groups
    has_vqa = "visual_question_answering" in intent.object_groups
    has_evidence = "evidence_faithfulness" in intent.problem_groups
    has_hallucination = "hallucination" in intent.problem_groups

    if has_vlm and has_vqa and (has_evidence or has_hallucination):
        variants.extend(
            [
                "object hallucination large vision language model",
                "POPE object hallucination",
                "LVLM hallucination benchmark",
                "vision language model hallucination benchmark",
                "visual question answering hallucination",
                "faithful visual question answering grounded evidence",
                "visual grounding VQA faithfulness",
                "evidence grounding visual question answering",
                "large vision language model visual grounding",
            ],
        )
    elif has_vlm and (has_evidence or has_hallucination):
        variants.extend(
            [
                "large vision language model hallucination",
                "object hallucination vision language model",
                "vision language model visual grounding",
                "evidence faithfulness vision language model",
            ],
        )
    elif has_vqa and has_evidence:
        variants.extend(
            [
                "faithful visual question answering grounded evidence",
                "visual grounding VQA faithfulness",
                "evidence grounding visual question answering",
            ],
        )
    elif has_hallucination:
        variants.extend(["object hallucination", "hallucination benchmark", "POPE object hallucination"])

    if "image_restoration" in intent.object_groups:
        variants.extend(["image restoration benchmark", "blind image restoration", "single image super resolution"])
    if "research_agent" in intent.object_groups:
        variants.extend(["research agent workflow", "scientific discovery workflow", "tool augmented agent"])

    return [variant for variant in unique_preserve_order(variants) if not is_support_only_query(variant)]


def is_support_only_query(query: str) -> bool:
    terms = {normalize_intent_term(term) for term in extract_terms(query, limit=16, include_domain_phrases=False)}
    if not terms:
        return False
    support_terms = SUPPORT_ONLY_TERMS | {"eval", "evaluate", "evaluates"}
    return all(term in support_terms for term in terms)


def is_safe_standalone_relaxed_query(query: str) -> bool:
    normalized = normalize_intent_term(query)
    if is_support_only_query(normalized):
        return False
    if " " in normalized:
        return True
    return normalized in {"hallucination", "faithfulness", "grounding", "pope", "vqa", "vlm", "lvlm", "mllm", "sisr"}


def search_arxiv(query: str, max_results: int, relaxed: bool = False) -> list[PaperCandidate]:
    params = {
        "search_query": build_arxiv_query(query, relaxed=relaxed),
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
        pdf_url = ""
        for link in entry.findall("atom:link", namespace):
            if link.attrib.get("rel") == "alternate":
                url = link.attrib.get("href", "")
            if link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
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
                pdf_url=pdf_url,
                relation="待排序：由 ScholarFlow 根据关键词相关性计算。",
                priority="Medium",
            ),
        )

    return papers


def build_arxiv_query(query: str, relaxed: bool = False) -> str:
    terms = [term for term in re.split(r"\s+", query.strip()) if term]
    if len(terms) <= 1:
        return f"all:{query}"
    if relaxed:
        return " OR ".join(f"all:{term}" for term in terms[:6])
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
                "best_oa_location",
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

    url = f"{OPENALEX_WORKS_URL}?{urllib.parse.urlencode(params)}"
    try:
        payload = json.loads(request_text(url))
    except urllib.error.HTTPError as error:
        if error.code in {503, 504}:
            raise SourceDegradedError(
                "openalex",
                query,
                error.code,
                "OpenAlex 暂时不可用，已降级为仅使用其它检索源。",
            ) from error
        raise
    papers: list[PaperCandidate] = []
    for work in payload.get("results", []):
        title = normalize_space(work.get("display_name") or "")
        if not title:
            continue

        primary_location = work.get("primary_location") or {}
        best_oa_location = work.get("best_oa_location") or {}
        source = primary_location.get("source") or {}
        url = primary_location.get("landing_page_url") or work.get("doi") or work.get("id") or ""
        pdf_url = best_oa_location.get("pdf_url") or primary_location.get("pdf_url") or ""
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
                pdf_url=pdf_url,
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
    cached = read_request_cache(url)
    if cached is not None:
        return cached
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, application/atom+xml, text/xml",
            "User-Agent": "ScholarFlow/0.1 (local research workflow agent)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS, context=get_ssl_context()) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        if error.code in TRANSIENT_HTTP_STATUS:
            raise SourceDegradedError(
                infer_source_from_url(url),
                extract_query_from_url(url),
                error.code,
                str(error),
            ) from error
        raise
    write_request_cache(url, payload)
    return payload


def get_ssl_context() -> ssl.SSLContext | None:
    global SSL_CONTEXT
    if SSL_CONTEXT is not None:
        return SSL_CONTEXT
    if certifi is None:
        return None
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    return SSL_CONTEXT


def read_request_cache(url: str) -> str | None:
    if REQUEST_CACHE_TTL_SECONDS <= 0:
        return None
    cached = REQUEST_CACHE.get(url)
    if cached is None:
        return None
    created_at, payload = cached
    if time.time() - created_at > REQUEST_CACHE_TTL_SECONDS:
        REQUEST_CACHE.pop(url, None)
        return None
    return payload


def write_request_cache(url: str, payload: str) -> None:
    if REQUEST_CACHE_TTL_SECONDS <= 0:
        return
    REQUEST_CACHE[url] = (time.time(), payload)


def infer_source_from_url(url: str) -> str:
    if "openalex" in url:
        return "openalex"
    if "arxiv" in url:
        return "arxiv"
    return "source"


def extract_query_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    return (params.get("search") or params.get("search_query") or [""])[0]


def compact_retrieval_errors(errors: list[str]) -> list[str]:
    if not errors:
        return []

    output: list[str] = []
    relaxed_queries: list[str] = []
    grouped: dict[tuple[str, str], list[str]] = {}

    for error in errors:
        if error.startswith("query_relaxed:"):
            relaxed_queries.append(error.split(":", 2)[1])
            continue
        if error.startswith("low_recall:"):
            output.append(error)
            continue
        if error.startswith("relevance_coverage:"):
            output.append(error)
            continue

        source, reason = retrieval_error_key(error)
        grouped.setdefault((source, reason), []).append(error)

    if relaxed_queries:
        examples = ", ".join(relaxed_queries[:3])
        suffix = f"; +{len(relaxed_queries) - 3} more" if len(relaxed_queries) > 3 else ""
        output.append(f"query_relaxed_summary: relaxed {len(relaxed_queries)} query variants after low recall: {examples}{suffix}.")

    for (source, reason), bucket in grouped.items():
        if len(bucket) == 1:
            output.append(bucket[0])
            continue
        sample_queries = ", ".join(extract_error_query(item) for item in bucket[:3] if extract_error_query(item))
        suffix = f"; +{len(bucket) - 3} more" if len(bucket) > 3 else ""
        output.append(f"{source}_summary: {len(bucket)} retrieval warnings with {reason}; examples: {sample_queries}{suffix}.")

    return output


def retrieval_error_key(error: str) -> tuple[str, str]:
    parts = error.split(":", 2)
    source = parts[0] if parts else "source"
    detail = parts[2] if len(parts) >= 3 else error
    if "degraded status=" in detail:
        match = re.search(r"degraded status=(\d+|unknown)", detail)
        status = match.group(1) if match else "unknown"
        return source, f"degraded status={status}"
    if "timed out" in detail.lower():
        return source, "request timeout"
    if "CERTIFICATE_VERIFY_FAILED" in detail:
        return source, "certificate verification failure"
    if "nodename nor servname" in detail or "Name or service not known" in detail:
        return source, "DNS/network unavailable"
    return source, truncate(normalize_space(detail), 120)


def extract_error_query(error: str) -> str:
    parts = error.split(":", 2)
    if len(parts) < 2:
        return ""
    return truncate(normalize_space(parts[1]), 80)


def rank_and_deduplicate(candidates: list[PaperCandidate], query: str) -> list[PaperCandidate]:
    return rank_and_deduplicate_result(candidates, query).papers


def rank_and_deduplicate_result(candidates: list[PaperCandidate], query: str) -> RankedPaperSet:
    deduped: dict[str, PaperCandidate] = {}
    for candidate in candidates:
        key = normalize_title_key(candidate.title)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = candidate
            continue
        if source_rank(candidate.source) > source_rank(existing.source):
            merge_candidate_access(candidate, existing)
            deduped[key] = candidate
        else:
            merge_candidate_access(existing, candidate)

    intent = build_query_intent(query)
    ranked: list[PaperCandidate] = []
    quality_counts = {"strong": 0, "medium": 0, "weak": 0, "off_topic": 0}
    for candidate in deduped.values():
        relevance = score_candidate(candidate, intent)
        candidate.relevance_score = round(relevance.score, 4)
        candidate.priority = priority_from_score(relevance.score, relevance.quality)
        candidate.relation = relevance.reason
        candidate.relevance_quality = relevance.quality
        candidate.matched_terms = relevance.matched_terms
        candidate.review_required = relevance.review_required
        quality_counts[relevance.quality] = quality_counts.get(relevance.quality, 0) + 1
        if relevance.quality in {"strong", "medium"}:
            ranked.append(candidate)

    returned = sorted(ranked, key=lambda paper: paper.relevance_score, reverse=True)
    coverage = {
        "candidate_count": len(deduped),
        "returned_count": len(returned),
        "strong_match_count": quality_counts["strong"],
        "medium_match_count": quality_counts["medium"],
        "weak_match_count": quality_counts["weak"],
        "off_topic_count": quality_counts["off_topic"],
        "filtered_count": quality_counts["weak"] + quality_counts["off_topic"],
    }
    return RankedPaperSet(papers=returned, coverage=coverage)


def merge_candidate_access(preferred: PaperCandidate, alternate: PaperCandidate) -> PaperCandidate:
    """Keep the ranked metadata record while preserving an OA PDF found on a duplicate."""
    if not preferred.pdf_url:
        preferred.pdf_url = alternate.pdf_url or derive_arxiv_pdf_url(alternate.url)
    if not preferred.url and alternate.url:
        preferred.url = alternate.url
    return preferred


def derive_arxiv_pdf_url(url: str) -> str:
    parsed = urllib.parse.urlparse(normalize_space(url))
    if (parsed.hostname or "").lower() not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        return ""
    match = re.match(r"/(?:abs|pdf)/(.+?)(?:\.pdf)?$", parsed.path, flags=re.IGNORECASE)
    if not match:
        return ""
    identifier = match.group(1)
    return f"https://arxiv.org/pdf/{identifier}.pdf"


def score_candidate(candidate: PaperCandidate, query_terms: set[str] | QueryIntent) -> CandidateRelevance:
    intent = query_terms if isinstance(query_terms, QueryIntent) else build_query_intent(" ".join(sorted(query_terms)))
    haystack = f"{candidate.title} {candidate.abstract} {candidate.venue}".lower()
    title_text = candidate.title.lower()
    term_overlap = score_term_overlap(haystack, intent.terms, weight=0.16, max_score=1.8)
    core_overlap = score_term_overlap(haystack, intent.core_terms, weight=0.34, max_score=1.8)
    title_overlap = score_term_overlap(title_text, intent.terms, weight=0.24, max_score=1.1)
    title_core_overlap = score_term_overlap(title_text, intent.core_terms, weight=0.42, max_score=1.4)
    matched_groups = [
        group_name
        for group_name, group_terms in intent.groups.items()
        if group_matches_intent(group_name, group_terms, haystack)
    ]
    matched_object_groups = [group for group in matched_groups if group in intent.object_groups]
    matched_problem_groups = [group for group in matched_groups if group in intent.problem_groups]
    matched_support_groups = [group for group in matched_groups if group in intent.support_groups]
    core_group_count = len([group for group in matched_groups if group in intent.core_groups])
    group_coverage = len(matched_groups) / max(len(intent.groups), 1)
    specific_overlap = score_term_overlap(haystack, intent.direction_specific_terms, weight=0.22, max_score=1.2)
    title_specific_overlap = score_term_overlap(title_text, intent.direction_specific_terms, weight=0.35, max_score=1.1)
    matched_terms = unique_preserve_order(
        [
            *title_specific_overlap.matched_terms,
            *specific_overlap.matched_terms,
            *title_core_overlap.matched_terms,
            *core_overlap.matched_terms,
            *title_overlap.matched_terms,
            *term_overlap.matched_terms,
        ],
    )
    current_year = datetime.now(timezone.utc).year
    year = int(candidate.year) if candidate.year.isdigit() else current_year - 8
    recency_score = max(0.0, 1.0 - min(max(current_year - year, 0), 8) / 8)
    source_score = 0.25 if candidate.source == "arxiv" else 0.18
    source_prior = min(max(float(candidate.relevance_score or 0.0), 0.0), 0.35)
    score = (
        term_overlap.score
        + core_overlap.score
        + title_overlap.score
        + title_core_overlap.score
        + group_coverage * 0.6
        + recency_score * 0.25
        + source_score
        + source_prior
    )

    domain_mismatch = detect_domain_mismatch(candidate, intent)
    required_intent_match = satisfies_required_intent(intent, matched_object_groups, matched_problem_groups, core_group_count)
    support_only_match = bool(matched_support_groups) and not matched_object_groups and not matched_problem_groups
    has_specific_match = bool(specific_overlap.matched_terms or title_specific_overlap.matched_terms)
    strict_object_hallucination = requires_object_hallucination_focus(intent)
    object_hallucination_match = matches_object_hallucination_focus(candidate)
    relevance_evidence = build_relevance_evidence_snippet(candidate, matched_terms)
    if domain_mismatch:
        quality = "off_topic"
        score = min(score, 0.2)
    elif strict_object_hallucination and not object_hallucination_match:
        # A generic "hallucination" or "vision-language" match is not enough for
        # an object-hallucination evaluation direction. It is a useful recall hint,
        # but not evidence that the paper belongs in the default reading set.
        quality = "weak" if required_intent_match else "off_topic"
        score = min(score, 0.5 if required_intent_match else 0.25)
    elif support_only_match:
        quality = "off_topic"
        score = min(score, 0.3)
    elif not required_intent_match:
        quality = "weak" if core_group_count else "off_topic"
        score = min(score, 0.55 if core_group_count else 0.25)
    elif not has_specific_match:
        quality = "weak"
        score = min(score, 0.7)
    elif is_strong_relevance(
        intent=intent,
        core_group_count=core_group_count,
        matched_object_groups=matched_object_groups,
        matched_problem_groups=matched_problem_groups,
        title_specific_terms=title_specific_overlap.matched_terms,
        title_core_terms=title_core_overlap.matched_terms,
        score=score,
    ):
        quality = "strong"
    else:
        quality = "medium"

    if quality == "off_topic":
        review_required = False
    elif quality == "weak":
        review_required = True
    else:
        review_required = False

    if domain_mismatch:
        reason = (
            f"离题过滤：候选论文领域与 query 意图不一致；matched={', '.join(matched_terms[:6]) or 'support-only'}；"
            f"来源 {candidate.source}，年份 {candidate.year or 'unknown'}。"
        )
    elif strict_object_hallucination and not object_hallucination_match:
        reason = (
            "弱匹配，未达到对象幻觉评估核心主题门槛：候选只命中泛化的 hallucination/VLM 词，"
            "没有 object hallucination、POPE 或 visual grounding 等直接证据。"
        )
    elif support_only_match:
        reason = (
            f"离题过滤：仅命中 support terms（{', '.join(matched_terms[:6]) or 'assessment/evaluation/evidence'}），"
            "未命中核心研究对象或核心问题。"
        )
    elif quality == "off_topic":
        reason = (
            f"离题过滤：未命中研究方向核心意图；来源 {candidate.source}，年份 {candidate.year or 'unknown'}。"
        )
    elif quality == "weak":
        reason = (
            f"弱匹配，需要人工复核：命中 {', '.join(matched_terms[:6]) or '少量泛化词'}；"
            f"coverage={group_coverage:.2f}；来源 {candidate.source}，年份 {candidate.year or 'unknown'}。"
        )
    else:
        reason = (
            f"相关性 {quality}：命中 {', '.join(matched_terms[:8]) or '核心意图'}；"
            f"直接证据：{relevance_evidence}；coverage={group_coverage:.2f}；"
            f"年份 {candidate.year or 'unknown'}；来源 {candidate.source}。"
        )
    return CandidateRelevance(
        score=round(score, 4),
        reason=reason,
        quality=quality,
        matched_terms=matched_terms[:12],
        review_required=review_required,
    )


def priority_from_score(score: float, quality: str = "medium") -> str:
    if quality == "strong" and score >= 1.35:
        return "High"
    if quality in {"strong", "medium"} and score >= 0.75:
        return "Medium"
    return "Watch"


def group_matches_intent(group_name: str, group_terms: set[str], haystack: str) -> bool:
    if group_name == "evidence_faithfulness":
        specific_terms = group_terms - {"evidence"}
        return bool(score_term_overlap(haystack, specific_terms, weight=0.1, max_score=0.1).matched_terms)
    return bool(score_term_overlap(haystack, group_terms, weight=0.1, max_score=0.1).matched_terms)


def satisfies_required_intent(
    intent: QueryIntent,
    matched_object_groups: list[str],
    matched_problem_groups: list[str],
    core_group_count: int,
) -> bool:
    if intent.object_groups and intent.problem_groups:
        return bool(matched_object_groups) and bool(matched_problem_groups)
    if intent.object_groups:
        return bool(matched_object_groups)
    if intent.problem_groups:
        return bool(matched_problem_groups)
    return core_group_count > 0


def is_strong_relevance(
    intent: QueryIntent,
    core_group_count: int,
    matched_object_groups: list[str],
    matched_problem_groups: list[str],
    title_specific_terms: list[str],
    title_core_terms: list[str],
    score: float,
) -> bool:
    if intent.object_groups and intent.problem_groups:
        return bool(matched_object_groups) and bool(matched_problem_groups) and (
            core_group_count >= 3 or bool(title_specific_terms) or (bool(title_core_terms) and score >= 1.4)
        )
    return core_group_count >= 2 or (core_group_count >= 1 and bool(title_specific_terms or title_core_terms) and score >= 1.1)


def detect_domain_mismatch(candidate: PaperCandidate, intent: QueryIntent) -> bool:
    text = f"{candidate.title} {candidate.abstract} {candidate.venue} {candidate.type}".lower()
    query = intent.query_text
    for domain, patterns in DOMAIN_MISMATCH_PATTERNS.items():
        if not any(pattern in text for pattern in patterns):
            continue
        if any(allowed in query for allowed in DOMAIN_QUERY_ALLOWLIST.get(domain, [])):
            continue
        return True
    return False


def requires_object_hallucination_focus(intent: QueryIntent) -> bool:
    query = intent.query_text
    return any(marker in query for marker in OBJECT_HALLUCINATION_DIRECTION_MARKERS)


def matches_object_hallucination_focus(candidate: PaperCandidate) -> bool:
    text = normalize_space(f"{candidate.title} {candidate.abstract}").lower()
    if any(pattern in text for pattern in OBJECT_HALLUCINATION_PRIMARY_PATTERNS):
        return True
    if "visual grounding" not in text:
        return False
    # Visual grounding by itself spans robotics, autonomous driving, OCR and
    # detection. Treat it as direct object-hallucination evidence only when the
    # paper also names both a VLM/VQA object and an evaluation operation.
    has_visual_model_context = any(pattern in text for pattern in OBJECT_HALLUCINATION_VISUAL_CONTEXT_PATTERNS)
    has_evaluation_context = any(pattern in text for pattern in OBJECT_HALLUCINATION_EVALUATION_PATTERNS)
    return has_visual_model_context and has_evaluation_context


def build_relevance_evidence_snippet(candidate: PaperCandidate, matched_terms: list[str]) -> str:
    title = normalize_space(candidate.title)
    abstract = normalize_space(candidate.abstract)
    for source, text in (("title", title), ("abstract", abstract)):
        if not text:
            continue
        sentences = [normalize_space(item) for item in re.split(r"(?<=[.!?。！？])\s+", text) if normalize_space(item)]
        matching = next(
            (
                sentence
                for sentence in sentences
                if any(term and term in sentence.lower() for term in matched_terms)
            ),
            sentences[0] if sentences else text,
        )
        return f"{source}=`{truncate(matching, 180)}`"
    return "metadata 中没有可引用的 title/abstract 片段"


def significant_terms(query: str) -> set[str]:
    return build_query_intent(query).terms


def build_query_intent(query: str) -> QueryIntent:
    lower = normalize_space(query).lower()
    terms = set(extract_terms(lower, limit=32))
    groups: dict[str, set[str]] = {}
    core_groups: set[str] = set()
    object_groups: set[str] = set()
    problem_groups: set[str] = set()
    support_groups: set[str] = set()
    direction_specific_terms: set[str] = set()

    def add_group(
        name: str,
        triggers: list[str],
        aliases: list[str],
        core: bool = True,
        role: str = "core",
        specific_aliases: list[str] | None = None,
        force: bool = False,
    ) -> None:
        nonlocal direction_specific_terms
        if force or any(trigger in lower for trigger in triggers):
            normalized_aliases = {normalize_intent_term(alias) for alias in aliases if normalize_intent_term(alias)}
            groups[name] = normalized_aliases
            terms.update(normalized_aliases)
            if core:
                core_groups.add(name)
            if role == "object":
                object_groups.add(name)
            elif role == "problem":
                problem_groups.add(name)
            else:
                support_groups.add(name)
            if core:
                specific_source = specific_aliases if specific_aliases is not None else aliases
                direction_specific_terms.update(
                    normalize_intent_term(alias)
                    for alias in specific_source
                    if normalize_intent_term(alias) and normalize_intent_term(alias) not in SUPPORT_ONLY_TERMS
                )

    add_group(
        "multimodal_vlm",
        ["多模态", "vision-language", "vision language", "vlm", "mllm", "multimodal", "multi modal"],
        ["multimodal", "multi modal", "vision language", "vision language model", "vlm", "mllm", "large vision language model"],
        role="object",
    )
    add_group(
        "visual_question_answering",
        ["视觉问答", "visual question", "vqa"],
        ["visual question answering", "visual question", "vqa", "vqa v2", "ok vqa"],
        role="object",
    )
    add_group(
        "evidence_faithfulness",
        ["证据", "忠实", "faithful", "faithfulness", "evidence", "grounding", "grounded"],
        [
            "evidence",
            "faithfulness",
            "faithful",
            "evidence faithfulness",
            "evidence grounding",
            "grounding",
            "grounded evidence",
            "visual grounding",
        ],
        role="problem",
        specific_aliases=[
            "faithfulness",
            "faithful",
            "evidence faithfulness",
            "evidence grounding",
            "grounding",
            "grounded evidence",
            "visual grounding",
        ],
    )
    add_group(
        "hallucination",
        ["幻觉", "hallucination", "hallucinated"],
        [
            "hallucination",
            "object hallucination",
            "visual hallucination",
            "hallucination benchmark",
            "pope",
            "pope benchmark",
            "lvlm hallucination",
            "large vision language model hallucination",
        ],
        role="problem",
    )
    add_group(
        "image_restoration",
        ["图像修复", "image restoration", "超分辨率", "super resolution", "super-resolution", "sisr"],
        ["image restoration", "blind image restoration", "super resolution", "super-resolution", "single image super resolution", "sisr"],
        role="object",
    )
    add_group(
        "research_agent",
        ["智能体", "agent", "workflow", "工具调用", "科研"],
        ["agent", "research agent", "workflow", "tool augmented agent", "scientific discovery workflow"],
        role="object",
    )
    add_group(
        "evaluation",
        ["评估", "评价", "benchmark", "evaluation", "eval", "metric", "测评"],
        ["evaluation", "benchmark", "metric", "assessment", "evaluating"],
        core=False,
        role="support",
    )
    add_group(
        "large_language_model",
        ["大模型", "large language model", "llm", "foundation model"],
        ["large language model", "llm", "foundation model"],
        core=False,
        role="support",
    )
    if (
        "hallucination" not in groups
        and "evidence_faithfulness" in groups
        and ("multimodal_vlm" in groups or "visual_question_answering" in groups)
    ):
        add_group(
            "hallucination",
            [],
            [
                "hallucination",
                "object hallucination",
                "visual hallucination",
                "hallucination benchmark",
                "pope",
                "pope benchmark",
                "lvlm hallucination",
                "large vision language model hallucination",
            ],
            role="problem",
            force=True,
        )

    core_terms = set().union(*(groups[name] for name in core_groups)) if core_groups else set(terms)
    return QueryIntent(
        query_text=lower,
        terms={term for term in terms if term},
        core_terms={term for term in core_terms if term},
        groups=groups or {"query": terms},
        core_groups=core_groups or {"query"},
        object_groups=object_groups,
        problem_groups=problem_groups,
        support_groups=support_groups,
        direction_specific_terms=direction_specific_terms or (core_terms - SUPPORT_ONLY_TERMS),
    )


def normalize_intent_term(value: str) -> str:
    return normalize_space(value.lower().replace("vision-language", "vision language"))


def has_relevance_filtering(coverage: dict[str, int]) -> bool:
    return coverage.get("filtered_count", 0) > 0 or coverage.get("off_topic_count", 0) > 0


def format_relevance_coverage(coverage: dict[str, int]) -> str:
    return (
        f"{coverage.get('candidate_count', 0)} candidates / "
        f"{coverage.get('eligible_count', coverage.get('returned_count', 0))} eligible / "
        f"{coverage.get('returned_count', 0)} returned / "
        f"{coverage.get('truncated_count', 0)} truncated by limit / "
        f"{coverage.get('strong_match_count', 0)} strong matches / "
        f"{coverage.get('medium_match_count', 0)} medium matches / "
        f"{coverage.get('weak_match_count', 0)} weak filtered / "
        f"{coverage.get('off_topic_count', 0)} off-topic filtered"
    )


def contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))


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
            "## Relevance Coverage",
            format_relevance_coverage(result.relevance_coverage or {}),
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
            "relevance_coverage": result.relevance_coverage,
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
