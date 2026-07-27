from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from scholarflow_api.full_text import qualify_card_context
from scholarflow_api.schemas import EvidenceQualification


@dataclass
class PaperCardSection:
    id: str
    title: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class SignalEvidenceRef:
    canonical_value: str
    raw_value: str
    source: str
    section: str
    page: int | None
    quote: str
    confidence: str
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SignalEvidence:
    field: str
    canonical_value: str
    raw_value: str
    source: str
    section: str
    page: int | None
    quote: str
    confidence: str
    validation_errors: list[str] = field(default_factory=list)
    evidence_refs: list[SignalEvidenceRef] = field(default_factory=list)
    availability: str = "partial"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaperSignals:
    task: str
    method: str
    dataset: str
    metric: str
    baseline: str
    claim: str
    limitation: str
    prior_work_limitation: str
    contribution_type: str
    contribution_evidence: str
    missing_signals: list[str]
    signal_evidence: dict[str, SignalEvidence] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeepPaperCard:
    paper_title: str
    evidence_level: str
    evidence_qualification: EvidenceQualification
    signals: PaperSignals
    sections: list[PaperCardSection]
    weakest_assumption: str
    minimal_reproduction: str
    counterexample: str
    follow_up_idea: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_title": self.paper_title,
            "evidence_level": self.evidence_level,
            "evidence_qualification": self.evidence_qualification.model_dump(),
            "signals": self.signals.to_dict(),
            "sections": [section.to_dict() for section in self.sections],
            "weakest_assumption": self.weakest_assumption,
            "minimal_reproduction": self.minimal_reproduction,
            "counterexample": self.counterexample,
            "follow_up_idea": self.follow_up_idea,
        }


SECTION_TITLES = [
    ("research_problem", "1. 研究问题与背景"),
    ("prior_work", "2. 已有研究与不足"),
    ("author_reasoning", "3. 作者可能的思考路径重建"),
    ("intuition", "4. 核心 Intuition"),
    ("method_pipeline", "5. 方法 Pipeline 与真实例子"),
    ("math_theory", "6. 数学与理论解释"),
    ("experiment_logic", "7. 实验逻辑与 Claim 验证"),
    ("takeaways", "8. Take-aways"),
    ("weakest_assumption", "9. 最脆弱的假设"),
    ("minimal_reproduction", "10. 一周最小复现实验"),
    ("counterexample", "11. 反例设计"),
    ("follow_up", "12. 非增量 Follow-up Idea"),
]


def generate_deep_paper_card(
    paper: dict[str, Any],
    extra_context: str = "",
    *,
    evidence_qualification: EvidenceQualification | None = None,
) -> DeepPaperCard:
    title = normalize_space(paper.get("title") or "Untitled Paper")
    abstract = normalize_space(paper.get("abstract") or "")
    venue = normalize_space(paper.get("venue") or paper.get("source") or "unknown venue")
    year = normalize_space(str(paper.get("year") or "unknown year"))
    context = normalize_space(f"{abstract} {extra_context}")
    qualification = qualify_card_context(
        extra_context,
        evidence_qualification,
        has_abstract=bool(abstract),
    )
    evidence_level = qualification.level
    signals = extract_paper_signals(
        title=title,
        abstract=abstract,
        paper_text=extra_context,
        paper_text_source=(
            "pdf.full_text"
            if qualification.level == "full_text" and qualification.verified
            else "user.supplemental_text"
        ),
        venue=venue,
    )
    focus = infer_focus(title, context)
    weakest_assumption = build_weakest_assumption(focus, signals)
    minimal_reproduction = build_minimal_reproduction(signals, title)
    counterexample = build_counterexample(signals, focus)
    follow_up = build_follow_up_idea(signals, focus)
    if evidence_level == "metadata_only":
        weakest_assumption = ""
        minimal_reproduction = ""
        counterexample = ""
        follow_up = ""

    sections = apply_evidence_boundary_to_sections(
        [
        PaperCardSection(
            "research_problem",
            "1. 研究问题与背景",
            build_research_problem_section(title, year, venue, signals, context),
        ),
        PaperCardSection(
            "prior_work",
            "2. 已有研究与不足",
            build_prior_work_section(signals),
        ),
        PaperCardSection(
            "author_reasoning",
            "3. 作者可能的思考路径重建",
            build_author_reasoning_section(signals),
        ),
        PaperCardSection(
            "intuition",
            "4. 核心 Intuition",
            build_intuition_section(signals),
        ),
        PaperCardSection(
            "method_pipeline",
            "5. 方法 Pipeline 与真实例子",
            build_method_pipeline_section(signals),
        ),
        PaperCardSection(
            "math_theory",
            "6. 数学与理论解释",
            build_math_section(focus, signals),
        ),
        PaperCardSection(
            "experiment_logic",
            "7. 实验逻辑与 Claim 验证",
            build_experiment_logic_section(signals),
        ),
        PaperCardSection(
            "takeaways",
            "8. Take-aways",
            build_takeaways_section(signals, focus),
        ),
        PaperCardSection(
            "weakest_assumption",
            "9. 最脆弱的假设",
            weakest_assumption,
        ),
        PaperCardSection(
            "minimal_reproduction",
            "10. 一周最小复现实验",
            minimal_reproduction,
        ),
        PaperCardSection(
            "counterexample",
            "11. 反例设计",
            counterexample,
        ),
        PaperCardSection(
            "follow_up",
            "12. 非增量 Follow-up Idea",
            follow_up,
        ),
        ],
        evidence_level,
        title,
    )

    return DeepPaperCard(
        paper_title=title,
        evidence_level=evidence_level,
        evidence_qualification=qualification,
        signals=signals,
        sections=sections,
        weakest_assumption=weakest_assumption,
        minimal_reproduction=minimal_reproduction,
        counterexample=counterexample,
        follow_up_idea=follow_up,
    )


INSUFFICIENT_PREFIX = "当前证据不足"

DATASET_NAMES = [
    "MMBench",
    "MMMU",
    "MME",
    "MM-Vet",
    "POPE",
    "CHAIR",
    "CHAIRs",
    "MMHal-Bench",
    "AMBER",
    "HallusionBench",
    "LLaVA-Bench",
    "LLaVA-Wild",
    "SEED-Bench",
    "RealWorldQA",
    "ScienceQA",
    "MathVista",
    "ChartQA",
    "DocVQA",
    "TextVQA",
    "VizWiz",
    "VQA v2",
    "OK-VQA",
    "A-OKVQA",
    "GQA",
    "RefCOCO",
    "COCO",
    "ImageNet",
    "Set5",
    "Set14",
    "BSD100",
    "Urban100",
    "Manga109",
    "DIV2K",
    "EndoVis-18",
    "OfficeBench",
]

METRIC_NAMES = [
    "accuracy",
    "acc",
    "F1",
    "precision",
    "recall",
    "AUC",
    "mAP",
    "IoU",
    "win rate",
    "human evaluation",
    "PSNR",
    "SSIM",
    "LPIPS",
    "FID",
    "BLEU",
    "ROUGE",
    "CIDEr",
    "faithfulness",
    "grounding accuracy",
    "hallucination rate",
    "CHAIRs",
    "CHAIRi",
    "Dice",
    "task success rate",
    "step failure rate",
    "execution steps",
]

METRIC_ALIASES = {
    "accuracy": ["accuracy", "acc"],
    "F1": ["F1", "F1-score", "F1 score"],
    "precision": ["precision"],
    "recall": ["recall"],
    "AUC": ["AUC"],
    "mAP": ["mAP"],
    "IoU": ["IoU"],
    "win rate": ["win rate"],
    "human evaluation": ["human evaluation"],
    "PSNR": ["PSNR"],
    "SSIM": ["SSIM"],
    "LPIPS": ["LPIPS"],
    "FID": ["FID"],
    "BLEU": ["BLEU"],
    "ROUGE": ["ROUGE"],
    "CIDEr": ["CIDEr"],
    "faithfulness": ["faithfulness"],
    "grounding accuracy": ["grounding accuracy"],
    "hallucination rate": ["hallucination rate"],
    "CHAIRs": ["CHAIRs", "CHAIR-s"],
    "CHAIRi": ["CHAIRi", "CHAIR-i"],
    "Dice": ["Dice", "Dice score", "Dice coefficient"],
    "task success rate": ["task success rate", "success rate", "task completion rate"],
    "step failure rate": ["step failure rate", "failed steps rate", "failure rate of agent steps"],
    "execution steps": ["execution steps", "number of execution steps"],
}

DATASET_ALIASES = {name: [name] for name in DATASET_NAMES}
DATASET_ALIASES.pop("CHAIRs", None)
DATASET_ALIASES["CHAIR"] = ["CHAIR", "CHAIRs"]
DATASET_ALIASES["MMHal-Bench"] = ["MMHal-Bench", "MMHalBench"]
DATASET_ALIASES["LLaVA-Bench"] = ["LLaVA-Bench", "LLaV A-Bench"]

BASELINE_ALIASES = {
    "LLaVA-1.5": ["LLaVA-1.5", "LLaVA 1.5", "LLaV A-1.5", "LLaV A 1.5"],
    "LLaVA": ["LLaVA", "LLaV A"],
    "InstructBLIP": ["InstructBLIP", "Instruct-BLIP"],
    "BLIP-2": ["BLIP-2", "BLIP2"],
    "MiniGPT-4": ["MiniGPT-4", "MiniGPT4"],
    "GPT-4V": ["GPT-4V", "GPT4V"],
    "GPT-4o": ["GPT-4o", "GPT4o"],
    "Qwen2.5-VL": ["Qwen2.5-VL", "Qwen2.5 VL"],
    "Qwen2-VL": ["Qwen2-VL", "Qwen2 VL"],
    "Qwen-VL": ["Qwen-VL", "Qwen VL"],
    "mPLUG-Owl": ["mPLUG-Owl"],
    "CLIPScore": ["CLIPScore", "CLIP Score"],
    "VCD": ["VCD"],
    "ICD": ["ICD"],
    "OPERA": ["OPERA"],
    "DoLa": ["DoLa"],
    "No memory": ["No memory", "No-memory", "memory-less", "memoryless"],
    "Synapse": ["Synapse"],
    "AWM": ["AWM", "A WM"],
}

