from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class EvidenceSnippet:
    id: str
    source: str
    kind: str
    text: str
    note: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidencePack:
    evidence_level: str
    confidence: str
    snippets: list[EvidenceSnippet]
    missing_evidence: list[str]
    grounding_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_level": self.evidence_level,
            "confidence": self.confidence,
            "snippets": [snippet.to_dict() for snippet in self.snippets],
            "missing_evidence": self.missing_evidence,
            "grounding_summary": self.grounding_summary,
        }


def build_paper_evidence_pack(
    paper: dict[str, Any],
    sections: list[dict[str, Any]],
    direction: str,
) -> EvidencePack:
    snippets = build_paper_evidence_snippets(paper, sections, direction)
    missing = infer_missing_evidence(paper, sections)
    confidence = infer_confidence(snippets, missing, paper)
    level = infer_evidence_level(paper, sections)
    return EvidencePack(
        evidence_level=level,
        confidence=confidence,
        snippets=snippets,
        missing_evidence=missing,
        grounding_summary=build_grounding_summary(level, confidence, snippets, missing),
    )


def build_baseline_reference_evidence(
    paper: dict[str, Any],
    direction: str,
    category: str,
) -> tuple[list[EvidenceSnippet], str, str]:
    snippets = build_paper_evidence_snippets(paper, [], direction)
    missing = infer_missing_evidence(paper, [])
    if category == "classic" and parse_year(paper.get("year", "")) >= 2024:
        missing.append("该 baseline 被归为 classic 主要因为候选池不足，需要后续引用图验证其基础地位。")
    if category == "alternative_paradigm" and len(snippets) < 2:
        missing.append("异质范式判断主要来自标题/摘要关键词，需要 method 细节确认。")
    confidence = infer_confidence(snippets, missing, paper)
    gap = "；".join(missing[:3]) if missing else "当前元数据和摘要足以支撑弱到中等置信度的 baseline 归类。"
    return snippets, confidence, gap


def build_paper_evidence_snippets(
    paper: dict[str, Any],
    sections: list[dict[str, Any]],
    direction: str,
) -> list[EvidenceSnippet]:
    snippets: list[EvidenceSnippet] = []
    title = normalize_space(paper.get("title", ""))
    if title:
        snippets.append(
            EvidenceSnippet(
                id="title",
                source="metadata.title",
                kind="metadata",
                text=title[:260],
                note="标题用于判断任务、方法范式和方向相关性。",
                confidence="medium",
            ),
        )

    abstract = normalize_space(paper.get("abstract", ""))
    for index, sentence in enumerate(select_relevant_sentences(abstract, direction), start=1):
        snippets.append(
            EvidenceSnippet(
                id=f"abstract_{index}",
                source="metadata.abstract",
                kind=infer_sentence_kind(sentence),
                text=sentence[:260],
                note="摘要片段用于约束 ResearchSight，不能替代全文证据。",
                confidence="medium",
            ),
        )

    venue = normalize_space(paper.get("venue", "") or paper.get("source", ""))
    year = normalize_space(str(paper.get("year", "")))
    if venue or year:
        snippets.append(
            EvidenceSnippet(
                id="venue_year",
                source="metadata.venue_year",
                kind="metadata",
                text=f"{venue or 'source unknown'} / {year or 'year unknown'}",
                note="venue/year 只作为来源与时效信号，不等同于质量证明。",
                confidence="low",
            ),
        )

    for section in sections[:4]:
        title_text = normalize_space(section.get("title", ""))
        content = normalize_space(section.get("content", ""))
        if not content:
            continue
        snippets.append(
            EvidenceSnippet(
                id=f"paper_card_{section.get('id', title_text).lower()}",
                source="generated.paper_card",
                kind=infer_sentence_kind(f"{title_text} {content}"),
                text=f"{title_text}: {content}"[:260],
                note="来自 ScholarFlow 生成的 paper card，是二级加工证据，需要回原文复核。",
                confidence="low",
            ),
        )
        if len(snippets) >= 7:
            break

    return snippets[:7]


def infer_missing_evidence(paper: dict[str, Any], sections: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    if not normalize_space(paper.get("abstract", "")):
        missing.append("缺少 abstract，当前判断只能基于标题和来源元数据。")
    if not sections:
        missing.append("缺少 12 条 paper card 或全文片段，方法和实验判断需要补充。")
    if "arxiv" in normalize_space(paper.get("venue", "")).lower() or "arxiv" in normalize_space(paper.get("source", "")).lower():
        missing.append("venue 仍是 arXiv/source 信号，顶会顶刊结论需要后续 metadata 验证。")
    if not normalize_space(paper.get("url", "")):
        missing.append("缺少论文 URL，用户无法直接回到原文核验。")
    missing.append("尚未接入 PDF 全文解析、引用图和代码仓库证据。")
    return unique_preserve_order(missing)


def infer_confidence(snippets: list[EvidenceSnippet], missing: list[str], paper: dict[str, Any]) -> str:
    abstract_available = bool(normalize_space(paper.get("abstract", "")))
    venue = normalize_space(paper.get("venue", ""))
    if abstract_available and len(snippets) >= 4 and len(missing) <= 2 and venue and "arxiv" not in venue.lower():
        return "high"
    if abstract_available and len(snippets) >= 3:
        return "medium"
    return "low"


def infer_evidence_level(paper: dict[str, Any], sections: list[dict[str, Any]]) -> str:
    if sections and normalize_space(paper.get("abstract", "")):
        return "metadata+abstract+paper-card"
    if normalize_space(paper.get("abstract", "")):
        return "metadata+abstract"
    return "metadata-only"


def build_grounding_summary(
    level: str,
    confidence: str,
    snippets: list[EvidenceSnippet],
    missing: list[str],
) -> str:
    return (
        f"当前判断基于 {level}，提取 {len(snippets)} 条证据片段，置信度为 {confidence}。"
        f" 主要缺口：{missing[0] if missing else '暂无显著缺口'}"
    )


def select_relevant_sentences(text: str, direction: str) -> list[str]:
    if not text:
        return []
    terms = significant_terms(direction)
    sentences = [normalize_space(sentence) for sentence in re.split(r"(?<=[。！？.!?])\s+", text) if normalize_space(sentence)]
    matched = [sentence for sentence in sentences if any(term in sentence.lower() for term in terms)]
    return (matched or sentences)[:2]


def infer_sentence_kind(sentence: str) -> str:
    lower = sentence.lower()
    if any(term in lower for term in ["experiment", "benchmark", "evaluation", "metric", "dataset", "评估", "实验"]):
        return "evaluation"
    if any(term in lower for term in ["method", "framework", "architecture", "model", "方法", "架构"]):
        return "method"
    if any(term in lower for term in ["problem", "challenge", "gap", "motivation", "问题", "挑战"]):
        return "problem"
    if any(term in lower for term in ["limitation", "risk", "failure", "hallucination", "缺陷", "失败"]):
        return "risk"
    return "context"


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


def parse_year(value: Any) -> int:
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else 0


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


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
