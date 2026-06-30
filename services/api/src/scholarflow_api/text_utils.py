from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


ENGLISH_STOPWORDS = {
    "about",
    "above",
    "add",
    "adds",
    "after",
    "again",
    "against",
    "all",
    "also",
    "abstract",
    "and",
    "are",
    "around",
    "assume",
    "assumes",
    "based",
    "been",
    "before",
    "being",
    "between",
    "both",
    "but",
    "can",
    "cannot",
    "could",
    "current",
    "data",
    "did",
    "does",
    "doing",
    "done",
    "during",
    "each",
    "few",
    "for",
    "from",
    "had",
    "has",
    "have",
    "having",
    "how",
    "into",
    "its",
    "generated",
    "may",
    "method",
    "methods",
    "metadata",
    "missing",
    "model",
    "models",
    "more",
    "most",
    "not",
    "off",
    "only",
    "onto",
    "our",
    "out",
    "over",
    "paper",
    "papers",
    "per",
    "research",
    "run",
    "runs",
    "same",
    "scholarflow",
    "should",
    "snippet",
    "snippets",
    "such",
    "than",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "this",
    "those",
    "through",
    "under",
    "used",
    "uses",
    "using",
    "via",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "within",
    "without",
    "would",
}

CHINESE_STOPWORDS = {
    "一个",
    "以及",
    "可以",
    "基于",
    "如何",
    "当前",
    "方向",
    "方法",
    "模型",
    "用户",
    "相关",
    "论文",
    "这个",
    "这些",
    "研究",
}

DOMAIN_PHRASES = [
    "evidence faithfulness",
    "visual grounding",
    "object hallucination",
    "counterexample evaluation",
    "vision language",
    "vision language model",
    "vision-language model",
    "multimodal alignment",
    "hallucination benchmark",
    "paper memory",
    "baseline map",
    "research sight",
    "state space",
    "state space model",
    "selective scan",
    "minimal reproduction",
]

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]*|[\u4e00-\u9fff]+")


@dataclass
class TermOverlapScore:
    score: float
    matched_terms: list[str]
    occurrences: dict[str, int]


def extract_terms(text: str, limit: int = 18, include_domain_phrases: bool = True) -> list[str]:
    normalized = normalize_search_text(text)
    phrase_counts: dict[str, int] = {}
    if include_domain_phrases:
        for phrase in DOMAIN_PHRASES:
            count = count_term_occurrences(normalized, phrase)
            if count:
                phrase_counts[canonical_phrase(phrase)] = count

    token_counts: dict[str, int] = {}
    for token in tokenize_text(normalized):
        if is_noise_token(token):
            continue
        token_counts[token] = token_counts.get(token, 0) + 1

    terms = set(token_counts) | set(phrase_counts)
    ranked = sorted(
        terms,
        key=lambda term: (
            -(phrase_counts.get(term, 0) * 3 + token_counts.get(term, 0)),
            0 if " " in term else 1,
            term,
        ),
    )
    return ranked[:limit]


def score_term_overlap(text: str, terms: set[str] | list[str], weight: float = 0.12, max_score: float = 1.0) -> TermOverlapScore:
    normalized = normalize_search_text(text)
    occurrences: dict[str, int] = {}
    score = 0.0
    for raw_term in terms:
        term = normalize_search_text(raw_term)
        if not term or is_noise_token(term):
            continue
        count = count_term_occurrences(normalized, term)
        if not count:
            continue
        occurrences[term] = count
        term_weight = weight * (2.0 if " " in term else 1.0)
        score += min(term_weight * count, term_weight * 4)
    return TermOverlapScore(
        score=round(min(score, max_score), 4),
        matched_terms=sorted(occurrences, key=lambda term: (-occurrences[term], term)),
        occurrences=occurrences,
    )


def tokenize_text(text: str) -> list[str]:
    normalized = normalize_search_text(text)
    return [match.group(0) for match in TOKEN_PATTERN.finditer(normalized)]


def normalize_terms(terms: set[str] | list[str]) -> set[str]:
    return {
        normalize_search_text(term)
        for term in terms
        if normalize_search_text(term) and not is_noise_token(normalize_search_text(term))
    }


def count_term_occurrences(text: str, term: str) -> int:
    normalized_text = normalize_search_text(text)
    normalized_term = normalize_search_text(term)
    if not normalized_text or not normalized_term:
        return 0
    if contains_cjk(normalized_term):
        return len(re.findall(re.escape(normalized_term), normalized_text))
    pattern = build_word_boundary_pattern(normalized_term)
    return len(re.findall(pattern, normalized_text))


def build_word_boundary_pattern(term: str) -> re.Pattern[str]:
    escaped_parts = [re.escape(part) for part in term.split()]
    body = r"[\s-]+".join(escaped_parts)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")


def is_noise_token(token: str) -> bool:
    normalized = normalize_search_text(token)
    if not normalized:
        return True
    if contains_cjk(normalized):
        return len(normalized) < 2 or normalized in CHINESE_STOPWORDS
    if " " in normalized:
        return False
    return len(normalized) < 3 or normalized in ENGLISH_STOPWORDS


def canonical_phrase(phrase: str) -> str:
    return normalize_search_text(phrase).replace("-", " ")


def normalize_search_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("vision-language", "vision language")
    text = re.sub(r"[_/]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))