METHOD_MARKERS = [
    "we propose",
    "we introduce",
    "we present",
    "our method",
    "our framework",
    "our model",
    "architecture",
    "algorithm",
    "pipeline",
    "training",
    "decoding",
    "prompt",
]

CLAIM_MARKERS = [
    "we show",
    "we demonstrate",
    "outperform",
    "improve",
    "achieve",
    "state-of-the-art",
    "sota",
    "effective",
    "robust",
    "reveals",
    "find that",
    "we find",
]

LIMITATION_MARKERS = [
    "limitation",
    "limited",
    "however",
    "challenge",
    "failure",
    "fails",
    "bias",
    "shortcut",
    "spurious",
    "mismatch",
    "hides",
    "brittle",
    "inadequate",
    "gap",
]

OWN_LIMITATION_MARKERS = [
    "a limitation of our",
    "our limitation",
    "our method is limited",
    "our approach is limited",
    "our model is limited",
    "we are limited",
    "we cannot",
    "we do not",
    "failure case",
    "future work",
]

PRIOR_WORK_MARKERS = [
    "existing methods",
    "existing models",
    "prior work",
    "previous work",
    "previous methods",
    "current methods",
    "these models",
    "these methods",
]


@dataclass
class EvidenceSegment:
    source: str
    section: str
    page: int | None
    text: str


def apply_evidence_boundary_to_sections(
    sections: list[PaperCardSection],
    evidence_level: str,
    paper_title: str,
) -> list[PaperCardSection]:
    if evidence_level == "metadata_only":
        # Keep the only available paper-specific signal (the title) in the
        # research-problem section. Evidence diagnostics belong to the card
        # boundary/checklist, not in twelve pseudo-research paragraphs.
        return [
            PaperCardSection(
                section.id,
                section.title,
                f"`{paper_title}`" if section.id == "research_problem" else "",
            )
            for section in sections
        ]
    # Abstract/full-text cards keep distinct paper-specific content. The global
    # evidence boundary is rendered once instead of being repeated 12 times.
    return sections


def evidence_boundary_sentence(evidence_level: str) -> str:
    if evidence_level == "metadata_only":
        return (
            "证据边界（metadata_only）：当前没有 abstract/PDF/正文，下面是基于标题和元数据的阅读提纲，"
            "不是完整正文阅读结论。"
        )
    if evidence_level == "supplemental_text":
        return (
            "证据边界（supplemental_text）：当前包含用户补充文本，但未通过 PDF 来源、页码和解析验证，"
            "可辅助阅读，不能作为全文级结论。"
        )
    return (
        "证据边界（abstract_only）：当前没有 PDF/完整正文，下面是基于标题和摘要的阅读提纲，"
        "不能当作已讲清整篇论文。"
    )


def evidence_gap_sentence(evidence_level: str) -> str:
    if evidence_level == "metadata_only":
        return "缺少 abstract、method、experiment、baseline、dataset、metric 和 failure case 原文证据。"
    return "缺少 PDF/完整正文中的 method、experiment、baseline、ablation、failure case 和表格证据。"


def extract_paper_signals(
    title: str,
    abstract: str,
    paper_text: str = "",
    venue: str = "",
    *,
    paper_text_source: str = "pdf.full_text",
) -> PaperSignals:
    title_text = normalize_space(title)
    abstract_text = normalize_space(abstract)
    segments = build_evidence_segments(
        title_text,
        abstract_text,
        paper_text,
        paper_text_source=paper_text_source,
    )
    contribution_body = normalize_space(
        " ".join(
            segment.text
            for segment in segments
            if segment.source == "pdf.full_text"
            and segment.section not in {"references", "related_work", "front_matter"}
        ),
    )
    combined = normalize_space(f"{title_text}. {abstract_text} {contribution_body}")
    contribution_type, contribution_evidence = infer_contribution_type(
        title,
        abstract_text,
        contribution_body,
        venue,
    )
    task, task_evidence = extract_task_signal_from_segments(
        segments,
        title,
        abstract,
        combined,
        contribution_type,
    )
    method, method_evidence = extract_method_signal_from_segments(segments, contribution_type)
    dataset, dataset_evidence = extract_named_signal_from_segments(
        segments,
        DATASET_ALIASES,
        "dataset",
        "未发现明确 dataset/benchmark 名称",
        context_markers=["dataset", "benchmark", "evaluation", "evaluate", "experiment", "train", "test", "using", " on "],
    )
    metric, metric_evidence = extract_named_signal_from_segments(
        segments,
        METRIC_ALIASES,
        "metric",
        "未发现明确 metric/evaluation 指标",
        context_markers=["metric", "measure", "report", "evaluation", "evaluate", "score", "accuracy", "rate"],
    )
    baseline, baseline_evidence = extract_baseline_signal_from_segments(segments)
    claim, claim_evidence = extract_claim_signal_from_segments(segments, title)
    limitation, limitation_evidence = extract_own_limitation_signal(segments)
    prior_work_limitation, prior_work_evidence = extract_prior_work_limitation_signal(segments)
    signal_evidence = {
        field_name: evidence
        for field_name, evidence in [
            ("task", task_evidence),
            ("method", method_evidence),
            ("dataset", dataset_evidence),
            ("metric", metric_evidence),
            ("baseline", baseline_evidence),
            ("claim", claim_evidence),
            ("limitation", limitation_evidence),
            ("prior_work_limitation", prior_work_evidence),
        ]
        if evidence is not None
    }
    signals = PaperSignals(
        task=task,
        method=method,
        dataset=dataset,
        metric=metric,
        baseline=baseline,
        claim=claim,
        limitation=limitation,
        prior_work_limitation=prior_work_limitation,
        contribution_type=contribution_type,
        contribution_evidence=contribution_evidence,
        missing_signals=[],
        signal_evidence=signal_evidence,
    )
    signals.missing_signals = [
        field
        for field in ["method", "dataset", "metric", "baseline", "claim", "limitation"]
        if not has_signal(getattr(signals, field))
    ]
    return signals


