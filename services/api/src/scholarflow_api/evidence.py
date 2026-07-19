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
    section: str = ""
    page: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidencePack:
    evidence_level: str
    confidence: str
    source_confidence: str
    extraction_confidence: str
    snippets: list[EvidenceSnippet]
    missing_evidence: list[str]
    grounding_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_level": self.evidence_level,
            "confidence": self.confidence,
            "source_confidence": self.source_confidence,
            "extraction_confidence": self.extraction_confidence,
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
    source_confidence = infer_source_confidence(snippets, paper)
    extraction_confidence = infer_extraction_confidence(snippets, missing)
    confidence = lower_confidence(source_confidence, extraction_confidence)
    level = infer_evidence_level(paper, sections)
    return EvidencePack(
        evidence_level=level,
        confidence=confidence,
        source_confidence=source_confidence,
        extraction_confidence=extraction_confidence,
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
    title_snippets: list[EvidenceSnippet] = []
    abstract_snippets: list[EvidenceSnippet] = []
    provenance_snippets: list[EvidenceSnippet] = []
    full_text_snippets: list[EvidenceSnippet] = []
    generated_snippets: list[EvidenceSnippet] = []
    title = normalize_space(paper.get("title", ""))
    if title:
        title_snippets.append(
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
        abstract_snippets.append(
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
        provenance_snippets.append(
            EvidenceSnippet(
                id="venue_year",
                source="metadata.venue_year",
                kind="metadata",
                text=f"{venue or 'source unknown'} / {year or 'year unknown'}",
                note="venue/year 只作为来源与时效信号，不等同于质量证明。",
                confidence="low",
            ),
        )

    full_text = str(paper.get("full_text", "") or "")
    for index, located in enumerate(select_full_text_sentences(full_text, direction), start=1):
        full_text_snippets.append(
            EvidenceSnippet(
                id=f"pdf_full_text_{index}",
                source="pdf.full_text",
                kind=infer_sentence_kind(located.text),
                text=located.text[:360],
                note="来自 PDF 文本层的定位片段；语义归类仍需回到原文复核。",
                confidence="medium",
                section=located.section,
                page=located.page,
            ),
        )

    for section in sections[:4]:
        title_text = normalize_space(section.get("title", ""))
        content = normalize_space(section.get("content", ""))
        if not content:
            continue
        generated_snippets.append(
            EvidenceSnippet(
                id=f"paper_card_{section.get('id', title_text).lower()}",
                source="generated.paper_card",
                kind=infer_sentence_kind(f"{title_text} {content}"),
                text=f"{title_text}: {content}"[:260],
                note="来自 ScholarFlow 生成的 paper card，是二级加工证据，需要回原文复核。",
                confidence="low",
            ),
        )
        if len(generated_snippets) >= 4:
            break

    # Keep the pack compact without allowing title/abstract metadata to consume
    # every slot before PDF evidence is added.
    snippets = [
        *title_snippets[:1],
        *full_text_snippets[:3],
        *abstract_snippets[:2],
        *provenance_snippets[:1],
    ]
    if len(snippets) < 7:
        snippets.extend(generated_snippets[: 7 - len(snippets)])
    return snippets[:7]


def infer_missing_evidence(paper: dict[str, Any], sections: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    if not normalize_space(paper.get("abstract", "")):
        missing.append("缺少 abstract，当前判断只能基于标题和来源元数据。")
    if not sections and not normalize_space(paper.get("full_text", "")):
        missing.append("缺少 12 条 paper card 或全文片段，方法和实验判断需要补充。")
    if "arxiv" in normalize_space(paper.get("venue", "")).lower() or "arxiv" in normalize_space(paper.get("source", "")).lower():
        missing.append("venue 仍是 arXiv/source 信号，顶会顶刊结论需要后续 metadata 验证。")
    if not normalize_space(paper.get("url", "")):
        missing.append("缺少论文 URL，用户无法直接回到原文核验。")
    if infer_evidence_level(paper, sections) == "full_text" and normalize_space(paper.get("full_text", "")):
        missing.append("已解析 PDF 文本层；表格结构、公式版式、引用图和代码仓库仍需回到原始材料复核。")
    else:
        provenance = paper.get("full_text_provenance") if isinstance(paper.get("full_text_provenance"), dict) else {}
        failure = normalize_space(provenance.get("error", ""))
        if failure:
            missing.append(f"PDF 全文未进入证据链：{failure}")
        else:
            missing.append("未获得可解析的开放 PDF 全文；方法、实验、消融和失败样本仍需补充。")
    return unique_preserve_order(missing)


def infer_confidence(snippets: list[EvidenceSnippet], missing: list[str], paper: dict[str, Any]) -> str:
    return lower_confidence(
        infer_source_confidence(snippets, paper),
        infer_extraction_confidence(snippets, missing),
    )


def infer_source_confidence(snippets: list[EvidenceSnippet], paper: dict[str, Any]) -> str:
    if any(snippet.source == "pdf.full_text" for snippet in snippets):
        return "high"
    abstract_available = bool(normalize_space(paper.get("abstract", "")))
    if abstract_available:
        return "medium"
    return "low"


def infer_extraction_confidence(snippets: list[EvidenceSnippet], missing: list[str]) -> str:
    located_pdf = [
        snippet
        for snippet in snippets
        if snippet.source == "pdf.full_text" and snippet.page is not None and snippet.section not in {"", "unknown"}
    ]
    section_count = len({snippet.section for snippet in located_pdf})
    if len(located_pdf) >= 3 and section_count >= 2 and len(missing) <= 1:
        return "high"
    if located_pdf or any(snippet.source == "metadata.abstract" for snippet in snippets):
        return "medium"
    return "low"


def lower_confidence(left: str, right: str) -> str:
    rank = {"low": 0, "medium": 1, "high": 2}
    return left if rank.get(left, 0) <= rank.get(right, 0) else right


def infer_evidence_level(paper: dict[str, Any], sections: list[dict[str, Any]]) -> str:
    explicit = normalize_evidence_level(paper.get("evidence_level", ""))
    if explicit:
        return explicit
    if normalize_space(paper.get("abstract", "")):
        return "abstract_only"
    return "metadata_only"


def normalize_evidence_level(value: Any) -> str:
    normalized = normalize_space(value).lower().replace("-", "_").replace("+", "_")
    if normalized in {"metadata_only", "abstract_only", "full_text"}:
        return normalized
    if normalized in {"metadata_abstract", "metadata_abstract_paper_card"}:
        return "abstract_only"
    if normalized in {"metadata", "metadataonly"}:
        return "metadata_only"
    return ""


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


@dataclass
class LocatedSentence:
    text: str
    section: str
    page: int | None


def select_full_text_sentences(text: str, direction: str) -> list[LocatedSentence]:
    if not text:
        return []
    direction_terms = significant_terms(direction)
    research_terms = {
        "method",
        "experiment",
        "evaluation",
        "dataset",
        "baseline",
        "ablation",
        "result",
        "limitation",
        "failure",
    }
    sentences: list[LocatedSentence] = []
    current_page: int | None = None
    current_section = "unknown"
    buffer: list[str] = []

    def flush() -> None:
        block = normalize_space(" ".join(buffer))
        for sentence in re.split(r"(?<=[。！？.!?])\s+", block):
            normalized = normalize_space(sentence)
            if len(normalized) >= 40 and current_section not in {"references", "related_work", "front_matter"}:
                sentences.append(LocatedSentence(normalized, current_section, current_page))
        buffer.clear()

    for line in str(text).splitlines():
        page_match = re.fullmatch(r"\[PDF page (\d+)\]", line.strip())
        if page_match:
            flush()
            current_page = int(page_match.group(1))
            continue
        section_match = re.fullmatch(r"\[Section: ([a-z_]+)\]", line.strip())
        if section_match:
            flush()
            current_section = section_match.group(1)
            continue
        if line.strip():
            buffer.append(line.strip())
    flush()
    if not sentences and normalize_space(text):
        sentences = [
            LocatedSentence(normalize_space(sentence), "unknown", None)
            for sentence in re.split(r"(?<=[。！？.!?])\s+", normalize_space(text))
            if len(normalize_space(sentence)) >= 40
        ]
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (
            sum(term in item[1].text.lower() for term in research_terms),
            sum(term in item[1].text.lower() for term in direction_terms),
            -item[0],
        ),
        reverse=True,
    )
    return [sentence for _index, sentence in ranked[:3]]


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