def build_evidence_segments(
    title: str,
    abstract: str,
    paper_text: str,
    *,
    paper_text_source: str = "pdf.full_text",
) -> list[EvidenceSegment]:
    segments: list[EvidenceSegment] = []
    if title:
        segments.append(EvidenceSegment(source="metadata.title", section="title", page=None, text=title))
    if abstract:
        segments.append(EvidenceSegment(source="metadata.abstract", section="abstract", page=None, text=abstract))
    raw = str(paper_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return segments
    if "[PDF page " not in raw and "[Section: " not in raw:
        current_section = "unknown"
        buffer: list[str] = []
        found_heading = False
        for line in raw.splitlines():
            heading = classify_plain_section_heading(line)
            if heading:
                found_heading = True
                if buffer:
                    segments.append(
                        EvidenceSegment(
                            source=paper_text_source,
                            section=current_section,
                            page=None,
                            text=normalize_space(" ".join(buffer)),
                        ),
                    )
                    buffer = []
                if heading == "references":
                    break
                current_section = heading
                continue
            if line.strip():
                buffer.append(line.strip())
        if buffer:
            segments.append(
                EvidenceSegment(
                    source=paper_text_source,
                    section=current_section if found_heading else "unknown",
                    page=None,
                    text=normalize_space(" ".join(buffer)),
                ),
            )
        return segments

    page: int | None = None
    section = "unknown"
    buffer: list[str] = []

    def flush() -> None:
        text = normalize_space(" ".join(buffer))
        if text:
            segments.append(
                EvidenceSegment(
                    source=paper_text_source,
                    section=section,
                    page=page,
                    text=text,
                ),
            )
        buffer.clear()

    for line in raw.splitlines():
        page_match = re.fullmatch(r"\[PDF page (\d+)\]", line.strip())
        if page_match:
            flush()
            page = int(page_match.group(1))
            continue
        section_match = re.fullmatch(r"\[Section: ([a-z_]+)\]", line.strip())
        if section_match:
            flush()
            section = section_match.group(1)
            continue
        if line.strip():
            buffer.append(line.strip())
    flush()
    return segments


def classify_plain_section_heading(line: str) -> str:
    normalized = normalize_space(line).strip(" .:-").lower()
    normalized = re.sub(r"^\d+(?:\.\d+)*[\s.:-]*", "", normalized)
    headings = {
        "abstract": "abstract",
        "introduction": "introduction",
        "related work": "related_work",
        "background": "related_work",
        "method": "method",
        "methods": "method",
        "methodology": "method",
        "approach": "method",
        "experiments": "experiments",
        "experimental setup": "experiments",
        "evaluation": "experiments",
        "results": "results",
        "analysis": "results",
        "limitations": "limitations",
        "failure cases": "limitations",
        "discussion": "limitations",
        "conclusion": "conclusion",
        "references": "references",
        "bibliography": "references",
    }
    return headings.get(normalized, "")


def extract_method_signal_from_segments(
    segments: list[EvidenceSegment],
    contribution_type: str,
) -> tuple[str, SignalEvidence | None]:
    if contribution_type == "survey":
        return (
            "综述/调研型贡献：主要方法应是组织、比较和归纳已有文献，而不是提出可训练模型。",
            None,
        )
    hit = find_ranked_own_sentence(
        segments,
        purpose="method",
        allowed_sections={"abstract", "method", "experiments", "unknown"},
    )
    if hit:
        segment, sentence = hit
        value = f"方法证据：{sentence}"
        return value, make_signal_evidence("method", value, sentence, segment)
    if contribution_type == "benchmark":
        hit = find_ranked_own_sentence(
            segments,
            purpose="benchmark",
            allowed_sections={"abstract", "method", "experiments", "unknown"},
        )
        if hit:
            segment, sentence = hit
            value = f"评测/benchmark 构造方法：{sentence}"
            return value, make_signal_evidence("method", value, sentence, segment)
    return "", None


def extract_named_signal_from_segments(
    segments: list[EvidenceSegment],
    aliases: dict[str, list[str]],
    field_name: str,
    missing_reason: str,
    *,
    context_markers: list[str],
) -> tuple[str, SignalEvidence | None]:
    matches_by_key: dict[str, tuple[int, int, SignalEvidenceRef]] = {}
    match_order = 0
    for segment in segments:
        if segment.source == "metadata.title" or segment.section in {"references", "related_work", "front_matter"}:
            continue
        for sentence in split_sentences(segment.text):
            lower = f" {sentence.lower()} "
            sentence_matches: list[tuple[str, str]] = []
            for canonical, variants in aliases.items():
                for variant in variants:
                    pattern = r"(?<![A-Za-z0-9])" + re.escape(variant) + r"(?![A-Za-z0-9])"
                    match = re.search(pattern, sentence, flags=re.IGNORECASE)
                    if match:
                        if (
                            field_name == "dataset"
                            and canonical == "CHAIR"
                            and re.search(r"\b(?:metrics?|scores?)\b", lower)
                            and not re.search(r"\b(?:dataset|benchmark|evaluate(?:d|s)?\s+on)\b", lower)
                        ):
                            continue
                        sentence_matches.append((canonical, match.group(0)))
                        break
            if not sentence_matches:
                if field_name != "dataset":
                    continue
            if not any(marker.lower() in lower for marker in context_markers):
                continue
            dynamic_matches = extract_dynamic_dataset_names(sentence) if field_name == "dataset" else []
            if not sentence_matches and not dynamic_matches:
                continue
            for canonical, raw_value in sentence_matches:
                ref = make_signal_evidence_ref(canonical, raw_value, segment, quote=sentence)
                key = canonical.casefold()
                current = matches_by_key.get(key)
                priority = signal_source_priority(segment.source)
                if current is None or priority > current[0]:
                    matches_by_key[key] = (priority, match_order, ref)
                match_order += 1
            for dynamic_value in dynamic_matches:
                ref = make_signal_evidence_ref(dynamic_value, dynamic_value, segment, quote=sentence)
                key = dynamic_value.casefold()
                current = matches_by_key.get(key)
                priority = signal_source_priority(segment.source)
                if current is None or priority > current[0]:
                    matches_by_key[key] = (priority, match_order, ref)
                match_order += 1
    ordered_matches = sorted(matches_by_key.values(), key=lambda item: item[1])
    evidence_refs = [item[2] for item in ordered_matches]
    if not evidence_refs:
        return "", None
    value = ", ".join(ref.canonical_value for ref in evidence_refs)
    primary_ref = max(
        evidence_refs,
        key=lambda ref: (
            signal_source_priority(ref.source),
            1 if ref.page is not None else 0,
        ),
    )
    evidence = make_signal_evidence(
        field_name,
        value,
        ", ".join(ref.raw_value for ref in evidence_refs),
        EvidenceSegment(
            source=primary_ref.source,
            section=primary_ref.section,
            page=primary_ref.page,
            text=primary_ref.quote,
        ),
        quote=primary_ref.quote,
        evidence_refs=evidence_refs,
    )
    return value, evidence


def extract_dynamic_dataset_names(sentence: str) -> list[str]:
    patterns = [
        r"\b(?:datasets?|benchmarks?|evaluation sets?)\s*(?:include|includes|are|is|used|:)\s*([^.;。！？!?]{2,180})",
        r"\b(?:evaluate|evaluates|evaluated|evaluation)\s+(?:our\s+(?:method|model)\s+)?on\s+([^.;。！？!?]{2,180})",
        r"\bexperiments?\s+(?:are\s+)?(?:conducted|performed|run)\s+on\s+([^.;。！？!?]{2,180})",
    ]
    generic_values = {
        "benchmark",
        "benchmarks",
        "dataset",
        "datasets",
        "evaluation set",
        "evaluation sets",
        "multiple benchmarks",
        "several benchmarks",
        "standard benchmarks",
        "various benchmarks",
        "various datasets",
    }
    resource_pattern = re.compile(
        r"\b(?:gpu|gpus|a100|h100|v100|tpu|cuda|cpu|cpus|gb|gib|"
        r"batch(?:\s+size)?|epochs?|learning\s+rate|parameters?|flops?|"
        r"nodes?|machines?|servers?|workers?)\b",
        flags=re.IGNORECASE,
    )
    values: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, sentence, flags=re.IGNORECASE)
        if not match:
            continue
        raw_value = re.sub(
            r"\b(?:datasets?|benchmarks?|evaluation sets?)\b\s*$",
            "",
            normalize_space(match.group(1)),
            flags=re.IGNORECASE,
        )
        for candidate in re.split(r"\s*(?:,|;|\band\b|&)\s*", raw_value, flags=re.IGNORECASE):
            cleaned = re.sub(r"^(?:the|our|three|two|several|multiple)\s+", "", candidate, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s+(?:dataset|benchmark|evaluation set)$", "", cleaned, flags=re.IGNORECASE)
            cleaned = cleaned.strip(" ()[]{}:,-")
            lower = cleaned.lower()
            if (
                not cleaned
                or lower in generic_values
                or len(cleaned) > 64
                or len(cleaned.split()) > 5
                or not re.search(r"[A-Z0-9-]", cleaned)
                or resource_pattern.search(cleaned)
                or re.fullmatch(r"\d+(?:\.\d+)?\s*[A-Za-z0-9-]+", cleaned)
            ):
                continue
            values.append(cleaned)
    return unique_preserve_order(values)


def extract_baseline_signal_from_segments(
    segments: list[EvidenceSegment],
) -> tuple[str, SignalEvidence | None]:
    patterns = [
        r"\b[Bb]aselines?\s*(?:include|are|:)\s*([^.;。！？!?]{2,360})",
        r"\b[Cc]ompared\s+(?:with|against|to)\s+([^.;。！？!?]{2,140})",
        r"\b[Cc]omparison\s+(?:with|against|to)\s+([^.;。！？!?]{2,140})",
        r"\b[Oo]utperform(?:s|ed|ing)?\s+([^.;。！？!?]{2,120})",
        r"\bvs\.?\s+([^.;。！？!?]{2,100})",
    ]
    for segment in segments:
        if segment.section not in {"abstract", "method", "experiments", "results", "unknown"}:
            continue
        searchable_text = re.sub(r"(?<=\d)\.(?=\d)", "__DECIMAL_DOT__", segment.text)
        for pattern in patterns:
            match = re.search(pattern, searchable_text)
            if match:
                raw_value = truncate_text(match.group(1).replace("__DECIMAL_DOT__", "."), 360)
                baseline_names = extract_baseline_names(raw_value)
                if not baseline_names:
                    continue
                quote = sentence_containing_offset(segment.text, match.start())
                canonical_value = ", ".join(baseline_names)
                value = f"Baseline evidence: {canonical_value}"
                evidence_refs = [
                    make_signal_evidence_ref(
                        baseline_name,
                        baseline_name,
                        segment,
                        quote=quote,
                    )
                    for baseline_name in baseline_names
                ]
                return value, make_signal_evidence(
                    "baseline",
                    value,
                    canonical_value,
                    segment,
                    quote=quote,
                    evidence_refs=evidence_refs,
                )
    return "", None


def extract_claim_signal_from_segments(
    segments: list[EvidenceSegment],
    title: str,
) -> tuple[str, SignalEvidence | None]:
    for segment in segments:
        if segment.section not in {"abstract", "experiments", "results", "conclusion", "unknown"}:
            continue
        for sentence in split_sentences(segment.text):
            if not re.match(r"^\s*claim\s*[:：]\s*\S+", sentence, flags=re.IGNORECASE):
                continue
            value = f"核心 claim 证据：{sentence}"
            return value, make_signal_evidence("claim", value, sentence, segment)
    hit = find_ranked_own_sentence(
        segments,
        purpose="claim",
        allowed_sections={"abstract", "experiments", "results", "conclusion", "unknown"},
    )
    if hit:
        segment, sentence = hit
        value = f"核心 claim 证据：{sentence}"
        return value, make_signal_evidence("claim", value, sentence, segment)
    if "?" in title:
        return "", None
    return "", None


def extract_own_limitation_signal(
    segments: list[EvidenceSegment],
) -> tuple[str, SignalEvidence | None]:
    for segment in segments:
        if segment.section not in {"abstract", "limitations", "results", "conclusion", "unknown"}:
            continue
        sentences = split_sentences(segment.text)
        for index, sentence in enumerate(sentences):
            lower = sentence.lower()
            resolution_statement = bool(
                re.search(
                    r"\b(?:to|we|our (?:method|approach|model))\s+"
                    r"(?:address|overcome|mitigate|solve|resolve|alleviate)\b.{0,60}"
                    r"\b(?:limitation|shortcoming|issue|problem|gap)\b",
                    lower,
                )
            ) or bool(
                re.search(
                    r"\b(?:address|overcome|mitigate|solve|resolve|alleviate)\s+"
                    r"(?:this|the|these|such)\s+(?:limitation|shortcoming|issue|problem|gap)\b",
                    lower,
                )
            )
            owned_statement = any(marker in lower for marker in OWN_LIMITATION_MARKERS)
            if resolution_statement and not owned_statement:
                continue
            explicit_section = segment.section == "limitations" and any(
                marker in lower
                for marker in [
                    "limitation",
                    "limited",
                    "cannot",
                    "we do not",
                    "failure",
                    "fails",
                    "challenge",
                ]
            )
            explicit_limitation = (
                ("limitation" in lower or "limited to" in lower)
                and any(owner in lower for owner in ["our ", "we ", "this work", "this method", "this approach", "this model"])
            )
            explicit_failure = bool(
                re.search(
                    r"\b(?:our (?:method|approach|model|system|framework)|we)\b"
                    r".{0,80}\b(?:fail|fails|failed|cannot|do not)\b",
                    lower,
                )
            )
            if not (explicit_section or owned_statement or explicit_limitation or explicit_failure):
                continue
            quote = sentence
            if is_generic_limitation_lead(sentence):
                follow_ups = [
                    candidate
                    for candidate in sentences[index + 1 : index + 3]
                    if is_specific_limitation_sentence(candidate)
                ]
                if not follow_ups:
                    continue
                quote = normalize_space(" ".join([sentence, *follow_ups]))
            elif not is_specific_limitation_sentence(sentence):
                continue
            value = f"本论文自身局限：{quote}"
            return value, make_signal_evidence("limitation", value, quote, segment, quote=quote)
    return "", None


def is_generic_limitation_lead(sentence: str) -> bool:
    lower = normalize_space(sentence).lower().rstrip(".;:。；：")
    generic_patterns = [
        r"\b(?:our|this) (?:method|approach|model|system|framework|work|paper|research)"
        r".{0,30}\b(?:has|have|faces?|contains?|still has)\b.{0,15}\blimitations?\b$",
        r"\b(?:there are|we identify|we acknowledge)\b.{0,20}\b(?:two|three|several|some)?\s*limitations?\b$",
        r"\b(?:although|while|despite)\b.{0,100}\b(?:has|have|faces?)\b.{0,15}\blimitations?\b$",
        r"\b(?:a|one|the) (?:key |main |important )?limitation remains\b$",
    ]
    return any(re.search(pattern, lower) for pattern in generic_patterns)


def is_specific_limitation_sentence(sentence: str) -> bool:
    lower = normalize_space(sentence).lower()
    if not lower or is_generic_limitation_lead(sentence):
        return False
    if re.match(r"^(?:future work|in future work|we plan to|we will)\b", lower):
        return False
    specific_patterns = [
        r"\blimited (?:to|by|in)\b.{3,}",
        r"\brestricted to\b.{3,}",
        r"\b(?:cannot|can't|unable to|fail(?:s|ed)? to|struggle(?:s|d)? to)\b.{3,}",
        r"\b(?:does not|do not|cannot)\s+(?:support|handle|generalize|transfer|verify|cover|capture)\b.{3,}",
        r"\bonly\s+(?:supports?|covers?|evaluates?|handles?|works? (?:for|on|with))\b.{3,}",
        r"\b(?:suffers?|degrades?|breaks?|fails?)\s+(?:under|on|when|for|with)\b.{3,}",
        r"\b(?:depends?|relies?)\s+(?:on|upon)\b.{3,}",
        r"\b(?:limitation|drawback|weakness|shortcoming)\s+(?:is|comes from|lies in)\b.{3,}",
        r"\bremains? (?:a )?(?:challenge|challenging|unresolved)\b.{3,}",
    ]
    return any(re.search(pattern, lower) for pattern in specific_patterns)


def extract_prior_work_limitation_signal(
    segments: list[EvidenceSegment],
) -> tuple[str, SignalEvidence | None]:
    strong_markers = [
        "suffer",
        "fail",
        "cannot",
        "limitation",
        "limited",
        "inadequate",
        "brittle",
        "shortcut",
        "bias",
        "gap",
        "stateless",
        "from scratch",
        "discard",
    ]
    antecedent_markers = [
        "method",
        "approach",
        "model",
        "framework",
        "system",
        "agent",
        "prior work",
        "previous work",
        "existing work",
    ]
    for segment in segments:
        if segment.section not in {"abstract", "introduction", "related_work", "unknown"}:
            continue
        sentences = split_sentences(segment.text)
        for index, sentence in enumerate(sentences):
            lower = sentence.lower()
            if not any(marker in lower for marker in strong_markers):
                continue
            explicit_owner = any(owner in lower for owner in PRIOR_WORK_MARKERS)
            previous = sentences[index - 1] if index > 0 else ""
            previous_lower = previous.lower()
            contextual_owner = bool(
                previous
                and any(marker in previous_lower for marker in antecedent_markers)
                and (
                    re.search(r"\b(?:they|these|such|those)\b", lower)
                    or lower.startswith(("however", "but ", "yet ", "nevertheless"))
                )
            )
            if explicit_owner or contextual_owner:
                value = f"已有研究不足：{sentence}"
                quote = normalize_space(f"{previous} {sentence}") if contextual_owner else sentence
                return value, make_signal_evidence(
                    "prior_work_limitation",
                    value,
                    sentence,
                    segment,
                    quote=quote,
                )
    return "", None


def find_segment_sentence(
    segments: list[EvidenceSegment],
    markers: list[str],
    *,
    allowed_sections: set[str],
) -> tuple[EvidenceSegment, str] | None:
    for segment in segments:
        if segment.section not in allowed_sections:
            continue
        sentence = find_sentence(segment.text, markers)
        if sentence:
            return segment, sentence
    return None


def find_ranked_own_sentence(
    segments: list[EvidenceSegment],
    *,
    purpose: str,
    allowed_sections: set[str],
) -> tuple[EvidenceSegment, str] | None:
    title = next((segment.text for segment in segments if segment.source == "metadata.title"), "")
    title_identifiers = {
        token.lower()
        for token in re.findall(
            r"(?<![A-Za-z0-9])(?:[A-Z][A-Z0-9-]{3,}|[A-Z][A-Za-z0-9-]*[A-Z][A-Za-z0-9-]*)(?![A-Za-z0-9])",
            title,
        )
        if token.lower()
        not in {
            "this",
            "with",
            "from",
            "vqa",
            "llm",
            "vlm",
            "lvlm",
            "mllm",
            "clip",
        }
    }
    ranked: list[tuple[int, int, EvidenceSegment, str]] = []
    for segment_index, segment in enumerate(segments):
        if segment.section not in allowed_sections:
            continue
        for sentence in split_sentences(segment.text):
            lower = sentence.lower()
            if purpose == "method" and is_method_configuration_sentence(sentence):
                continue
            if re.search(
                r"\bwe\s+(?:first\s+)?(?:introduce|present|provide|describe)\b"
                r".{0,50}\b(?:experimental|implementation)\s+(?:setup|details?|settings?|results?)\b",
                lower,
            ):
                continue
            own_method = bool(
                re.search(
                    r"\b(?:we|this (?:paper|work)|our (?:method|approach|framework|model|system|algorithm))\b"
                    r".{0,80}\b(?:propose|introduce|present|develop|design|build|construct|use|employ|consist|comprise)",
                    lower,
                )
            ) or bool(
                re.search(
                    r"\bwe\s+(?:propose|introduce|present|develop|design|build|construct)\b",
                    lower,
                )
            )
            named_method = any(
                re.search(r"(?<![a-z0-9])" + re.escape(identifier) + r"(?![a-z0-9])", lower)
                and re.search(
                    r"\b(?:decomposes?|allocates?|retrieves?|suppresses?|aligns?|optimizes?|"
                    r"intervenes?|aggregates?|routes?|updates?|stores?|selects?|generates?|"
                    r"adapts?|enables?|consists?|comprises?)\b",
                    lower,
                )
                for identifier in title_identifiers
            )
            own_method = own_method or named_method
            own_claim = bool(
                re.search(
                    r"\bwe\s+(?:show|demonstrate|find|reveal|observe|achieve|outperform)\b",
                    lower,
                )
            ) or bool(
                re.search(
                    r"\bour (?:method|approach|framework|model|system|algorithm)\b"
                    r".{0,100}\b(?:improves?|outperforms?|achieves?|reduces?|mitigates?)\b",
                    lower,
                )
            )
            benchmark_ownership = bool(
                re.search(
                    r"\bwe\s+(?:introduce|present|build|construct|release|develop)\b"
                    r".{0,120}\b(?:benchmark|dataset|evaluation (?:protocol|suite|set))\b",
                    lower,
                )
            )
            prior_work = is_prior_work_sentence(sentence)
            if purpose == "method":
                relevant = own_method and not benchmark_ownership
            elif purpose == "benchmark":
                relevant = benchmark_ownership
            else:
                relevant = own_claim
            if not relevant or prior_work:
                continue
            score = 8
            if segment.section == "method" and purpose == "method":
                score += 5
            if segment.section in {"results", "conclusion"} and purpose == "claim":
                score += 5
            if segment.section == "abstract":
                score += 3
            if purpose == "method":
                if re.search(r"\b(?:propose|introduce|develop|design)\b", lower):
                    score += 4
                elif re.search(r"\b(?:present|build|construct)\b", lower):
                    score += 3
                if named_method:
                    score += 5
                if re.search(
                    r"\b(?:decomposes?|allocates?|retrieves?|suppresses?|aligns?|optimizes?|"
                    r"intervenes?|aggregates?|routes?|updates?|stores?|selects?|generates?|adapts?|enables?)\b",
                    lower,
                ):
                    score += 4
                if re.search(r"\b(?:use|employ)\b", lower):
                    score -= 2
                if any(
                    re.search(r"(?<![a-z0-9])" + re.escape(identifier) + r"(?![a-z0-9])", lower)
                    for identifier in title_identifiers
                ):
                    score += 6
            if re.search(r"\[[0-9,\s-]+\]", sentence):
                score -= 2
            limit = 420 if purpose == "claim" else 320
            ranked.append((score, -segment_index, segment, truncate_text(sentence, limit)))
    if not ranked:
        return None
    _score, _order, segment, sentence = max(ranked, key=lambda item: (item[0], item[1]))
    return segment, sentence


def is_method_configuration_sentence(sentence: str) -> bool:
    lower = normalize_space(sentence).lower()
    configuration_patterns = [
        r"\b(?:backbone|resolution|image size|input size|embedding dimension|hidden size)\b",
        r"\b(?:batch size|learning rate|weight decay|epochs?|warmup|optimizer)\b",
        r"\b(?:parameters?|flops?|fps|a100|h100|v100|tpu|cuda)\b",
        r"\b(?:we use|we employ)\b.{0,80}\b(?:as (?:the )?(?:backbone|encoder|decoder|baseline)|for comparison)\b",
        r"\b(?:respectively|pre-?trained|initialized from)\b",
    ]
    if any(re.search(pattern, lower) for pattern in configuration_patterns):
        return True
    numeric_tokens = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:[A-Za-z]+)?", sentence)
    return len(numeric_tokens) >= 4 and not re.search(
        r"\b(?:improve|reduce|outperform|achieve|gain)\b",
        lower,
    )


def is_prior_work_sentence(sentence: str) -> bool:
    lower = normalize_space(sentence).lower()
    prior_subjects = [
        "existing method",
        "existing approach",
        "previous method",
        "previous approach",
        "prior work",
        "prior method",
        "other method",
        "several approach",
        "recent method",
        "current method",
        "conventional method",
    ]
    background_openers = [
        "although several",
        "although existing",
        "while existing",
        "despite recent",
        "methods such as",
        "approaches such as",
    ]
    return any(marker in lower for marker in [*prior_subjects, *background_openers])


def extract_baseline_names(raw_value: str) -> list[str]:
    normalized = normalize_space(raw_value)
    normalized = re.sub(r"\bLLaV\s+A(?=[-\s]?\d|\b)", "LLaVA", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\[[0-9,\s-]+\]", " ", normalized)
    found: list[tuple[int, str]] = []
    occupied: list[tuple[int, int]] = []
    aliases = sorted(
        (
            (canonical, alias)
            for canonical, variants in BASELINE_ALIASES.items()
            for alias in variants
        ),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    for canonical, alias in aliases:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9.-])"
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            if any(start < match.end() and match.start() < end for start, end in occupied):
                continue
            found.append((match.start(), canonical))
            occupied.append((match.start(), match.end()))

    dataset_keys = {name.lower() for name in DATASET_NAMES}
    generic_tokens = {
        "baseline",
        "baselines",
        "method",
        "methods",
        "model",
        "models",
        "accuracy",
        "margin",
        "score",
        "state-of-the-art",
        "vlm",
        "vlms",
        "lvlm",
        "lvlms",
    }
    for match in re.finditer(
        r"(?<![A-Za-z0-9])(?:[A-Z]{2,}[A-Za-z0-9.-]*|[A-Z][a-z]+[A-Z][A-Za-z0-9.-]*)(?![A-Za-z0-9])",
        normalized,
    ):
        if any(start < match.end() and match.start() < end for start, end in occupied):
            continue
        token = match.group(0).strip(".,:;()[]")
        lower = token.lower()
        if (
            not token
            or lower in dataset_keys
            or lower in generic_tokens
            or re.fullmatch(r"\d+(?:\.\d+)?", token)
        ):
            continue
        found.append((match.start(), token))
    return unique_preserve_order([value for _offset, value in sorted(found, key=lambda item: item[0])])[:8]


def make_signal_evidence(
    field_name: str,
    canonical_value: str,
    raw_value: str,
    segment: EvidenceSegment,
    *,
    quote: str | None = None,
    evidence_refs: list[SignalEvidenceRef] | None = None,
) -> SignalEvidence:
    refs = evidence_refs or [
        make_signal_evidence_ref(
            canonical_value,
            raw_value,
            segment,
            quote=quote,
        )
    ]
    has_validation_error = bool(
        any(ref.validation_errors for ref in refs)
    )
    sources = {ref.source for ref in refs}
    availability = (
        "invalid"
        if has_validation_error
        else "verified"
        if refs and sources == {"pdf.full_text"}
        else "partial"
    )
    return SignalEvidence(
        field=field_name,
        canonical_value=canonical_value,
        raw_value=raw_value,
        source=segment.source,
        section=segment.section,
        page=segment.page,
        quote=truncate_text(quote or raw_value, 360),
        confidence=(
            "high"
            if segment.source == "pdf.full_text"
            else "medium"
            if segment.source == "metadata.abstract"
            else "low"
        ),
        validation_errors=[],
        evidence_refs=refs,
        availability=availability,
    )


def make_signal_evidence_ref(
    canonical_value: str,
    raw_value: str,
    segment: EvidenceSegment,
    *,
    quote: str | None = None,
) -> SignalEvidenceRef:
    return SignalEvidenceRef(
        canonical_value=canonical_value,
        raw_value=raw_value,
        source=segment.source,
        section=segment.section,
        page=segment.page,
        quote=truncate_text(quote or raw_value, 360),
        confidence=(
            "high"
            if segment.source == "pdf.full_text"
            else "medium"
            if segment.source == "metadata.abstract"
            else "low"
        ),
        validation_errors=[],
    )


def signal_source_priority(source: str) -> int:
    if source == "pdf.full_text":
        return 3
    if source == "metadata.abstract":
        return 2
    if source == "metadata.title":
        return 1
    return 0


def sentence_containing_offset(text: str, offset: int) -> str:
    for sentence in split_sentences(text):
        start = text.find(sentence)
        if start <= offset <= start + len(sentence):
            return truncate_text(sentence, 360)
    return truncate_text(text, 360)


def infer_contribution_type(title: str, abstract: str, paper_text: str, venue: str) -> tuple[str, str]:
    """Classify the contribution from an explicit claim, not incidental citations.

    Full papers routinely contain phrases such as "we review related work" or
    cite survey papers. Those mentions must not turn an analysis or benchmark
    paper into a survey. Survey classification therefore needs a title signal
    or an explicit self-description near the abstract/introduction.
    """
    title_text = normalize_space(title)
    abstract_text = normalize_space(abstract)
    body_text = normalize_space(paper_text)
    title_lower = title_text.lower()
    survey_title_patterns = [
        r"\b(?:a|an|the)?\s*(?:comprehensive\s+)?survey\b",
        r"\b(?:a|an|the)?\s*(?:systematic\s+)?review\b",
        r"\boverview\b",
        r"\btaxonomy\b",
    ]
    for pattern in survey_title_patterns:
        if re.search(pattern, title_lower):
            return "survey", f"标题证据：{truncate_text(title_text)}"

    survey_self_description_patterns = [
        r"\b(?:this (?:paper|work)|we)\s+(?:present|provide|conduct|offer|develop|introduce)\s+(?:a|an|the)?\s*(?:comprehensive\s+|systematic\s+)?(?:survey|review|overview|taxonomy)\b",
        r"\b(?:this (?:paper|work)|we)\s+(?:survey|review)\s+(?:the\s+)?(?:literature|field|research|studies)\b",
        r"\b(?:a|an)\s+(?:comprehensive\s+|systematic\s+)?(?:survey|review)\s+of\b",
    ]
    for source_name, source_text in (("摘要", abstract_text), ("正文", body_text[:12000])):
        for sentence in split_sentences(source_text):
            if any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in survey_self_description_patterns):
                return "survey", f"{source_name}证据：{truncate_text(sentence)}"

    evidence_sources = [abstract_text, body_text]
    title_type_patterns = [
        ("benchmark", [r"\bbenchmark\b", r"\bdataset\b"]),
        (
            "analysis",
            [
                r"\banalysis\b",
                r"\bunderstanding\b",
                r"\binvestigat(?:e|ing|ion)\b",
                r"\bcharacteriz",
                r"\bcircuits?\b",
                r"\bwhat makes\b",
            ],
        ),
        ("system", [r"\bagent\b", r"\bworkflow\b", r"\bsystem\b"]),
    ]
    for contribution_type, patterns in title_type_patterns:
        if any(re.search(pattern, title_lower) for pattern in patterns):
            evidence = find_owned_contribution_evidence(evidence_sources, contribution_type)
            return contribution_type, evidence or f"标题证据：{truncate_text(title_text)}"

    method_evidence = find_owned_contribution_evidence(evidence_sources, "method")
    benchmark_evidence = find_owned_contribution_evidence(evidence_sources, "benchmark")
    analysis_evidence = find_owned_contribution_evidence(evidence_sources, "analysis")
    system_evidence = find_owned_contribution_evidence(evidence_sources, "system")
    if method_evidence:
        return "method", method_evidence
    if benchmark_evidence:
        return "benchmark", benchmark_evidence
    if analysis_evidence:
        return "analysis", analysis_evidence
    if system_evidence:
        return "system", system_evidence
    return "unknown", "未发现可定位的贡献类型证据。"


def find_owned_contribution_evidence(texts: list[str], contribution_type: str) -> str:
    patterns = {
        "method": [
            r"\bwe\s+(?:propose|introduce|present|develop|design)\b"
            r"(?![^.!?]{0,100}\b(?:benchmark|dataset|evaluation (?:protocol|suite|set))\b)",
            r"\bour\s+(?:method|approach|framework|model|algorithm|intervention)\b",
        ],
        "benchmark": [
            r"\bwe\s+(?:introduce|present|build|construct|release|develop)\b"
            r".{0,120}\b(?:benchmark|dataset|evaluation (?:protocol|suite|set))\b",
        ],
        "analysis": [
            r"\bwe\s+(?:analyze|analyse|investigate|characterize|study|examine)\b",
            r"\bthis (?:paper|work)\s+(?:analyzes|analyses|investigates|characterizes|studies|examines)\b",
        ],
        "system": [
            r"\bwe\s+(?:build|develop|introduce|present)\b.{0,100}\b(?:agent|workflow|system)\b",
            r"\bour\s+(?:agent|workflow|system)\b",
        ],
    }
    for text in texts:
        for sentence in split_sentences(text):
            if is_prior_work_sentence(sentence):
                continue
            if any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in patterns[contribution_type]):
                return f"贡献证据：{truncate_text(sentence)}"
    return ""


def find_first_evidence_sentence(texts: list[str], markers: list[str]) -> str:
    for text in texts:
        sentence = find_sentence(text, markers)
        if sentence:
            return f"贡献证据：{sentence}"
    return ""


def extract_task_signal(title: str, abstract: str, text: str, contribution_type: str) -> str:
    lower = text.lower()
    if contribution_type == "survey":
        return f"围绕 `{title}` 的文献图谱、问题分类或研究脉络梳理"
    match = re.search(r"\bfor\s+([^:.;!?]{4,120})", title, flags=re.IGNORECASE)
    if match:
        return truncate_text(match.group(1))
    if "hallucination" in lower or "幻觉" in lower:
        return "vision-language model hallucination 的检测、评估或缓解"
    if "visual grounding" in lower or "grounded" in lower or "evidence" in lower or "faithful" in lower:
        return "模型输出是否与可验证视觉证据一致"
    if "benchmark" in lower or "evaluation" in lower:
        return "benchmark/evaluation 是否真实测到目标 AI 能力"
    if "super-resolution" in lower or "image restoration" in lower:
        return "图像恢复/超分辨率中的质量提升与可部署性问题"
    if "agent" in lower or "workflow" in lower:
        return "科研 agent 的流程规划、工具调用与结果追踪"
    return infer_focus(title, abstract)


def extract_task_signal_from_segments(
    segments: list[EvidenceSegment],
    title: str,
    abstract: str,
    text: str,
    contribution_type: str,
) -> tuple[str, SignalEvidence | None]:
    value = extract_task_signal(title, abstract, text, contribution_type)
    title_terms = {
        token
        for token in re.findall(r"[a-z][a-z0-9-]{3,}", normalize_space(title).lower())
        if token not in {"with", "from", "using", "towards", "through"}
    }
    ranked: list[tuple[int, int, EvidenceSegment, str]] = []
    for segment_index, segment in enumerate(segments):
        if segment.section in {"references", "related_work", "front_matter"}:
            continue
        for sentence in split_sentences(segment.text):
            lower = sentence.lower()
            explicit_task = bool(
                re.search(
                    r"\bwe\s+(?:study|investigate|analyze|analyse|address|tackle|evaluate|"
                    r"examine|focus on|aim to|seek to)\b",
                    lower,
                )
                or re.search(
                    r"\bthis (?:paper|work)\s+(?:studies|investigates|analyzes|analyses|"
                    r"addresses|evaluates|examines|focuses on)\b",
                    lower,
                )
                or re.search(r"\b(?:task|problem|goal|objective)\s+(?:is|of this work|we address)\b", lower)
            )
            overlap = len(
                title_terms
                & {
                    token
                    for token in re.findall(r"[a-z][a-z0-9-]{3,}", lower)
                }
            )
            title_for_task = segment.source == "metadata.title" and bool(
                re.search(r"\bfor\b", lower)
            )
            if not explicit_task and overlap < 2 and not title_for_task:
                continue
            score = signal_source_priority(segment.source) * 4
            if explicit_task:
                score += 5
            if segment.section in {"introduction", "abstract"}:
                score += 2
            if title_for_task:
                score += 2
            ranked.append((score, -segment_index, segment, sentence))
    if not ranked:
        return value, None
    _score, _order, segment, sentence = max(ranked, key=lambda item: (item[0], item[1]))
    return value, make_signal_evidence("task", value, sentence, segment, quote=sentence)


def extract_method_signal(text: str, contribution_type: str) -> str:
    if contribution_type == "survey":
        return "综述/调研型贡献：主要方法应是组织、比较和归纳已有文献，而不是提出可训练模型。"
    sentence = find_sentence(text, METHOD_MARKERS)
    if sentence:
        return f"方法证据：{sentence}"
    if contribution_type == "benchmark":
        benchmark_sentence = find_sentence(text, ["benchmark", "dataset", "evaluation", "protocol"])
        if benchmark_sentence:
            return f"评测/benchmark 构造方法：{benchmark_sentence}"
    return insufficient("摘要/正文中没有抽到明确方法机制、模型结构、训练策略或评测协议")


def extract_claim_signal(text: str, title: str) -> str:
    sentence = find_sentence(text, CLAIM_MARKERS)
    if sentence:
        return f"核心 claim 证据：{sentence}"
    if "?" in title:
        return insufficient("标题更像研究问题，摘要/正文未给出明确结论型 claim")
    return insufficient("未发现 we show/demonstrate/outperform/improve 等明确 claim 句")


def extract_limitation_signal(text: str) -> str:
    sentence = find_sentence(text, LIMITATION_MARKERS)
    if sentence:
        return f"显式或隐含不足：{sentence}"
    return insufficient("摘要/正文未明确说明已有方法不足或 failure mode")


def extract_named_signal(text: str, names: list[str], missing_reason: str) -> str:
    found: list[str] = []
    for name in names:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(name)
    if found:
        return ", ".join(unique_preserve_order(found))
    return insufficient(missing_reason)


def extract_named_signal_priority(texts: list[str], names: list[str], missing_reason: str) -> str:
    for text in texts:
        if not normalize_space(text):
            continue
        signal = extract_named_signal(text, names, missing_reason)
        if has_signal(signal):
            return signal
    return insufficient(missing_reason)


def extract_baseline_signal(text: str) -> str:
    normalized = normalize_space(text)
    if not normalized:
        return insufficient("摘要/正文未发现 baseline、comparison 或对照方法")
    patterns = [
        r"\b[Bb]aselines?\s*(?:include|are|:)\s*([^.;。！？!?]{2,160})",
        r"\b[Cc]ompared\s+(?:with|against|to)\s+([^.;。！？!?]{2,140})",
        r"\b[Cc]omparison\s+(?:with|against|to)\s+([^.;。！？!?]{2,140})",
        r"\b[Oo]utperform(?:s|ed|ing)?\s+([^.;。！？!?]{2,120})",
        r"\bvs\.?\s+([^.;。！？!?]{2,100})",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return f"Baseline evidence: {truncate_text(match.group(1), 180)}"
    return insufficient("未发现 Baseline:, compared with, outperform, vs. 或 comparison 等对照信号")


def find_sentence(text: str, markers: list[str]) -> str:
    for sentence in split_sentences(text):
        lower = sentence.lower()
        if any(marker.lower() in lower for marker in markers):
            return truncate_text(sentence)
    return ""


def split_sentences(text: str) -> list[str]:
    normalized = normalize_space(text)
    if not normalized:
        return []
    sentences = re.split(r"(?<=[.!?。！？])\s+", normalized)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def truncate_text(value: str, limit: int = 260) -> str:
    normalized = normalize_space(value)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def insufficient(reason: str) -> str:
    return f"{INSUFFICIENT_PREFIX}：{reason}。"


def has_signal(value: str) -> bool:
    normalized = normalize_space(value)
    return bool(normalized) and not normalized.startswith(INSUFFICIENT_PREFIX)


def has_verified_signals(signals: PaperSignals, *fields: str) -> bool:
    return all(
        (evidence := signals.signal_evidence.get(field_name)) is not None
        and evidence.availability == "verified"
        and not evidence.validation_errors
        for field_name in fields
    )


def has_any_verified_signal(signals: PaperSignals) -> bool:
    return any(
        evidence.availability == "verified" and not evidence.validation_errors
        for evidence in signals.signal_evidence.values()
    )


def academic_signal_text(value: str) -> str:
    """Return research-facing content without extractor/debug prefixes."""
    normalized = normalize_space(value)
    if (
        not normalized
        or normalized.startswith(INSUFFICIENT_PREFIX)
        or normalized.startswith(("无法判断", "未识别", "未发现"))
    ):
        return ""
    return re.sub(
        r"^(?:方法证据|核心 claim 证据|本论文自身局限|已有研究不足|贡献证据|Baseline evidence)\s*[：:]\s*",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()


def primary_metric_text(value: str) -> str:
    metrics = [item.strip() for item in academic_signal_text(value).split(",") if item.strip()]
    for preferred in [
        "task success rate",
        "grounding accuracy",
        "hallucination rate",
        "accuracy",
        "F1",
    ]:
        if any(metric.lower() == preferred.lower() for metric in metrics):
            return preferred
    return metrics[0] if metrics else ""


def build_research_problem_section(
    title: str,
    year: str,
    venue: str,
    signals: PaperSignals,
    context: str,
) -> str:
    task = academic_signal_text(signals.task) or title
    method = academic_signal_text(signals.method)
    claim = academic_signal_text(signals.claim)
    paragraphs = [
        f"`{title}`（{year}，{venue}）研究 `{task}`。",
    ]
    if method:
        paragraphs.append(f"论文提出的核心方案是：{method}")
    if claim:
        paragraphs.append(f"作者报告的主要结论是：{claim}")
    elif context:
        paragraphs.append(f"已定位的研究背景为：{summarize_context(context)}")
    return "\n\n".join(paragraphs)


def build_prior_work_section(signals: PaperSignals) -> str:
    prior_limitation = academic_signal_text(signals.prior_work_limitation)
    own_limitation = academic_signal_text(signals.limitation)
    dataset = academic_signal_text(signals.dataset)
    metric = primary_metric_text(signals.metric)
    baseline = academic_signal_text(signals.baseline)
    paragraphs: list[str] = []
    if prior_limitation:
        paragraphs.append(f"已有工作的关键不足是：{prior_limitation}")
    if dataset and metric:
        experiment = f"论文在 `{dataset}` 上使用 `{metric}` 评估"
        if baseline:
            experiment += f"，对照 `{baseline}`"
        paragraphs.append(f"{experiment}。")
    if own_limitation:
        paragraphs.append(f"作者明确留下的后续边界是：{own_limitation}")
    return "\n\n".join(paragraphs)


def build_author_reasoning_section(signals: PaperSignals) -> str:
    task = academic_signal_text(signals.task)
    method = academic_signal_text(signals.method)
    claim = academic_signal_text(signals.claim)
    prior_limitation = academic_signal_text(signals.prior_work_limitation)
    if not method or not has_verified_signals(signals, "method"):
        return ""
    starting_point = prior_limitation or f"`{task}` 中尚未被稳定解决的流程问题"
    ending = f"，并以“{claim}”作为待验证结果" if claim else ""
    return (
        "推断性重建（非作者原话）：研究者先识别到"
        f"“{starting_point}”；随后把这一问题转化为可操作的方法设计——{method}{ending}。"
        "这条路径只用于解释问题、机制与实验之间的关系，最终仍应以原文论证顺序为准。"
    )


def build_intuition_section(signals: PaperSignals) -> str:
    task = academic_signal_text(signals.task)
    method = academic_signal_text(signals.method)
    dataset = academic_signal_text(signals.dataset)
    metric = primary_metric_text(signals.metric)
    baseline = academic_signal_text(signals.baseline)
    claim = academic_signal_text(signals.claim)
    if not method or not has_verified_signals(signals, "method"):
        return ""
    intuition = f"核心直觉是用 `{method}` 处理 `{task}`"
    if dataset and metric:
        intuition += f"，再在 `{dataset}` 上以 `{metric}` 进行检验"
    if baseline:
        intuition += f"，并与 `{baseline}` 比较"
    if claim:
        intuition += f"，从而验证“{claim}”"
    return f"{intuition}。"


def render_signal_summary(signals: PaperSignals) -> str:
    locations = ", ".join(
        f"{field}@{evidence.section or 'unknown'}"
        + (f":p{evidence.page}" if evidence.page is not None else "")
        for field, evidence in signals.signal_evidence.items()
    )
    return (
        f"task={signals.task}; method={signals.method}; dataset={signals.dataset}; "
        f"metric={signals.metric}; baseline={signals.baseline}; claim={signals.claim}; limitation={signals.limitation}; "
        f"prior_work_limitation={signals.prior_work_limitation}; type={signals.contribution_type}; "
        f"contribution_evidence={signals.contribution_evidence}; evidence_locations={locations or 'none'}"
    )


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def infer_focus(title: str, context: str) -> str:
    text = f"{title} {context}".lower()
    if "hallucination" in text or "幻觉" in text:
        return "vision-language model hallucination 是否能被更细粒度、更证据化地评测"
    if "agent" in text or "workflow" in text:
        return "科研 agent 的任务流程是否能被拆解、追踪和可靠复用"
    if "ground" in text or "evidence" in text or "faithful" in text:
        return "模型输出是否真正依赖可验证证据，而不是依赖语言先验或数据捷径"
    if "benchmark" in text or "evaluation" in text:
        return "现有 benchmark 是否真实测到了目标能力，而不是测到数据偏差或模板捷径"
    return "论文所定义的 AI 能力或失败模式是否能被清晰建模、测量和验证"


def infer_limitation(focus: str) -> str:
    if "hallucination" in focus or "证据" in focus:
        return "最终答案正确率无法区分真实视觉理解和偶然猜对"
    if "benchmark" in focus:
        return "benchmark 可能混入数据偏差、模板线索和不真实的分布假设"
    if "agent" in focus:
        return "只展示最终回答，缺少 plan、tool call、artifact 和失败恢复记录"
    return "评价目标、实验设置和失败模式之间缺少可验证映射"


def infer_weakest_assumption(focus: str) -> str:
    if "hallucination" in focus or "证据" in focus:
        return "最脆弱假设：标注或指标能代表模型真实使用的视觉证据。若模型答对但证据链错误，论文的核心判断会被削弱。"
    if "benchmark" in focus:
        return "最脆弱假设：benchmark 分布足以代表真实任务分布。若模型只利用模板或数据偏差，结论会高估能力。"
    if "agent" in focus:
        return "最脆弱假设：任务流程可被固定 schema 覆盖。若真实科研任务需要频繁改写目标，固定流程会变得僵硬。"
    return "最脆弱假设：论文定义的评价对象和真实目标能力一致。只要二者错位，实验结论就会变得不可泛化。"


def build_method_pipeline_section(signals: PaperSignals) -> str:
    task = academic_signal_text(signals.task)
    method = academic_signal_text(signals.method)
    dataset = academic_signal_text(signals.dataset)
    metric = primary_metric_text(signals.metric)
    baseline = academic_signal_text(signals.baseline)
    claim = academic_signal_text(signals.claim)
    if not method or not has_verified_signals(signals, "method"):
        return ""
    input_text = f"`{dataset}` 中面向 `{task}` 的任务实例" if dataset else f"面向 `{task}` 的任务实例"
    output_parts = []
    if metric:
        output_parts.append(f"用 `{metric}` 评价结果")
    if baseline:
        output_parts.append(f"与 `{baseline}` 对照")
    if claim:
        output_parts.append(f"检验“{claim}”")
    output_text = "，".join(output_parts) or "输出论文定义的任务结果"
    return (
        f"输入：{input_text}。\n"
        f"处理：{method}\n"
        f"输出与验证：{output_text}。"
    )


def build_experiment_logic_section(signals: PaperSignals) -> str:
    if signals.contribution_type == "survey":
        if not has_any_verified_signal(signals):
            return ""
        return (
            "这篇论文更像 survey/review，不适合按方法论文写“复现实验”。"
            "实验层面应改为验证它的文献图谱是否完整：它覆盖了哪些范式，遗漏了哪些近三年关键 baseline，"
            "以及分类轴是否能帮助研究者定位真实 gap。"
        )
    task = academic_signal_text(signals.task)
    claim = academic_signal_text(signals.claim)
    dataset = academic_signal_text(signals.dataset)
    metric = primary_metric_text(signals.metric)
    baseline = academic_signal_text(signals.baseline)
    missing = [
        field
        for field, value in [
            ("claim", claim),
            ("dataset", dataset),
            ("metric", metric),
            ("baseline", baseline),
        ]
        if not value
    ]
    if missing or not has_verified_signals(signals, "claim", "dataset", "metric", "baseline"):
        return ""
    return (
        f"研究问题：`{task}` 是否被所提方法真正改善。\n"
        f"实验设置：在 `{dataset}` 上使用 `{metric}`，并与 `{baseline}` 对照。\n"
        f"待验证主张：{claim}\n"
        "判断标准：结果应在主要对照、不同任务难度或消融设置下保持一致，且提升不能仅由样本选择或评测设置造成。"
    )


def build_takeaways_section(signals: PaperSignals, focus: str) -> str:
    if signals.contribution_type == "survey":
        if not has_any_verified_signal(signals):
            return ""
        return (
            "Take-away 不是复现某个模型，而是提取它的文献组织价值：它如何划分问题空间、哪些范式被认为重要、"
            "哪些失败模式仍未解决。读这类论文时要特别检查 survey 的覆盖面和分类轴是否有明确纳入规则。"
        )
    task = academic_signal_text(signals.task)
    method = academic_signal_text(signals.method)
    dataset = academic_signal_text(signals.dataset)
    metric = primary_metric_text(signals.metric)
    baseline = academic_signal_text(signals.baseline)
    claim = academic_signal_text(signals.claim)
    missing = [
        name
        for name, value in [
            ("method", method),
            ("claim", claim),
            ("dataset", dataset),
            ("metric", metric),
        ]
        if not value
    ]
    if missing or not has_verified_signals(signals, "method", "claim", "dataset", "metric"):
        return ""
    return (
        f"任务：`{task}`。\n"
        f"方法：{method}\n"
        f"主要结论：{claim}\n"
        f"实验锚点：`{dataset}`、`{metric}`"
        + (f"、对照 `{baseline}`。" if baseline else "。")
        + f"\n研究迁移时，应围绕 `{focus}` 检查结论的适用边界，而不是只复述平均指标。"
    )


def build_weakest_assumption(focus: str, signals: PaperSignals) -> str:
    claim = academic_signal_text(signals.claim)
    dataset = academic_signal_text(signals.dataset)
    metric = primary_metric_text(signals.metric)
    limitation = academic_signal_text(signals.limitation)
    missing = [name for name, value in [("claim", claim), ("dataset", dataset), ("metric", metric)] if not value]
    if not missing and has_verified_signals(signals, "claim", "dataset", "metric"):
        if not limitation:
            return (
                f"推断性弱假设（作者未明确陈述 limitation）：`{metric}` 在 `{dataset}` 上"
                f"足以支持“{claim}”。若该指标受样本选择、任务分布或评测协议影响，核心主张会被削弱。"
                "这是由 claim + dataset + metric 原文信号推出的待验证假设，不是作者已经承认的局限。"
            )
        return (
            f"推断性弱假设：作者指出“{limitation}”。这可能使 `{metric}` 在 `{dataset}` 上"
            f"不足以支持“{claim}”，仍需结合对应实验和失败案例复核。"
        )
    return ""


def build_math_section(focus: str, signals: PaperSignals) -> str:
    task = academic_signal_text(signals.task)
    method = academic_signal_text(signals.method)
    metric = primary_metric_text(signals.metric)
    claim = academic_signal_text(signals.claim)
    verified_method = bool(method) and has_verified_signals(signals, "method")
    verified_evaluation = bool(task and metric and claim) and has_verified_signals(
        signals,
        "task",
        "metric",
        "claim",
    )
    if not verified_method and not verified_evaluation:
        return ""
    if "agent" in focus and verified_method:
        return (
            f"这项工作以系统流程为核心，未把贡献建立在新的损失函数或定理上。可将 `{task}` 表示为状态转移："
            "历史任务轨迹 → 结构化程序性记忆 → 按任务或子任务检索 → 分配给协调器与任务智能体 → 执行并评价。"
            f"方法机制是：{method}"
            + (f" 主要实验量化指标为 `{metric}`。" if metric else "")
        )
    if verified_evaluation and (
        "hallucination" in focus or "证据" in focus or "benchmark" in focus or metric
    ):
        return (
            f"理论上先把论文目标拆成三个变量：任务对象 `{task}`、评价指标 `{metric}`、核心 claim `{claim}`。"
            "0 基础可以这样理解：平均准确率像总成绩，证据一致性、failure rate 或分层指标像解题过程；"
            "总成绩高但过程错，说明模型能力判断不可靠。若论文有公式，重点检查公式是否真的对应它声称要测的能力。"
        )
    return ""


def build_minimal_reproduction(signals: PaperSignals, title: str) -> str:
    if signals.contribution_type == "survey":
        if not has_any_verified_signal(signals):
            return ""
        return (
            "这篇论文更像 survey/review，不应作为一周复现实验 anchor。"
            "更合适的一周任务是：用它的分类轴抽取 10 篇候选方法/benchmark 论文，检查是否遗漏近三年关键 baseline，"
            "并产出一个可复现论文图谱，而不是复现模型性能。"
        )
    claim = academic_signal_text(signals.claim)
    dataset = academic_signal_text(signals.dataset)
    metric = primary_metric_text(signals.metric)
    baseline = academic_signal_text(signals.baseline)
    missing = [
        name
        for name, value in [("claim", claim), ("dataset", dataset), ("metric", metric), ("baseline", baseline)]
        if not value
    ]
    if missing or not has_verified_signals(signals, "claim", "dataset", "metric", "baseline"):
        return ""
    return (
        "状态：可进入最小复现设计\n"
        f"待检验主张：{claim}\n"
        f"最小数据：从 `{dataset}` 中抽取与核心现象直接相关的小规模子集。\n"
        f"对照方法：{baseline}；同时保留一个无机制或 no-op 对照。\n"
        f"评价指标：记录论文指标 `{metric}`，并增加能够揭示失败模式的辅助指标。\n"
        "步骤：1）复现输入与环境；2）运行对照；3）运行论文方法；4）按任务难度或失败类型分层统计；5）人工复核代表性失败样本。\n"
        f"成功标准：在小规模设置下重现 `{title}` 的核心现象，并定位至少一类稳定失败模式。\n"
        "失败标准：结果高度依赖样本挑选、随机性或未公开设置，无法稳定支持论文主张。"
    )


def build_counterexample(signals: PaperSignals, focus: str) -> str:
    claim = academic_signal_text(signals.claim)
    dataset = academic_signal_text(signals.dataset)
    metric = primary_metric_text(signals.metric)
    if claim and dataset and metric and has_verified_signals(signals, "claim", "dataset", "metric"):
        return (
            f"待检验主张是“{claim}”。围绕 `{dataset}` 构造任务目标不变、但难度、历史轨迹质量或执行环境发生变化的样本，"
            f"继续用 `{metric}` 评估。若优势在这些设置中消失，可据此界定该主张的泛化边界。"
        )
    return ""


def build_follow_up_idea(signals: PaperSignals, focus: str) -> str:
    claim = academic_signal_text(signals.claim)
    dataset = academic_signal_text(signals.dataset)
    metric = primary_metric_text(signals.metric)
    limitation = academic_signal_text(signals.limitation)
    if (
        not claim
        or not dataset
        or not metric
        or not has_verified_signals(signals, "claim", "dataset", "metric")
    ):
        return ""
    if not limitation:
        return (
            f"Follow-up（待验证推断）：固定原文主张“{claim}”，在 `{dataset}` 中构造"
            f"分布偏移或关键机制失效的切片，并继续用 `{metric}` 与反例指标联合评估。"
            "作者未明确陈述 limitation，因此这不是论文结论；第一步必须先验证该失败切片是否稳定存在。"
        )
    return (
        f"Follow-up（推断）：从作者指出的边界“{limitation}”出发，围绕 `{dataset}` 中的“{claim}”"
        f"设计一个能暴露该限制的评测切片，并继续用 `{metric}` 检查它是否成立。"
        "这是一条待验证推断，而不是论文已经证明的结论；下一步需要先在原文实验设置内验证该限制是否稳定出现。"
    )


def render_card_markdown(
    card: DeepPaperCard,
    paper: dict[str, Any],
    full_text: dict[str, Any] | None = None,
) -> str:
    provenance = full_text or {}
    boundary = "" if card.evidence_level == "full_text" else evidence_boundary_sentence(card.evidence_level)
    header = [
        f"# {card_markdown_title(card.evidence_level)}",
        f"Paper: {card.paper_title}",
        f"Authors: {paper.get('authors') or 'unknown'}",
        f"Venue/Year: {paper.get('venue') or paper.get('source') or 'unknown'} / {paper.get('year') or 'unknown'}",
        f"Evidence level: {card.evidence_level}",
        f"Evidence verified: {str(card.evidence_qualification.verified).lower()}",
        f"Evidence source origin: {card.evidence_qualification.source_origin or 'none'}",
        f"Evidence qualification reason: {card.evidence_qualification.reason}",
        f"Full-text status: {provenance.get('status') or 'not_available'}",
        f"Full-text source: {provenance.get('source') or 'none'}",
        f"PDF URL: {provenance.get('pdf_url') or paper.get('pdf_url') or 'none'}",
        f"Parsed pages/chars: {provenance.get('page_count') or 0} / {provenance.get('character_count') or 0}",
        f"Full-text note: {provenance.get('error') or 'none'}",
        f"Evidence boundary: {boundary or 'PDF 文本已解析；关键 claim 仍需回原文页码、表格和公式复核。'}",
        "",
        "## Paper Signals",
        f"- Task: {card.signals.task}",
        f"- Contribution type: {card.signals.contribution_type}",
        f"- Method: {card.signals.method}",
        f"- Dataset: {card.signals.dataset}",
        f"- Metric: {card.signals.metric}",
        f"- Baseline: {card.signals.baseline}",
        f"- Claim: {card.signals.claim}",
        f"- Limitation: {card.signals.limitation}",
        f"- Missing signals: {', '.join(card.signals.missing_signals) if card.signals.missing_signals else 'none'}",
        "",
    ]
    sections = [f"## {section.title}\n\n{section.content}" for section in card.sections]
    return "\n".join(header + sections)


def card_markdown_title(evidence_level: str) -> str:
    if evidence_level == "full_text":
        return "Full-text Paper Card"
    if evidence_level == "abstract_only":
        return "Abstract-level Paper Card"
    if evidence_level == "supplemental_text":
        return "Supplemental-text Paper Card"
    return "Metadata Reading Outline"


def render_card_json(
    card: DeepPaperCard,
    paper: dict[str, Any],
    full_text: dict[str, Any] | None = None,
    updated_at: str = "",
) -> str:
    paper_id = paper.get("id") or ""
    return json.dumps(
        {
            "schema_version": "paper_card.v2",
            "paper_id": paper_id,
            "updated_at": updated_at,
            "paper": {
                "id": paper_id,
                "project_id": paper.get("project_id") or "",
                "title": paper.get("title") or card.paper_title,
                "authors": paper.get("authors") or "",
                "abstract": paper.get("abstract") or "",
                "year": paper.get("year") or "",
                "type": paper.get("type") or "",
                "venue": paper.get("venue") or "",
                "source": paper.get("source") or "",
                "url": paper.get("url") or "",
                "pdf_url": paper.get("pdf_url") or "",
                "priority": paper.get("priority") or "",
            },
            "card": card.to_dict(),
            "evidence_level": card.evidence_level,
            "evidence_quality": card.evidence_level,
            "evidence_qualification": card.evidence_qualification.model_dump(),
            "full_text": full_text or {
                "status": "not_available",
                "pdf_url": paper.get("pdf_url") or "",
                "source": "",
                "page_count": 0,
                "character_count": 0,
                "error": "",
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def paper_slug(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return normalized[:64] or "paper"


def summarize_context(context: str) -> str:
    if not context:
        return "当前只提供了标题或元数据，因此分析会明确标记为基于有限信息的结构化推断。"
    if len(context) <= 280:
        return context
    return f"{context[:277]}..."


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
